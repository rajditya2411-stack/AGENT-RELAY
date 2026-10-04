"""
AgentRelay v2.0 — ActionGuard
Universal Mutation & Security Interceptor Gate.
Unifies PathGuard, CommandGuard, SecretRedactor, and ExecutionRateGuard with
Autonomy Tier governance and real-time quarantine countdowns for personal autonomous agents.
"""

from dataclasses import dataclass, field
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from agentrelay.core.events import (
    ActionType,
    AgentEvent,
    AutonomyTier,
    EventType,
    MutationPayload,
    RiskLevel,
    SourceMode,
)
from agentrelay.guardrails.command_guard import CommandGuard
from agentrelay.guardrails.path_guard import PathGuard, SecurityViolation
from agentrelay.guardrails.rate_guard import ExecutionRateGuard
from agentrelay.guardrails.secret_redactor import SecretRedactor

logger = logging.getLogger("ActionGuard")


@dataclass
class InterceptRecord:
    """Represents a suspended action quarantined pending human authorization."""
    intercept_id: str
    agent_id: str
    action_type: ActionType
    risk_level: RiskLevel
    target: str
    description: str
    content_preview: str
    created_at: float = field(default_factory=time.time)
    quarantine_timer_sec: int = 30
    status: str = "PENDING"  # PENDING, APPROVED, BLOCKED, EXPIRED, MASKED
    resolution_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.status != "PENDING":
            return False
        return (time.time() - self.created_at) >= self.quarantine_timer_sec

    @property
    def remaining_seconds(self) -> float:
        remaining = self.quarantine_timer_sec - (time.time() - self.created_at)
        return max(0.0, remaining)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interceptId": self.intercept_id,
            "agentId": self.agent_id,
            "actionType": self.action_type.value if isinstance(self.action_type, ActionType) else str(self.action_type),
            "riskLevel": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else str(self.risk_level),
            "target": self.target,
            "description": self.description,
            "contentPreview": self.content_preview,
            "createdAt": self.created_at,
            "quarantineTimerSec": self.quarantine_timer_sec,
            "remainingSeconds": round(self.remaining_seconds, 1),
            "status": self.status,
            "resolutionReason": self.resolution_reason,
            "metadata": self.metadata,
        }


class ActionGuard:
    """
    Universal Security & Mutation Interceptor.
    Protects both host system integrity (dev shield) and external platforms (frontier assistants).
    """

    # Actions considered external mutations
    MUTATION_ACTIONS = {
        ActionType.PUBLISH_POST,
        ActionType.SEND_MESSAGE,
        ActionType.GIT_PUSH,
        ActionType.TRIGGER_WEBHOOK,
        ActionType.EXECUTE_TRANSACTION,
        ActionType.EXTERNAL_API_CALL,
    }

    def __init__(
        self,
        workspace_path: str = ".",
        default_tier: AutonomyTier = AutonomyTier.TIER_2_BALANCED,
    ):
        self.workspace_path = workspace_path
        self.autonomy_tier = default_tier
        self.path_guard = PathGuard(workspace_path)
        self.command_guard = CommandGuard()
        self.secret_redactor = SecretRedactor()
        self.rate_guard = ExecutionRateGuard()
        self.active_intercepts: Dict[str, InterceptRecord] = {}

    def set_autonomy_tier(self, tier: AutonomyTier) -> None:
        """Dynamically update the active autonomy tier."""
        self.autonomy_tier = tier
        logger.info(f"ActionGuard autonomy tier set to: {tier.name}")

    def sanitize_output(self, text: str) -> str:
        """Redact secrets and tokens from text streams."""
        return self.secret_redactor.redact(text)

    def validate_file_access(self, target_path: str) -> Path:
        """Validate filesystem read/write boundary."""
        return self.path_guard.validate_path(target_path)

    def validate_command(self, cmd: str) -> Tuple[bool, Optional[str]]:
        """Validate shell command against blacklists."""
        return self.command_guard.validate_command(cmd)

    def evaluate_mutation(
        self,
        agent_id: str,
        payload: MutationPayload,
    ) -> Dict[str, Any]:
        """
        Evaluates an external mutation request against the active Autonomy Tier.
        Returns evaluation result dictionary.
        """
        action_type = payload.action_type
        risk = payload.risk_level

        # Tier 3 (High-Velocity / Autonomous):
        # Auto-approves INFO, LOW, and MEDIUM risk actions.
        # Only HIGH and CRITICAL require quarantine.
        if self.autonomy_tier == AutonomyTier.TIER_3_AUTONOMOUS:
            if risk in (RiskLevel.INFO, RiskLevel.LOW, RiskLevel.MEDIUM):
                return {
                    "status": "ALLOWED",
                    "requires_approval": False,
                    "reason": "Auto-approved by Autonomy Tier 3 policy.",
                }

        # Tier 2 (Balanced):
        # Auto-approves INFO and LOW risk reads/safe actions.
        # Quarantines MEDIUM, HIGH, and CRITICAL mutations with a timer.
        elif self.autonomy_tier == AutonomyTier.TIER_2_BALANCED:
            if risk in (RiskLevel.INFO, RiskLevel.LOW) and action_type not in (
                ActionType.PUBLISH_POST,
                ActionType.EXECUTE_TRANSACTION,
                ActionType.GIT_PUSH,
            ):
                return {
                    "status": "ALLOWED",
                    "requires_approval": False,
                    "reason": "Auto-approved low-risk action under Tier 2.",
                }

        # Tier 1 (Guarded):
        # Zero mutations permitted without explicit human verification.
        # Everything non-INFO requires approval.

        # Trigger Quarantine & Intercept
        intercept_id = f"int_{int(time.time() * 1000) % 1000000}"
        quarantine_sec = payload.quarantine_timer_sec
        if self.autonomy_tier == AutonomyTier.TIER_1_GUARDED:
            quarantine_sec = max(quarantine_sec, 45)

        record = InterceptRecord(
            intercept_id=intercept_id,
            agent_id=agent_id,
            action_type=action_type,
            risk_level=risk,
            target=payload.target,
            description=payload.description,
            content_preview=self.sanitize_output(payload.content_preview),
            quarantine_timer_sec=quarantine_sec,
            metadata=payload.metadata,
        )
        self.active_intercepts[intercept_id] = record

        logger.warning(
            f"🚨 ActionGuard Intercept [{intercept_id}]: {agent_id} requested {action_type.value} "
            f"on {payload.target} (Risk: {risk.value}, Tier: {self.autonomy_tier.value})"
        )

        return {
            "status": "QUARANTINED",
            "requires_approval": True,
            "intercept_id": intercept_id,
            "quarantine_timer_sec": quarantine_sec,
            "reason": f"Action {action_type.value} on '{payload.target}' requires human approval under Tier {self.autonomy_tier.value}.",
            "record": record.to_dict(),
        }

    def resolve_intercept(
        self,
        intercept_id: str,
        decision: str,  # "APPROVE", "BLOCK", "MASK"
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve, block, or mask a quarantined intercept."""
        if intercept_id not in self.active_intercepts:
            raise KeyError(f"Intercept ID '{intercept_id}' not found.")

        record = self.active_intercepts[intercept_id]

        if record.is_expired:
            record.status = "EXPIRED"
            record.resolution_reason = "Quarantine countdown expired; automatically blocked."
            return {"status": "BLOCKED", "reason": record.resolution_reason, "record": record.to_dict()}

        decision_upper = decision.upper()
        if decision_upper == "APPROVE":
            record.status = "APPROVED"
            record.resolution_reason = reason or "Explicitly approved by user."
            return {"status": "ALLOWED", "record": record.to_dict()}

        elif decision_upper == "MASK":
            record.status = "MASKED"
            record.content_preview = self.sanitize_output(record.content_preview)
            record.resolution_reason = reason or "Credentials masked before execution."
            return {"status": "MASKED", "record": record.to_dict()}

        else:
            record.status = "BLOCKED"
            record.resolution_reason = reason or "Blocked by user."
            return {"status": "BLOCKED", "record": record.to_dict()}

    def prune_expired(self) -> List[InterceptRecord]:
        """Auto-blocks and cleans up expired intercepts."""
        expired = []
        for record in list(self.active_intercepts.values()):
            if record.is_expired and record.status == "PENDING":
                record.status = "EXPIRED"
                record.resolution_reason = "Quarantine countdown expired; auto-blocked."
                expired.append(record)
        return expired

    def get_pending_intercepts(self) -> List[Dict[str, Any]]:
        """Return list of unexpired, pending intercepts."""
        self.prune_expired()
        return [
            rec.to_dict()
            for rec in self.active_intercepts.values()
            if rec.status == "PENDING"
        ]
