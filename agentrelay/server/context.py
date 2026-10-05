"""
AgentRelay v2.0 — Server Context & Shared Kernel Singletons
Manages the shared instances of EventBus, ActionGuard, Vault, AuditLogger, and Agent Adapters.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

from agentrelay.adapters.base_adapter import BaseAdapter
from agentrelay.adapters.dots_adapter import DotsAdapter
from agentrelay.adapters.grok_adapter import GrokAdapter
from agentrelay.adapters.muse_adapter import MuseAdapter
from agentrelay.core.event_bus import EventBus
from agentrelay.core.events import (
    ActionType,
    AgentEvent,
    AutonomyTier,
    EventType,
    SourceMode,
)
from agentrelay.guardrails.action_guard import ActionGuard
from agentrelay.server.audit_logger import AuditLogger
from agentrelay.server.vault import Vault

logger = logging.getLogger("ServerContext")


class ServerContext:
    """Central singleton managing all running system state for AgentRelay v2.0."""

    _instance: Optional["ServerContext"] = None

    def __init__(self, workspace_path: str = ".", vault_passphrase: str = "agentrelay_master_passphrase"):
        self.workspace_path = workspace_path
        self.event_bus = EventBus(history_limit=1000)
        self.action_guard = ActionGuard(workspace_path=workspace_path, default_tier=AutonomyTier.TIER_2_BALANCED)
        self.vault = Vault(passphrase=vault_passphrase)
        self.audit_logger = AuditLogger()

        # Connected WebSocket clients with their subscribed mode ("ALL", "DEV_SHIELD", "FRONTIER_AGENT")
        self.connected_clients: Dict[WebSocket, str] = {}
        self.client_lock = asyncio.Lock()

        # Frontier Adapters Registry
        self.adapters: Dict[str, BaseAdapter] = {}
        self._init_adapters()

        # Connect EventBus to AuditLogger and WebSocket broadcaster
        self.event_bus.subscribe(self._on_bus_event)

    def _init_adapters(self) -> None:
        """Initialize built-in Frontier Agent adapters in mock/BYOK mode."""
        self.adapters["dots"] = DotsAdapter(
            agent_id="dots",
            event_bus=self.event_bus,
            action_guard=self.action_guard,
            api_key=self.vault.get_key("openai"),
            mock_mode=True if not self.vault.get_key("openai") else False,
        )
        self.adapters["grokbot"] = GrokAdapter(
            agent_id="grokbot",
            event_bus=self.event_bus,
            action_guard=self.action_guard,
            api_key=self.vault.get_key("xai"),
            mock_mode=True if not self.vault.get_key("xai") else False,
        )
        self.adapters["muse"] = MuseAdapter(
            agent_id="muse",
            event_bus=self.event_bus,
            action_guard=self.action_guard,
            access_token=self.vault.get_key("meta_graph"),
            mock_mode=True if not self.vault.get_key("meta_graph") else False,
        )

    async def _on_bus_event(self, event: AgentEvent) -> None:
        """Internal handler whenever an event passes through EventBus."""
        # Record intercepts to audit log
        if event.event_type == EventType.INTERCEPT_REQUIRED:
            self.audit_logger.record(
                agent_id=event.agent_id,
                action_type=event.payload.get("actionType", "EXTERNAL_MUTATION"),
                target=event.payload.get("target", "unknown"),
                payload=event.payload,
                status="QUARANTINED",
                severity=event.payload.get("riskLevel", "HIGH"),
                metadata={"interceptId": event.payload.get("interceptId")},
            )

        # Broadcast to WebSocket clients
        await self.broadcast_event(event)

    async def register_client(self, websocket: WebSocket, initial_mode: str = "ALL") -> None:
        """Register a connected WebSocket client."""
        async with self.client_lock:
            self.connected_clients[websocket] = initial_mode
        logger.info(f"WebSocket client registered with mode: {initial_mode} (total: {len(self.connected_clients)})")

    async def unregister_client(self, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket client."""
        async with self.client_lock:
            if websocket in self.connected_clients:
                del self.connected_clients[websocket]
        logger.info(f"WebSocket client unregistered (remaining: {len(self.connected_clients)})")

    def update_client_mode(self, websocket: WebSocket, mode: str) -> None:
        """Update client's view subscription filter."""
        if websocket in self.connected_clients:
            self.connected_clients[websocket] = mode.upper()

    async def broadcast_event(self, event: AgentEvent) -> None:
        """
        Broadcast an event to connected WebSocket clients.
        INTERCEPT_REQUIRED events are broadcast to ALL clients regardless of mode (Cross-Mode Alert).
        Other events are filtered by client's active mode.
        """
        is_high_priority_intercept = (event.event_type == EventType.INTERCEPT_REQUIRED)
        event_dict = event.to_dict()

        disconnected = []
        for ws, sub_mode in list(self.connected_clients.items()):
            # Intercepts bypass filters!
            if not is_high_priority_intercept:
                if sub_mode != "ALL":
                    if sub_mode == "DEV_SHIELD" and event.source_mode != SourceMode.DEV_SHIELD:
                        continue
                    if sub_mode == "FRONTIER_AGENT" and event.source_mode != SourceMode.FRONTIER_AGENT:
                        continue

            try:
                res = ws.send_json(event_dict)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                disconnected.append(ws)

        if disconnected:
            async with self.client_lock:
                for ws in disconnected:
                    if ws in self.connected_clients:
                        del self.connected_clients[ws]

    @classmethod
    def get_instance(cls) -> "ServerContext":
        if cls._instance is None:
            cls._instance = ServerContext()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
