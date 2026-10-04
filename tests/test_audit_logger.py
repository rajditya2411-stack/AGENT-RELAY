"""
Unit Tests for AgentRelay v2.0 Cryptographic Audit Logger (Phase 3)
Tests append-only ledger, SHA-256 hash chaining, Ed25519 signatures,
tamper detection, and compliance bundle exports.
"""

import json
from pathlib import Path
import tempfile
import unittest

from agentrelay.server.audit_logger import AuditLogger, GENESIS_PREV_HASH


class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / ".agentrelay_audit.jsonl"
        self.key_file = Path(self.temp_dir.name) / ".agentrelay_signing.key"
        self.logger = AuditLogger(
            ledger_path=str(self.ledger_file),
            key_path=str(self.key_file),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_key_generation_and_persistence(self):
        self.assertTrue(self.key_file.exists())
        pubkey1 = self.logger.public_key_hex
        self.assertTrue(len(pubkey1) > 0)

        # Re-instantiating should reuse existing key
        logger2 = AuditLogger(
            ledger_path=str(self.ledger_file),
            key_path=str(self.key_file),
        )
        self.assertEqual(logger2.public_key_hex, pubkey1)

    def test_log_event_and_hash_chain(self):
        # Entry 1: Intercept required
        r1 = self.logger.log_event(
            agent_id="grokbot",
            action_type="PUBLISH_POST",
            details={"content": "Hello World", "target": "twitter/@agentrelay"},
            status="QUARANTINED",
            risk_level="HIGH",
        )
        self.assertEqual(r1["seq_id"], 1)
        self.assertEqual(r1["prev_hash"], GENESIS_PREV_HASH)
        self.assertIsNotNone(r1["entry_hash"])
        self.assertIsNotNone(r1["signature"])

        # Entry 2: User approval
        r2 = self.logger.log_event(
            agent_id="mobile_user",
            action_type="INTERCEPT_RESOLVED",
            details={"intercept_id": "int_001", "decision": "APPROVE"},
            status="APPROVED",
            risk_level="INFO",
        )
        self.assertEqual(r2["seq_id"], 2)
        self.assertEqual(r2["prev_hash"], r1["entry_hash"])

        # Entry 3: Execution trace
        r3 = self.logger.log_event(
            agent_id="grokbot",
            action_type="PUBLISH_POST",
            details={"postId": "post_123", "target": "twitter/@agentrelay"},
            status="EXECUTED",
            risk_level="HIGH",
        )
        self.assertEqual(r3["seq_id"], 3)
        self.assertEqual(r3["prev_hash"], r2["entry_hash"])

        # Verify integrity
        valid, err = self.logger.verify_integrity()
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_tamper_detection_payload_alteration(self):
        # Write valid entries
        self.logger.log_event("muse", "SEND_MESSAGE", {"to": "+1234"}, "QUARANTINED", "HIGH")
        self.logger.log_event("mobile_user", "APPROVE", {"to": "+1234"}, "APPROVED", "INFO")

        valid, err = self.logger.verify_integrity()
        self.assertTrue(valid)

        # Maliciously modify entry on disk (tampering with payload)
        records = self.logger.read_records()
        records[0]["details"]["to"] = "+9999_TAMPERED"

        with open(self.ledger_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        valid, err = self.logger.verify_integrity()
        self.assertFalse(valid)
        self.assertIn("tamper", err.lower())

    def test_tamper_detection_broken_chain(self):
        # Write entries
        self.logger.log_event("dots", "RUN_COMMAND", {"cmd": "pytest"}, "EXECUTED", "LOW")
        self.logger.log_event("dots", "WRITE_FILE", {"file": "app.py"}, "EXECUTED", "LOW")

        # Corrupt prev_hash of record 2
        records = self.logger.read_records()
        records[1]["prev_hash"] = "f" * 64

        with open(self.ledger_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        valid, err = self.logger.verify_integrity()
        self.assertFalse(valid)
        self.assertIn("broken", err.lower())

    def test_compliance_bundle_export(self):
        self.logger.log_event("grokbot", "SEARCH_PULSE", {"query": "safety"}, "COMPLETED", "INFO")
        self.logger.log_event("muse", "DRAFT_OUTREACH", {"campaign": "v2"}, "COMPLETED", "LOW")

        bundle_path = Path(self.temp_dir.name) / "compliance_bundle.json"
        bundle = self.logger.export_compliance_bundle(output_path=str(bundle_path))

        self.assertEqual(bundle["complianceBundleVersion"], "2.0")
        self.assertEqual(bundle["totalRecords"], 2)
        self.assertTrue(bundle["integrityVerified"])
        self.assertEqual(bundle["signingAlgorithm"], "Ed25519")
        self.assertTrue(bundle_path.exists())

        # Verify bundle contents on disk
        with open(bundle_path, "r", encoding="utf-8") as f:
            loaded_bundle = json.load(f)
        self.assertEqual(loaded_bundle["totalRecords"], 2)
        self.assertTrue(loaded_bundle["integrityVerified"])


if __name__ == "__main__":
    unittest.main()
