"""
AgentRelay v2.0 — Secret Redactor Guardrail
Detects and redacts credentials, private keys, and API tokens from streams.
"""

import re
from typing import Any


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
