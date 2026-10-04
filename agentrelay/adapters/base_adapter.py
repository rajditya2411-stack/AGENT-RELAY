"""
AgentRelay v2.0 — Base Agent Adapter
Abstract contract and lifecycle manager for Dev Coding and Frontier Assistant agent connectors.
"""

from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Any, Dict, Optional

from agentrelay.core.event_bus import EventBus
from agentrelay.core.events import (
    ActionType,
    AgentEvent,
    AutonomyTier,
    EventType,
    MutationPayload,
    RiskLevel,
    SourceMode,
)
from agentrelay.guardrails.action_guard import ActionGuard

logger = logging.getLogger("BaseAdapter")


class BaseAdapter(ABC):
    """
    Standard interface that all agents (terminal processes and API assistants) implement.
    Provides lifecycle methods, normalized event emission, and mutation interception hooks.
    """

    def __init__(
        self,
        agent_id: str,
        source_mode: SourceMode,
        event_bus: EventBus,
        action_guard: ActionGuard,
        name: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.source_mode = source_mode
        self.event_bus = event_bus
        self.action_guard = action_guard
        self.name = name or agent_id.replace("_", " ").title()
        self.is_running = False
        self._active_task: Optional[str] = None

    @abstractmethod
    async def start(self) -> None:
        """Initialize the agent, connection, or subshell process."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the agent connection or process."""
        pass

    @abstractmethod
    async def send_instruction(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Send a prompt or directive to the agent."""
        pass

    async def emit_event(
        self,
        event_type: EventType,
        payload: Dict[str, Any],
        autonomy_tier: Optional[AutonomyTier] = None,
    ) -> AgentEvent:
        """Emit a normalized AgentEvent to the central EventBus."""
        event = AgentEvent(
            source_mode=self.source_mode,
            agent_id=self.agent_id,
            event_type=event_type,
            autonomy_tier=autonomy_tier or self.action_guard.autonomy_tier,
            payload=payload,
        )
        await self.event_bus.publish(event)
        return event

    async def request_mutation(self, payload: MutationPayload) -> Dict[str, Any]:
        """
        Request permission to perform an external mutation (e.g. tweet, WhatsApp message, shell command).
        Routes through ActionGuard and emits INTERCEPT_REQUIRED if quarantined.
        """
        eval_result = self.action_guard.evaluate_mutation(self.agent_id, payload)

        if eval_result.get("requires_approval", False):
            # Emit high-priority intercept event
            await self.emit_event(
                event_type=EventType.INTERCEPT_REQUIRED,
                payload={
                    "interceptId": eval_result["intercept_id"],
                    "quarantineTimerSec": eval_result["quarantine_timer_sec"],
                    "actionType": payload.action_type.value,
                    "target": payload.target,
                    "description": payload.description,
                    "contentPreview": payload.content_preview,
                    "riskLevel": payload.risk_level.value,
                    "reason": eval_result.get("reason"),
                },
            )

        return eval_result

    def get_status(self) -> Dict[str, Any]:
        """Return standardized status dictionary."""
        return {
            "agentId": self.agent_id,
            "name": self.name,
            "sourceMode": self.source_mode.value,
            "isRunning": self.is_running,
            "activeTask": self._active_task,
            "autonomyTier": self.action_guard.autonomy_tier.value,
        }
