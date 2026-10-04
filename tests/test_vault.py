"""
Unit Tests for AgentRelay v2.0 Local BYOK Encrypted Vault (Phase 3)
Tests AES-256-GCM encryption, PBKDF2 derivation, key setting, getting,
rotation, masking, and security isolation.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest

from agentrelay.server.vault import Vault


class TestVault(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_file = Path(self.temp_dir.name) / ".agentrelay_vault.enc"
        self.passphrase = "UltraSecureMasterPassphrase-2026!"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_vault_initialization_and_set_get(self):
        vault = Vault(vault_path=str(self.vault_file), passphrase=self.passphrase)
        self.assertTrue(vault.is_unlocked)

        # Initially empty
        self.assertEqual(vault.list_providers(), [])
        self.assertIsNone(vault.get_key("xai"))

        # Set keys
        vault.set_key("xai", "xai-grok-sec-token-123456789")
        vault.set_key("openai", "sk-proj-openai-9988776655")
        vault.set_key("anthropic", "sk-ant-claude-alpha-001122")
        vault.set_key("meta_graph", "EAAB-meta-graph-whatsapp-token")

        # Verify retrieval
        self.assertEqual(vault.get_key("xai"), "xai-grok-sec-token-123456789")
        self.assertEqual(vault.get_key("OpenAI"), "sk-proj-openai-9988776655")
        self.assertEqual(vault.get_key("anthropic"), "sk-ant-claude-alpha-001122")
        self.assertEqual(vault.get_key("meta-graph"), "EAAB-meta-graph-whatsapp-token")

        # Verify providers list
        providers = vault.list_providers()
        self.assertEqual(sorted(providers), ["anthropic", "meta_graph", "openai", "xai"])

    def test_disk_encryption_no_plaintext_leak(self):
        vault = Vault(vault_path=str(self.vault_file), passphrase=self.passphrase)
        secret_key = "super-confidential-secret-api-key-9999"
        vault.set_key("openai", secret_key)

        # Read raw file on disk
        self.assertTrue(self.vault_file.exists())
        with open(self.vault_file, "r", encoding="utf-8") as f:
            disk_content = f.read()

        # Zero plaintext leakage
        self.assertNotIn(secret_key, disk_content)
        envelope = json.loads(disk_content)
        self.assertEqual(envelope["algorithm"], "AES-256-GCM")
        self.assertIn("salt", envelope)
        self.assertIn("nonce", envelope)
        self.assertIn("ciphertext", envelope)

    def test_vault_persistence_and_reload(self):
        # Create and write
        v1 = Vault(vault_path=str(self.vault_file), passphrase=self.passphrase)
        v1.set_key("xai", "xai-key-alpha")
        del v1

        # Reopen with correct passphrase
        v2 = Vault(vault_path=str(self.vault_file), passphrase=self.passphrase)
        self.assertTrue(v2.is_unlocked)
        self.assertEqual(v2.get_key("xai"), "xai-key-alpha")

        # Attempt to reopen with wrong passphrase
        with self.assertRaises(ValueError):
            Vault(vault_path=str(self.vault_file), passphrase="IncorrectPassword123!")

    def test_key_rotation(self):
        vault = Vault(vault_path=str(self.vault_file), passphrase=self.passphrase)
        vault.set_key("anthropic", "sk-ant-v1")

        meta = vault.rotate_key("anthropic", "sk-ant-v2")
        self.assertEqual(meta["rotation_count"], 1)
        self.assertIsNotNone(meta["rotated_at"])
        self.assertEqual(vault.get_key("anthropic"), "sk-ant-v2")

        meta2 = vault.rotate_key("anthropic", "sk-ant-v3")
        self.assertEqual(meta2["rotation_count"], 2)
        self.assertEqual(vault.get_key("anthropic"), "sk-ant-v3")

    def test_key_masking_and_summary(self):
        vault = Vault(vault_path=str(self.vault_file), passphrase=self.passphrase)
        vault.set_key("xai", "xai-9876543210abcdef")

        masked = vault.get_masked_key("xai")
        self.assertEqual(masked, "xai-...cdef")
        self.assertNotIn("9876543210", masked)

        summary = vault.export_summary()
        self.assertEqual(summary["providerCount"], 1)
        self.assertIn("xai", summary["providers"])
        self.assertEqual(summary["providers"]["xai"]["maskedKey"], "xai-...cdef")

    def test_key_clearing(self):
        vault = Vault(vault_path=str(self.vault_file), passphrase=self.passphrase)
        vault.set_key("meta_graph", "EAAB-test-token")
        vault.set_key("openai", "sk-openai-test")

        self.assertTrue(vault.clear_key("meta_graph"))
        self.assertIsNone(vault.get_key("meta_graph"))
        self.assertFalse(vault.clear_key("non_existent_provider"))

        # Clear all
        vault.clear_all()
        self.assertEqual(vault.list_providers(), [])
        self.assertIsNone(vault.get_key("openai"))

    def test_vault_lock(self):
        vault = Vault(vault_path=str(self.vault_file), passphrase=self.passphrase)
        vault.set_key("xai", "secret-token")

        vault.lock()
        self.assertFalse(vault.is_unlocked)

        with self.assertRaises(PermissionError):
            vault.get_key("xai")

        with self.assertRaises(PermissionError):
            vault.set_key("xai", "new-key")

        # Unlock again
        vault.unlock(self.passphrase)
        self.assertTrue(vault.is_unlocked)
        self.assertEqual(vault.get_key("xai"), "secret-token")

    def test_machine_bound_passphrase(self):
        # When passphrase is None, auto-derives stable machine-bound key
        v1 = Vault(vault_path=str(self.vault_file), passphrase=None)
        v1.set_key("anthropic", "machine-bound-secret")
        del v1

        # Reopen with None should derive the same key on this machine
        v2 = Vault(vault_path=str(self.vault_file), passphrase=None)
        self.assertEqual(v2.get_key("anthropic"), "machine-bound-secret")


if __name__ == "__main__":
    unittest.main()
