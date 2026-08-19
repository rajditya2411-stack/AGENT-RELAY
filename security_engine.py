"""
AgentRelay — Security Policy & Sandboxing Engine (Phase 4)
Provides strict security hardening:
1. Path Traversal & Workspace Boundary Enforcement
2. Protected Secrets & Sensitive File Shield (.env, ssh keys, certificates)
3. Secret Redaction on all streamed tokens & tool outputs
4. Dangerous Command / Destructive RCE Filtering
5. Runaway Loop & Rate-Limit Protection
"""

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SecurityViolation(Exception):
    """Raised when an operation violates the security policy."""
    pass


class SecretRedactor:
    """Detects and redacts credentials, private keys, and API tokens from streams."""

    PATTERNS = [
        # Google / Gemini API Keys
        (re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}"), "[REDACTED_GEMINI_KEY]"),
        # OpenAI / Anthropic Keys
        (re.compile(r"sk-(?:proj-|live-)?[a-zA-Z0-9_-]{32,}"), "[REDACTED_API_KEY]"),
        # GitHub Personal Access Tokens
        (re.compile(r"gh[pousr]_[a-zA-Z0-9]{36,40}"), "[REDACTED_GITHUB_TOKEN]"),
        # JWT Bearer Tokens
        (re.compile(r"Bearer\s+eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"), "Bearer [REDACTED_JWT_TOKEN]"),
        # Private Keys
        (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
        # Generic Secret/Password assignments in envs or code
        (re.compile(r"(?i)(password|secret|api_key|access_token|db_pass)\s*[:=]\s*['\"]([^'\"]{6,})['\"]"), r"\1='[REDACTED_SECRET]'"),
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        """Scrubs all sensitive credentials from text."""
        if not isinstance(text, str):
            return text
        sanitized = text
        for pattern, replacement in cls.PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized


class PathGuard:
    """Enforces that all file operations stay inside the allowed workspace directory."""

    PROTECTED_FILENAMES = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "id_rsa",
        "id_rsa.pub",
        "id_ed25519",
        "id_ed25519.pub",
        "credentials.json",
        "service_account.json",
    }

    PROTECTED_EXTENSIONS = {
        ".pem",
        ".key",
        ".pfx",
        ".p12",
        ".kdbx",
    }

    def __init__(self, workspace_path: str = "."):
        self.workspace_root = Path(workspace_path).resolve()

    def validate_path(self, target_path: str, allow_read_only_config: bool = False) -> Path:
        """Validates that target_path is inside workspace and is not a protected secret file."""
        resolved = Path(target_path).resolve()
        
        # 1. Path Traversal Check (Must be within workspace root)
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            raise SecurityViolation(
                f"Path Traversal Blocked: '{target_path}' resolves outside the allowed workspace '{self.workspace_root}'"
            )

        # 2. Sensitive File Check
        filename = resolved.name.lower()
        if filename in self.PROTECTED_FILENAMES:
            raise SecurityViolation(f"Protected Secret File Access Blocked: '{filename}'")

        if resolved.suffix.lower() in self.PROTECTED_EXTENSIONS:
            raise SecurityViolation(f"Protected File Extension Blocked: '{resolved.suffix}'")

        return resolved


class CommandGuard:
    """Inspects and filters destructive or dangerous shell commands."""

    BLOCKED_PATTERNS = [
        # Dangerous system modification commands
        re.compile(r"(?i)\b(rm\s+-rf\s+[/~]|rmdir\s+/[sq]|del\s+/[sq]\s+[a-z]:\\|format\s+[a-z]:)"),
        # System control / power commands
        re.compile(r"(?i)\b(shutdown|reboot|init\s+0|halt|poweroff)\b"),
        # Disk partitioning / low-level disk tools
        re.compile(r"(?i)\b(diskpart|bcdedit|mkfs|fdisk|dd\s+if=)\b"),
        # Encoded / obfuscated command runners
        re.compile(r"(?i)\b(powershell.*-(?:enc|encodedcommand)|base64\s+-d\s*\|\s*sh)\b"),
        # Fork bomb patterns
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
    ]

    @classmethod
    def validate_command(cls, command_str: str) -> Tuple[bool, Optional[str]]:
        """Checks if a command is permitted. Returns (is_safe, reason_if_unsafe)."""
        cmd = command_str.strip()
        for pattern in cls.BLOCKED_PATTERNS:
            if pattern.search(cmd):
                return False, f"Dangerous command blocked by security policy: '{cmd}'"
        return True, None


class ExecutionRateGuard:
    """Protects against runaway agent loops and infinite tool executions."""

    def __init__(self, max_tool_calls_per_turn: int = 25, turn_timeout_seconds: float = 300.0):
        self.max_tool_calls = max_tool_calls_per_turn
        self.turn_timeout = turn_timeout_seconds
        self.tool_call_count = 0
        self.turn_start_time = 0.0

    def start_turn(self):
        self.tool_call_count = 0
        self.turn_start_time = time.time()

    def record_tool_call(self):
        self.tool_call_count += 1
        # Check loop limit
        if self.tool_call_count > self.max_tool_calls:
            raise SecurityViolation(
                f"Runaway Loop Prevention: Exceeded max allowed tool calls ({self.max_tool_calls}) in a single turn."
            )
        # Check turn timeout
        elapsed = time.time() - self.turn_start_time
        if elapsed > self.turn_timeout:
            raise SecurityViolation(
                f"Execution Timeout: Task exceeded maximum allowed duration ({self.turn_timeout}s)."
            )


class SecurityEngine:
    """Unified security engine orchestrating all guards and redactors."""

    def __init__(self, workspace_path: str = "."):
        self.path_guard = PathGuard(workspace_path)
        self.secret_redactor = SecretRedactor()
        self.command_guard = CommandGuard()
        self.rate_guard = ExecutionRateGuard()

    def sanitize_output(self, text: str) -> str:
        return self.secret_redactor.redact(text)

    def validate_file_access(self, target_path: str) -> Path:
        return self.path_guard.validate_path(target_path)

    def validate_command(self, cmd: str) -> Tuple[bool, Optional[str]]:
        return self.command_guard.validate_command(cmd)
