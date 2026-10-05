"""
Unit Tests for AgentRelay CLI (Phase 5)
"""

import subprocess
import sys
import unittest


class TestCLI(unittest.TestCase):
    def test_cli_version(self):
        result = subprocess.run(
            [sys.executable, "-m", "agentrelay", "--version"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("agentrelay 2.0.0", result.stdout)

    def test_cli_audit_verify(self):
        result = subprocess.run(
            [sys.executable, "-m", "agentrelay", "audit", "verify"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Cryptographic chain verified intact", result.stdout)

    def test_cli_vault_status(self):
        result = subprocess.run(
            [sys.executable, "-m", "agentrelay", "vault", "status"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Vault Path:", result.stdout)


if __name__ == "__main__":
    unittest.main()
