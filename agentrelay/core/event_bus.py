"""
AgentRelay v2.0 — Asynchronous Event Bus
In-memory Pub/Sub broker dispatching normalized AgentEvents across agents, guardrails, and gateways.
"""

import asyncio
from collections import deque
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Union
import uuid

from agentrelay.core.events import AgentEvent, SourceMode, EventType

logger = logging.getLogger("AgentRelayEventBus")

SubscriberCallback = Callable[[AgentEvent], Union[None, Coroutine[Any, Any, None]]]


class EventBus:
    """Central asynchronous Pub/Sub broker for AgentEvents."""

    def __init__(self, history_limit: int = 500):
        self._subscribers: Dict[str, Dict[str, Any]] = {}
        self._history: deque[AgentEvent] = deque(maxlen=history_limit)
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        callback: SubscriberCallback,
        filter_mode: Optional[SourceMode] = None,
        filter_agent_id: Optional[str] = None,
        filter_event_type: Optional[EventType] = None,
    ) -> str:
        """Register a subscriber with optional filters. Returns subscription ID."""
        sub_id = f"sub_{uuid.uuid4().hex[:8]}"
        self._subscribers[sub_id] = {
            "callback": callback,
            "filter_mode": filter_mode,
            "filter_agent_id": filter_agent_id,
            "filter_event_type": filter_event_type,
        }
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """Remove a subscription."""
        if sub_id in self._subscribers:
            del self._subscribers[sub_id]
            return True
        return False

    async def publish(self, event: AgentEvent) -> None:
        """Publish an event to all matching subscribers."""
        async with self._lock:
            self._history.append(event)

        tasks = []
        for sub_id, sub in list(self._subscribers.items()):
            # Apply filters
            if sub["filter_mode"] and event.source_mode != sub["filter_mode"]:
                continue
            if sub["filter_agent_id"] and event.agent_id != sub["filter_agent_id"]:
                continue
            if sub["filter_event_type"] and event.event_type != sub["filter_event_type"]:
                continue

            cb = sub["callback"]
            try:
                if asyncio.iscoroutinefunction(cb):
                    tasks.append(asyncio.create_task(cb(event)))
                else:
                    cb(event)
            except Exception as e:
                logger.error(f"Error executing event bus subscriber {sub_id}: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_history(
        self,
        limit: int = 50,
        mode: Optional[SourceMode] = None,
        agent_id: Optional[str] = None,
    ) -> List[AgentEvent]:
        """Retrieve historical events matching criteria."""
        events = list(self._history)
        if mode:
            events = [e for e in events if e.source_mode == mode]
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]
        return events[-limit:]

    def clear(self) -> None:
        """Clear subscribers and history."""
        self._subscribers.clear()
        self._history.clear()
