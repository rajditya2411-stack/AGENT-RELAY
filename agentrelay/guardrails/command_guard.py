"""
AgentRelay v2.0 — CommandGuard (CG-01)
Inspects and filters destructive or dangerous shell commands before execution.
"""

import re
from typing import Optional, Tuple


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
