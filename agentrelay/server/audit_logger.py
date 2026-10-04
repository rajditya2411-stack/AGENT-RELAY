"""
AgentRelay v2.0 — Signed Append-Only Cryptographic Audit Ledger
Maintains an immutable, tamper-evident forensic ledger signing every intercept,
approval, and execution trace with Ed25519 signatures and SHA-256 state hashes.
Includes one-tap JSON compliance bundle export functionality.
"""

import base64
import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AuditLogger")

DEFAULT_LEDGER_FILENAME = ".agentrelay_audit.jsonl"
DEFAULT_KEY_FILENAME = ".agentrelay_signing.key"
GENESIS_PREV_HASH = "0" * 64

# Try importing Ed25519 from cryptography
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    HAS_ED25519 = True
except ImportError:
    HAS_ED25519 = False


class AuditLogger:
    """
    Append-only Cryptographic Ledger for AgentRelay.
    Signs all security gate decisions, agent mutations, and forensic traces.
    Verifies chain integrity and exports compliance bundles.
    """

    def __init__(
        self,
        ledger_path: Optional[str] = None,
        key_path: Optional[str] = None,
        private_key_bytes: Optional[bytes] = None,
    ):
        self.ledger_path = Path(ledger_path or DEFAULT_LEDGER_FILENAME).resolve()
        self.key_path = Path(key_path or DEFAULT_KEY_FILENAME).resolve()

        self._private_key = None
        self._public_key = None
        self._hmac_fallback_key: Optional[bytes] = None

        self._init_keys(private_key_bytes)
        self._latest_hash = self._read_latest_hash()

    def _init_keys(self, private_key_bytes: Optional[bytes]) -> None:
        """Initialize or load Ed25519 signing keys, or fallback to HMAC-SHA256."""
        if HAS_ED25519:
            try:
                if private_key_bytes:
                    self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
                elif self.key_path.exists():
                    with open(self.key_path, "rb") as kf:
                        raw = kf.read()
                    self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw[:32])
                else:
                    self._private_key = ed25519.Ed25519PrivateKey.generate()
                    raw = self._private_key.private_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PrivateFormat.Raw,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                    with open(self.key_path, "wb") as kf:
                        kf.write(raw)

                self._public_key = self._private_key.public_key()
                return
            except Exception as e:
                logger.warning(f"Failed to initialize Ed25519 key ({e}); using HMAC fallback.")

        # Fallback to HMAC-SHA256
        self._hmac_fallback_key = private_key_bytes or os.urandom(32)

    @property
    def public_key_hex(self) -> str:
        """Get hex string representation of public signing key."""
        if HAS_ED25519 and self._public_key:
            raw = self._public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            return raw.hex()
        return (self._hmac_fallback_key or b"").hex()

    def _read_latest_hash(self) -> str:
        """Scan ledger file for the most recent entry hash."""
        if not self.ledger_path.exists():
            return GENESIS_PREV_HASH

        last_hash = GENESIS_PREV_HASH
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        last_hash = entry.get("entry_hash", last_hash)
        except Exception as e:
            logger.warning(f"Error reading existing ledger: {e}")
        return last_hash

    def _get_next_seq_id(self) -> int:
        """Count existing entries to derive next monotonic sequence number."""
        if not self.ledger_path.exists():
            return 1
        count = 0
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1
        except Exception:
            pass
        return count + 1

    def _canonical_payload(
        self,
        seq_id: int,
        timestamp: float,
        agent_id: str,
        action_type: str,
        status: str,
        risk_level: str,
        details: Dict[str, Any],
        prev_hash: str,
    ) -> bytes:
        """Create deterministic canonical representation for hashing and signing."""
        data = {
            "seq_id": seq_id,
            "timestamp": timestamp,
            "agent_id": agent_id,
            "action_type": action_type,
            "status": status,
            "risk_level": risk_level,
            "details": details,
            "prev_hash": prev_hash,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _sign_hash(self, entry_hash_bytes: bytes) -> str:
        """Sign entry hash bytes and return base64 signature."""
        if HAS_ED25519 and self._private_key:
            sig = self._private_key.sign(entry_hash_bytes)
            return base64.b64encode(sig).decode("ascii")

        # Fallback HMAC signature
        import hmac
        h = hmac.new(self._hmac_fallback_key or b"", entry_hash_bytes, hashlib.sha256)
        return base64.b64encode(h.digest()).decode("ascii")

    def _verify_signature(self, entry_hash_bytes: bytes, sig_b64: str) -> bool:
        """Verify signature for entry hash bytes."""
        try:
            sig_bytes = base64.b64decode(sig_b64)
            if HAS_ED25519 and self._public_key:
                self._public_key.verify(sig_bytes, entry_hash_bytes)
                return True

            import hmac
            h = hmac.new(self._hmac_fallback_key or b"", entry_hash_bytes, hashlib.sha256)
            return hmac.compare_digest(h.digest(), sig_bytes)
        except Exception:
            return False

    def log_event(
        self,
        agent_id: str,
        action_type: str,
        details: Dict[str, Any],
        status: str,
        risk_level: str = "INFO",
    ) -> Dict[str, Any]:
        """
        Append a cryptographically signed entry into the ledger.
        Computes SHA-256 hash linked to previous entry and signs with Ed25519.
        """
        seq_id = self._get_next_seq_id()
        now = time.time()
        prev_hash = self._latest_hash

        canonical_bytes = self._canonical_payload(
            seq_id=seq_id,
            timestamp=now,
            agent_id=agent_id,
            action_type=action_type,
            status=status,
            risk_level=risk_level,
            details=details,
            prev_hash=prev_hash,
        )

        entry_hash = hashlib.sha256(canonical_bytes).hexdigest()
        signature = self._sign_hash(entry_hash.encode("ascii"))

        record = {
            "seq_id": seq_id,
            "timestamp": now,
            "iso_time": datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat(),
            "agent_id": agent_id,
            "action_type": action_type,
            "status": status,
            "risk_level": risk_level,
            "details": details,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
            "signature": signature,
            "signer_pubkey": self.public_key_hex,
            "algorithm": "Ed25519" if HAS_ED25519 and self._public_key else "HMAC-SHA256",
        }

        # Append atomically to ledger file
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        self._latest_hash = entry_hash
        logger.info(
            f"Audit entry #{seq_id} recorded for [{agent_id}] {action_type} -> {status} (hash: {entry_hash[:12]}...)"
        )
        return record

    def read_records(self) -> List[Dict[str, Any]]:
        """Read all ledger records from disk."""
        if not self.ledger_path.exists():
            return []

        records = []
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def verify_integrity(self) -> Tuple[bool, Optional[str]]:
        """
        Traverse the entire ledger and cryptographically verify:
        1. Monotonic sequence numbers.
        2. Unbroken SHA-256 hash chain (prev_hash matches preceding entry_hash).
        3. Canonical payload hash computation matches entry_hash.
        4. Valid Ed25519 signature on entry_hash.
        Returns (True, None) or (False, error_description).
        """
        records = self.read_records()
        if not records:
            return True, None

        expected_prev_hash = GENESIS_PREV_HASH

        for idx, rec in enumerate(records):
            expected_seq = idx + 1
            seq_id = rec.get("seq_id")

            # Check sequence ordering
            if seq_id != expected_seq:
                return False, f"Sequence discontinuity at index {idx}: expected {expected_seq}, found {seq_id}"

            # Check hash chain continuity
            prev_hash = rec.get("prev_hash")
            if prev_hash != expected_prev_hash:
                return False, f"Hash chain broken at seq #{seq_id}: prev_hash does not match preceding entry_hash."

            # Verify canonical payload hash
            canonical_bytes = self._canonical_payload(
                seq_id=seq_id,
                timestamp=rec.get("timestamp", 0.0),
                agent_id=rec.get("agent_id", ""),
                action_type=rec.get("action_type", ""),
                status=rec.get("status", ""),
                risk_level=rec.get("risk_level", "INFO"),
                details=rec.get("details", {}),
                prev_hash=prev_hash,
            )
            recomputed_hash = hashlib.sha256(canonical_bytes).hexdigest()
            if recomputed_hash != rec.get("entry_hash"):
                return False, f"Payload tamper detected at seq #{seq_id}: entry_hash mismatch."

            # Verify cryptographic signature
            sig = rec.get("signature", "")
            if not self._verify_signature(recomputed_hash.encode("ascii"), sig):
                return False, f"Cryptographic signature invalid at seq #{seq_id}."

            expected_prev_hash = rec.get("entry_hash")

        return True, None

    def export_compliance_bundle(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Export a complete, self-verifying JSON compliance bundle.
        Includes full audit trail, integrity verification proof, and public signing key.
        """
        records = self.read_records()
        valid, issue = self.verify_integrity()
        now = time.time()

        bundle = {
            "complianceBundleVersion": "2.0",
            "exportedAt": now,
            "exportedAtIso": datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat(),
            "totalRecords": len(records),
            "genesisHash": records[0]["entry_hash"] if records else None,
            "latestHash": records[-1]["entry_hash"] if records else None,
            "integrityVerified": valid,
            "verificationReport": "All cryptographic signatures and hash-chain links valid." if valid else f"Integrity check failed: {issue}",
            "publicKeyHex": self.public_key_hex,
            "signingAlgorithm": "Ed25519" if HAS_ED25519 and self._public_key else "HMAC-SHA256",
            "records": records,
        }

        if output_path:
            out_file = Path(output_path).resolve()
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(bundle, f, indent=2)
            logger.info(f"Compliance audit bundle exported to {out_file}")

        return bundle
