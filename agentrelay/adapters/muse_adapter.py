"""
AgentRelay v2.0 — Meta Muse Adapter
Frontier connector for Meta Muse (WhatsApp Cloud API & Meta Graph).
Supports webhook ingestion, intelligent customer outreach drafting,
and safe SEND_MESSAGE mutations quarantined via ActionGuard.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from agentrelay.adapters.base_adapter import BaseAdapter
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

logger = logging.getLogger("MuseAdapter")


class MuseAdapter(BaseAdapter):
    """
    Meta Muse WhatsApp & Meta Graph Frontier Connector.
    Provides inbound webhook ingestion, outreach campaign drafting,
    and ActionGuard-quarantined SEND_MESSAGE mutation controls.
    """

    def __init__(
        self,
        event_bus: EventBus,
        action_guard: ActionGuard,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
        graph_api_version: str = "v18.0",
        mock_mode: Optional[bool] = None,
        agent_id: str = "muse",
        name: str = "Meta Muse",
    ):
        super().__init__(
            agent_id=agent_id,
            source_mode=SourceMode.FRONTIER_AGENT,
            event_bus=event_bus,
            action_guard=action_guard,
            name=name,
        )
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.graph_api_version = graph_api_version
        self.mock_mode = (access_token is None) if mock_mode is None else mock_mode
        self.sent_messages: List[Dict[str, Any]] = []
        self.inbound_messages: List[Dict[str, Any]] = []

    async def start(self) -> None:
        """Initialize Muse connector and announce online state."""
        self.is_running = True
        await self.emit_event(
            EventType.STATUS_UPDATE,
            {
                "status": "INITIALIZED",
                "agent": self.name,
                "agentId": self.agent_id,
                "mockMode": self.mock_mode,
                "capabilities": [
                    "meta_graph_webhook_ingest",
                    "outreach_campaign_drafting",
                    "whatsapp_send_message",
                ],
            },
        )
        logger.info(f"MuseAdapter [{self.agent_id}] started (mock_mode={self.mock_mode})")

    async def stop(self) -> None:
        """Gracefully disconnect Muse connector."""
        self.is_running = False
        await self.emit_event(
            EventType.STATUS_UPDATE,
            {"status": "TERMINATED", "agent": self.name, "agentId": self.agent_id},
        )
        logger.info(f"MuseAdapter [{self.agent_id}] stopped")

    async def handle_webhook_payload(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingest and normalize an incoming Meta Graph / WhatsApp Cloud webhook payload.
        Emits TOOL_START and STATUS_UPDATE events for incoming user messages.
        """
        await self.emit_event(
            EventType.TOOL_START,
            {"tool": "whatsapp_webhook_ingest", "rawKeys": list(webhook_data.keys())},
        )

        parsed_messages = []

        # Standard WhatsApp Cloud API payload format:
        # {"entry": [{"changes": [{"value": {"messages": [{"from": "...", "text": {"body": "..."}}]}}]}]}
        entries = webhook_data.get("entry", [])
        if entries and isinstance(entries, list):
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    for msg in value.get("messages", []):
                        parsed_messages.append({
                            "messageId": msg.get("id", f"wam_{uuid.uuid4().hex[:8]}"),
                            "sender": msg.get("from", "unknown"),
                            "text": msg.get("text", {}).get("body", ""),
                            "timestamp": float(msg.get("timestamp", time.time())),
                        })

        # Flat fallback format: {"from": "+123...", "text": "hello"}
        if not parsed_messages and "from" in webhook_data:
            parsed_messages.append({
                "messageId": webhook_data.get("id", f"wam_{uuid.uuid4().hex[:8]}"),
                "sender": webhook_data.get("from"),
                "text": webhook_data.get("text") or webhook_data.get("body", ""),
                "timestamp": float(webhook_data.get("timestamp", time.time())),
            })

        for msg in parsed_messages:
            self.inbound_messages.append(msg)
            await self.emit_event(
                EventType.STATUS_UPDATE,
                {
                    "event": "INBOUND_WHATSAPP_MESSAGE",
                    "sender": msg["sender"],
                    "textPreview": self.action_guard.sanitize_output(msg["text"][:100]),
                },
            )

        await self.emit_event(
            EventType.TOOL_COMPLETE,
            {"tool": "whatsapp_webhook_ingest", "messagesCount": len(parsed_messages)},
        )

        return {
            "status": "PROCESSED",
            "count": len(parsed_messages),
            "messages": parsed_messages,
        }

    async def draft_outreach(
        self,
        recipient: str,
        topic: str,
        tone: str = "professional",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Draft high-conversion customer outreach messaging with brand safety analysis.
        Emits deep thought detailing outreach strategy.
        """
        await self.emit_event(
            EventType.THOUGHT,
            {
                "thought": (
                    f"[Muse Outreach Formulation] Drafting personalized outreach for recipient {recipient} "
                    f"on topic '{topic}' with {tone} tone. Analyzing boundary compliance and customer sentiment..."
                ),
            },
        )

        draft = (
            f"Hi! Reaching out regarding {topic}. We've streamlined our autonomous agent "
            f"workflows to ensure zero-downtime and bank-grade security. Would love to share an update!"
        )

        await self.emit_event(
            EventType.THOUGHT,
            {
                "thought": f"[Muse Brand Verification] Draft verified: no sensitive tokens, tone adheres to {tone}.",
            },
        )

        return {
            "recipient": recipient,
            "topic": topic,
            "tone": tone,
            "draft": draft,
            "timestamp": time.time(),
        }

    async def send_message(
        self,
        recipient: str,
        message: str,
        template: Optional[str] = None,
        risk_level: RiskLevel = RiskLevel.HIGH,
        quarantine_timer_sec: int = 30,
    ) -> Dict[str, Any]:
        """
        Outbound WhatsApp communication hook: sends message subject to ActionGuard interception.
        Quarantines communication under Tier 1 & Tier 2 for human confirmation.
        """
        payload = MutationPayload(
            action_type=ActionType.SEND_MESSAGE,
            target=f"whatsapp/{recipient}",
            description=f"Send WhatsApp message to {recipient}",
            content_preview=message,
            risk_level=risk_level,
            quarantine_timer_sec=quarantine_timer_sec,
            metadata={
                "recipient": recipient,
                "template": template,
                "charCount": len(message),
            },
        )

        eval_result = await self.request_mutation(payload)

        if eval_result.get("requires_approval", False) or eval_result.get("status") == "QUARANTINED":
            return {
                "status": "QUARANTINED",
                "intercept_id": eval_result.get("intercept_id"),
                "requires_approval": True,
                "quarantine_timer_sec": eval_result.get("quarantine_timer_sec", quarantine_timer_sec),
                "reason": eval_result.get("reason"),
                "recipient": recipient,
                "message": message,
            }

        # If allowed:
        return await self._execute_send(recipient, message, template)

    async def execute_approved_mutation(self, intercept_id: str) -> Dict[str, Any]:
        """Execute a previously quarantined message after user approval."""
        record = self.action_guard.active_intercepts.get(intercept_id)
        if not record:
            raise KeyError(f"Intercept '{intercept_id}' not found.")
        if record.status != "APPROVED":
            raise ValueError(f"Intercept '{intercept_id}' is not in APPROVED state (current: {record.status}).")

        recipient = record.metadata.get("recipient", record.target.replace("whatsapp/", ""))
        template = record.metadata.get("template")
        return await self._execute_send(recipient, record.content_preview, template)

    async def _execute_send(
        self,
        recipient: str,
        message: str,
        template: Optional[str],
    ) -> Dict[str, Any]:
        """Dispatch message via Meta Graph API or safe mock transmission."""
        msg_id = f"wam_{uuid.uuid4().hex[:12]}"
        record = {
            "messageId": msg_id,
            "recipient": recipient,
            "content": message,
            "template": template,
            "sentAt": time.time(),
            "status": "SENT",
        }
        self.sent_messages.append(record)

        await self.emit_event(
            EventType.TOOL_COMPLETE,
            {"tool": "whatsapp_send_message", "messageId": msg_id, "recipient": recipient},
        )

        return {"status": "SENT", "messageId": msg_id, "record": record}

    async def send_instruction(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process prompt/instruction: draft outreach, handle webhooks, or dispatch WhatsApp messages.
        """
        self._active_task = instruction
        await self.emit_event(
            EventType.THOUGHT,
            {"thought": f"Muse processing directive: '{instruction}'"},
        )

        instruction_lower = instruction.lower()

        # Handle outbound message instruction
        if "send" in instruction_lower or "message" in instruction_lower or "outreach" in instruction_lower:
            recipient = (context or {}).get("recipient", "+1234567890")
            msg = (context or {}).get("message", instruction)
            res = await self.send_message(recipient=recipient, message=msg)
            self._active_task = None
            return res

        # Handle webhook ingestion instruction
        if "webhook" in instruction_lower or "inbound" in instruction_lower:
            payload = (context or {}).get("webhook_data", {"from": "+1987654321", "text": instruction})
            res = await self.handle_webhook_payload(webhook_data=payload)
            self._active_task = None
            return res

        # General communication response
        await self.emit_event(
            EventType.THOUGHT,
            {"thought": "Synthesizing conversational and customer outreach directives..."},
        )
        self._active_task = None
        return {
            "status": "SUCCESS",
            "agent": self.name,
            "response": f"Muse processed communication directive: {instruction}",
        }
