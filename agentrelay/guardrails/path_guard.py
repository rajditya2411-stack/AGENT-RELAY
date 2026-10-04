"""
AgentRelay v2.0 — PathGuard (PG-04)
Enforces that all file operations stay inside the allowed workspace directory and blocks protected secrets.
"""

from pathlib import Path


class SecurityViolation(Exception):
    """Raised when an operation violates the security policy."""
    pass


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
