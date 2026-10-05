"""
AgentRelay v2.0 — Local BYOK Encrypted Vault
Provides military-grade AES-256-GCM encrypted keystore (.agentrelay_vault.enc)
with PBKDF2 key derivation for frontier provider API credentials.
Guarantees zero raw keys are leaked or transmitted across external networks.
"""

import base64
import json
import logging
import os
from pathlib import Path
import platform
import time
from typing import Any, Dict, List, Optional
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("Vault")

DEFAULT_VAULT_FILENAME = ".agentrelay_vault.enc"
PBKDF2_ITERATIONS = 100_000
SALT_SIZE = 16
NONCE_SIZE = 12


class Vault:
    """
    Local AES-256-GCM Encrypted Keystore for Frontier Agent API Credentials.
    Supports setting, getting, rotating, and clearing keys for xAI, OpenAI, Anthropic,
    and Meta Graph, with zero raw key leakage to third parties.
    """

    SUPPORTED_PROVIDERS = {"xai", "openai", "anthropic", "meta_graph"}

    def __init__(
        self,
        vault_path: Optional[str] = None,
        passphrase: Optional[str] = None,
    ):
        self.vault_path = Path(vault_path or DEFAULT_VAULT_FILENAME).resolve()
        self._passphrase = passphrase
        self._derived_key: Optional[bytes] = None
        self._salt: Optional[bytes] = None
        self._is_unlocked: bool = False
        self._data: Dict[str, Any] = {"keys": {}, "metadata": {}}

        # Attempt unlock if passphrase provided or if vault file exists/can use machine salt
        self.unlock(passphrase=passphrase)

    @property
    def is_unlocked(self) -> bool:
        return self._is_unlocked

    @property
    def is_locked(self) -> bool:
        return not self._is_unlocked

    def lock(self) -> None:
        """Lock the vault and zero out in-memory data."""
        self._is_unlocked = False
        self._derived_key = None
        self._data = {"keys": {}, "metadata": {}}
        logger.info("Vault locked: in-memory credentials cleared.")

    def list_configured_providers(self) -> List[str]:
        return self.list_providers()

    def wipe_all(self) -> None:
        self.clear_all()

    @staticmethod
    def _get_machine_bound_passphrase() -> str:
        """Derive a stable machine-bound secret if no user passphrase is provided."""
        node_id = str(uuid.getnode())
        system_id = platform.node() + platform.system()
        combined = f"agentrelay-machine-vault::{node_id}::{system_id}"
        return combined

    def _derive_encryption_key(self, passphrase: str, salt: bytes) -> bytes:
        """Derive 256-bit AES key using PBKDF2HMAC with SHA-256."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return kdf.derive(passphrase.encode("utf-8"))

    def unlock(self, passphrase: Optional[str] = None) -> bool:
        """
        Unlock and decrypt the vault from disk.
        If the vault file does not exist, initializes an empty vault structure.
        """
        effective_passphrase = passphrase or self._passphrase or self._get_machine_bound_passphrase()

        if not self.vault_path.exists():
            # Brand new vault
            self._salt = os.urandom(SALT_SIZE)
            self._derived_key = self._derive_encryption_key(effective_passphrase, self._salt)
            self._data = {"keys": {}, "metadata": {}}
            self._is_unlocked = True
            self._passphrase = effective_passphrase
            return True

        # Existing vault file: read and decrypt
        try:
            with open(self.vault_path, "r", encoding="utf-8") as f:
                envelope = json.load(f)

            salt = base64.b64decode(envelope["salt"])
            nonce = base64.b64decode(envelope["nonce"])
            ciphertext = base64.b64decode(envelope["ciphertext"])

            derived_key = self._derive_encryption_key(effective_passphrase, salt)
            aesgcm = AESGCM(derived_key)
            decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)

            self._derived_key = derived_key
            self._salt = salt
            self._data = json.loads(decrypted_bytes.decode("utf-8"))
            self._is_unlocked = True
            self._passphrase = effective_passphrase
            logger.info(f"Vault successfully unlocked from {self.vault_path}")
            return True

        except (InvalidTag, KeyError, ValueError) as e:
            logger.error(f"Failed to decrypt vault: {e}")
            self._is_unlocked = False
            self._derived_key = None
            raise ValueError("Failed to decrypt vault: invalid passphrase or corrupted vault file.") from e

    def lock(self) -> None:
        """Wipe plaintext keys from memory and lock vault."""
        self._data = {"keys": {}, "metadata": {}}
        self._derived_key = None
        self._is_unlocked = False
        logger.info("Vault locked: in-memory credentials cleared.")

    def _save_to_disk(self) -> None:
        """Encrypt in-memory keys with AES-256-GCM and atomically save to disk."""
        if not self._is_unlocked or not self._derived_key or not self._salt:
            raise PermissionError("Cannot save: vault is locked.")

        nonce = os.urandom(NONCE_SIZE)
        aesgcm = AESGCM(self._derived_key)

        plaintext = json.dumps(self._data).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        envelope = {
            "version": 1,
            "algorithm": "AES-256-GCM",
            "kdf": "PBKDF2HMAC-SHA256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": base64.b64encode(self._salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "updated_at": time.time(),
        }

        # Write atomically via temp file
        temp_path = self.vault_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)

        os.replace(temp_path, self.vault_path)
        logger.debug(f"Vault successfully saved to {self.vault_path}")

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        return provider.strip().lower().replace("-", "_").replace(" ", "_")

    def set_key(self, provider: str, key_value: str) -> None:
        """
        Store a provider API key in encrypted vault.
        Immediately encrypts and writes changes to disk.
        """
        if not self._is_unlocked:
            raise PermissionError("Vault is locked. Call unlock() first.")

        p = self._normalize_provider(provider)
        now = time.time()

        is_new = p not in self._data["keys"]
        self._data["keys"][p] = key_value.strip()

        if is_new:
            self._data["metadata"][p] = {
                "created_at": now,
                "rotated_at": None,
                "rotation_count": 0,
            }
        else:
            meta = self._data["metadata"].get(p, {})
            meta["updated_at"] = now
            self._data["metadata"][p] = meta

        self._save_to_disk()
        logger.info(f"Encrypted key stored for provider: '{p}'")

    def get_key(self, provider: str) -> Optional[str]:
        """Retrieve decrypted raw API key for provider."""
        if not self._is_unlocked:
            raise PermissionError("Vault is locked. Call unlock() first.")

        p = self._normalize_provider(provider)
        return self._data["keys"].get(p)

    def rotate_key(self, provider: str, new_key_value: str) -> Dict[str, Any]:
        """
        Rotate existing provider key, incrementing rotation counter and updating timestamp.
        """
        if not self._is_unlocked:
            raise PermissionError("Vault is locked. Call unlock() first.")

        p = self._normalize_provider(provider)
        if p not in self._data["keys"]:
            # If not yet set, set as initial
            self.set_key(p, new_key_value)
            return self._data["metadata"][p]

        now = time.time()
        self._data["keys"][p] = new_key_value.strip()

        meta = self._data["metadata"].setdefault(p, {
            "created_at": now,
            "rotated_at": None,
            "rotation_count": 0,
        })
        meta["rotated_at"] = now
        meta["rotation_count"] = meta.get("rotation_count", 0) + 1
        meta["last_rotation_timestamp"] = now

        self._save_to_disk()
        logger.info(f"Key rotated for provider '{p}' (rotation #{meta['rotation_count']})")
        return meta

    def clear_key(self, provider: str) -> bool:
        """Remove key and metadata for specific provider."""
        if not self._is_unlocked:
            raise PermissionError("Vault is locked. Call unlock() first.")

        p = self._normalize_provider(provider)
        if p in self._data["keys"]:
            del self._data["keys"][p]
            self._data["metadata"].pop(p, None)
            self._save_to_disk()
            logger.info(f"Key cleared for provider: '{p}'")
            return True
        return False

    def clear_all(self) -> None:
        """Wipe all keys and metadata from both memory and disk."""
        if not self._is_unlocked:
            raise PermissionError("Vault is locked. Call unlock() first.")

        self._data = {"keys": {}, "metadata": {}}
        self._save_to_disk()
        logger.info("All credentials wiped from encrypted vault.")

    def list_providers(self) -> List[str]:
        """List configured providers without exposing secret keys."""
        if not self._is_unlocked:
            raise PermissionError("Vault is locked. Call unlock() first.")
        return sorted(list(self._data["keys"].keys()))

    def get_masked_key(self, provider: str) -> Optional[str]:
        """
        Return a safe, masked representation of the provider key
        (e.g., 'sk-ant...98ab').
        """
        raw = self.get_key(provider)
        if not raw:
            return None
        if len(raw) <= 8:
            return "****"
        return f"{raw[:4]}...{raw[-4:]}"

    def export_summary(self) -> Dict[str, Any]:
        """
        Export a safe non-sensitive summary of configured keys and rotation status.
        Never outputs raw secret values.
        """
        if not self._is_unlocked:
            raise PermissionError("Vault is locked. Call unlock() first.")

        summary = {}
        for prov, key in self._data["keys"].items():
            meta = self._data["metadata"].get(prov, {})
            summary[prov] = {
                "configured": True,
                "maskedKey": self.get_masked_key(prov),
                "createdAt": meta.get("created_at"),
                "rotatedAt": meta.get("rotated_at"),
                "rotationCount": meta.get("rotation_count", 0),
            }
        return {
            "vaultPath": str(self.vault_path),
            "unlocked": self._is_unlocked,
            "providerCount": len(summary),
            "providers": summary,
        }
