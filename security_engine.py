"""
AgentRelay — Security Policy & Sandboxing Engine (Phase 4 / v2.0 Modular Facade)
Provides strict security hardening:
1. Path Traversal & Workspace Boundary Enforcement
2. Protected Secrets & Sensitive File Shield (.env, ssh keys, certificates)
3. Secret Redaction on all streamed tokens & tool outputs
4. Dangerous Command / Destructive RCE Filtering
5. Runaway Loop & Rate-Limit Protection
6. v2.0 Universal ActionGuard & Mutation Interceptor
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agentrelay.guardrails.action_guard import ActionGuard, InterceptRecord
from agentrelay.guardrails.command_guard import CommandGuard
from agentrelay.guardrails.path_guard import PathGuard, SecurityViolation
from agentrelay.guardrails.rate_guard import ExecutionRateGuard
from agentrelay.guardrails.secret_redactor import SecretRedactor


class SecurityEngine:
    """Unified security engine orchestrating all guards and redactors (v1 & v2 compatible)."""

    def __init__(self, workspace_path: str = "."):
        self.workspace_path = workspace_path
        self.path_guard = PathGuard(workspace_path)
        self.secret_redactor = SecretRedactor()
        self.command_guard = CommandGuard()
        self.rate_guard = ExecutionRateGuard()
        self.action_guard = ActionGuard(workspace_path)

    def sanitize_output(self, text: str) -> str:
        return self.secret_redactor.redact(text)

    def validate_file_access(self, target_path: str) -> Path:
        return self.path_guard.validate_path(target_path)

    def validate_command(self, cmd: str) -> Tuple[bool, Optional[str]]:
        return self.command_guard.validate_command(cmd)


__all__ = [
    "SecurityViolation",
    "SecretRedactor",
    "PathGuard",
    "CommandGuard",
    "ExecutionRateGuard",
    "SecurityEngine",
    "ActionGuard",
    "InterceptRecord",
]
