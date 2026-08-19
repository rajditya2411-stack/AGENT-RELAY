"""
AgentRelay — Automated Security Verification Test Suite (Phase 4)
"""

import sys
import time
import unittest
from pathlib import Path

from security_engine import (
    CommandGuard,
    ExecutionRateGuard,
    PathGuard,
    SecretRedactor,
    SecurityEngine,
    SecurityViolation,
)


class TestSecretRedaction(unittest.TestCase):
    def test_gemini_key_redaction(self):
        text = "My API key is AIzaSyD98fGhJkLmNoPqRsTuVwXyZ1234567890 please keep it safe."
        sanitized = SecretRedactor.redact(text)
        self.assertNotIn("AIzaSyD98fGhJkLmNoPqRsTuVwXyZ1234567890", sanitized)
        self.assertIn("[REDACTED_GEMINI_KEY]", sanitized)

    def test_openai_key_redaction(self):
        text = "Key sk-proj-1234567890abcdef1234567890abcdef12 was leaked."
        sanitized = SecretRedactor.redact(text)
        self.assertNotIn("sk-proj-1234567890abcdef1234567890abcdef12", sanitized)
        self.assertIn("[REDACTED_API_KEY]", sanitized)

    def test_github_token_redaction(self):
        text = "Token: ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        sanitized = SecretRedactor.redact(text)
        self.assertNotIn("ghp_1234567890abcdefghijklmnopqrstuvwxyz", sanitized)
        self.assertIn("[REDACTED_GITHUB_TOKEN]", sanitized)

    def test_bearer_jwt_redaction(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        sanitized = SecretRedactor.redact(text)
        self.assertIn("Bearer [REDACTED_JWT_TOKEN]", sanitized)

    def test_password_assignment_redaction(self):
        text = "db_pass='supersecretpassword123'"
        sanitized = SecretRedactor.redact(text)
        self.assertNotIn("supersecretpassword123", sanitized)
        self.assertIn("[REDACTED_SECRET]", sanitized)


class TestPathGuard(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(__file__).parent.resolve()
        self.guard = PathGuard(str(self.workspace))

    def test_allow_valid_workspace_file(self):
        valid = self.guard.validate_path(str(self.workspace / "bridge.py"))
        self.assertTrue(valid.exists())

    def test_block_path_traversal(self):
        with self.assertRaises(SecurityViolation):
            self.guard.validate_path(str(self.workspace / "../../../Windows/System32"))

    def test_block_env_file(self):
        with self.assertRaises(SecurityViolation):
            self.guard.validate_path(str(self.workspace / ".env"))

    def test_block_ssh_key_file(self):
        with self.assertRaises(SecurityViolation):
            self.guard.validate_path(str(self.workspace / "id_rsa"))

    def test_block_pem_extension(self):
        with self.assertRaises(SecurityViolation):
            self.guard.validate_path(str(self.workspace / "cert.pem"))


class TestCommandGuard(unittest.TestCase):
    def test_safe_commands_allowed(self):
        safe_cmds = [
            "npm test",
            "pytest",
            "git status",
            "python -m unittest",
            "node index.js",
            "cargo build",
        ]
        for cmd in safe_cmds:
            is_safe, reason = CommandGuard.validate_command(cmd)
            self.assertTrue(is_safe, f"Expected '{cmd}' to be safe, but got reason: {reason}")

    def test_destructive_commands_blocked(self):
        dangerous_cmds = [
            "rm -rf /",
            "rm -rf ~/",
            "del /s C:\\",
            "format D:",
            "shutdown -s -t 0",
            "powershell -enc aW52b2tlLWV4cHJlc3Npb24=",
            "diskpart",
            "mkfs /dev/sda1",
        ]
        for cmd in dangerous_cmds:
            is_safe, reason = CommandGuard.validate_command(cmd)
            self.assertFalse(is_safe, f"Expected '{cmd}' to be blocked!")
            self.assertIsNotNone(reason)


class TestExecutionRateGuard(unittest.TestCase):
    def test_max_tool_calls_protection(self):
        guard = ExecutionRateGuard(max_tool_calls_per_turn=5)
        guard.start_turn()
        for _ in range(5):
            guard.record_tool_call()

        # 6th call exceeds threshold and triggers runaway loop protection
        with self.assertRaises(SecurityViolation):
            guard.record_tool_call()

    def test_turn_timeout_protection(self):
        guard = ExecutionRateGuard(turn_timeout_seconds=0.1)
        guard.start_turn()
        time.sleep(0.15)
        with self.assertRaises(SecurityViolation):
            guard.record_tool_call()


if __name__ == "__main__":
    unittest.main()
