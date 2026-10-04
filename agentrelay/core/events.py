"""
AgentRelay v2.0 — Normalized AgentEvent Schema & Action Types
Defines the standard contract for all Dev Coding and Frontier Assistant events.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import time
from typing import Any, Dict, Optional
import uuid


class SourceMode(str, Enum):
    """Execution context mode."""
    DEV_SHIELD = "DEV_SHIELD"
    FRONTIER_AGENT = "FRONTIER_AGENT"


class AutonomyTier(int, Enum):
    """
    Tier 1 (Guarded): Zero external mutations allowed without manual mobile approval.
    Tier 2 (Balanced): Low/info risk mutations auto-approved; high/critical quarantined with timer.
    Tier 3 (Autonomous): High-velocity execution; only destructive root/system events blocked.
    """
    TIER_1_GUARDED = 1
    TIER_2_BALANCED = 2
    TIER_3_AUTONOMOUS = 3


class RiskLevel(str, Enum):
    """Risk classification for actions and events."""
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionType(str, Enum):
    """Action categories requested by agents."""
    # Dev Shield Actions
    RUN_COMMAND = "RUN_COMMAND"
    WRITE_FILE = "WRITE_FILE"
    READ_FILE = "READ_FILE"
    GIT_PUSH = "GIT_PUSH"

    # Frontier Agent Actions
    PUBLISH_POST = "PUBLISH_POST"
    SEND_MESSAGE = "SEND_MESSAGE"
    TRIGGER_WEBHOOK = "TRIGGER_WEBHOOK"
    EXECUTE_TRANSACTION = "EXECUTE_TRANSACTION"
    EXTERNAL_API_CALL = "EXTERNAL_API_CALL"


class EventType(str, Enum):
    """Event types emitted into the event bus."""
    THOUGHT = "THOUGHT"
    TOOL_START = "TOOL_START"
    TOOL_COMPLETE = "TOOL_COMPLETE"
    INTERCEPT_REQUIRED = "INTERCEPT_REQUIRED"
    INTERCEPT_RESOLVED = "INTERCEPT_RESOLVED"
    ERROR = "ERROR"
    STATUS_UPDATE = "STATUS_UPDATE"


@dataclass
class MutationPayload:
    """Detailed payload for an external action requiring verification."""
    action_type: ActionType
    target: str
    description: str
    content_preview: str
    risk_level: RiskLevel
    quarantine_timer_sec: int = 30
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actionType": self.action_type.value if isinstance(self.action_type, ActionType) else str(self.action_type),
            "target": self.target,
            "description": self.description,
            "contentPreview": self.content_preview,
            "riskLevel": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else str(self.risk_level),
            "quarantineTimerSec": self.quarantine_timer_sec,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MutationPayload":
        action_type = ActionType(data.get("actionType", data.get("action_type", "RUN_COMMAND")))
        risk_level = RiskLevel(data.get("riskLevel", data.get("risk_level", "LOW")))
        return cls(
            action_type=action_type,
            target=data.get("target", ""),
            description=data.get("description", ""),
            content_preview=data.get("contentPreview", data.get("content_preview", "")),
            risk_level=risk_level,
            quarantine_timer_sec=int(data.get("quarantineTimerSec", data.get("quarantine_timer_sec", 30))),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentEvent:
    """Normalized event contract emitted by all agents."""
    source_mode: SourceMode
    agent_id: str
    event_type: EventType
    autonomy_tier: AutonomyTier
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eventId": self.event_id,
            "timestamp": self.timestamp,
            "sourceMode": self.source_mode.value if isinstance(self.source_mode, SourceMode) else str(self.source_mode),
            "agentId": self.agent_id,
            "eventType": self.event_type.value if isinstance(self.event_type, EventType) else str(self.event_type),
            "autonomyTier": int(self.autonomy_tier.value if isinstance(self.autonomy_tier, AutonomyTier) else self.autonomy_tier),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentEvent":
        source_mode = SourceMode(data.get("sourceMode", data.get("source_mode", "DEV_SHIELD")))
        event_type = EventType(data.get("eventType", data.get("event_type", "STATUS_UPDATE")))
        tier_val = int(data.get("autonomyTier", data.get("autonomy_tier", 2)))
        autonomy_tier = AutonomyTier(tier_val)

        return cls(
            event_id=data.get("eventId", data.get("event_id", f"evt_{uuid.uuid4().hex[:8]}")),
            timestamp=float(data.get("timestamp", time.time())),
            source_mode=source_mode,
            agent_id=data.get("agentId", data.get("agent_id", "unknown")),
            event_type=event_type,
            autonomy_tier=autonomy_tier,
            payload=data.get("payload", {}),
        )
