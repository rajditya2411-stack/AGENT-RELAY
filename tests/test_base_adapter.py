"""
Unit Tests for BaseAdapter Lifecycle and Mutation Handling (v2.0 Phase 1)
"""

import asyncio
from typing import Any, Dict, Optional
import unittest

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


class MockAgentAdapter(BaseAdapter):
    """Concrete mock adapter for testing lifecycle and event routing."""

    def __init__(self, agent_id: str, mode: SourceMode, bus: EventBus, guard: ActionGuard):
        super().__init__(agent_id=agent_id, source_mode=mode, event_bus=bus, action_guard=guard)
        self.instructions_received = []

    async def start(self) -> None:
        self.is_running = True
        await self.emit_event(EventType.STATUS_UPDATE, {"status": "INITIALIZED"})

    async def stop(self) -> None:
        self.is_running = False
        await self.emit_event(EventType.STATUS_UPDATE, {"status": "TERMINATED"})

    async def send_instruction(self, instruction: str, context: Optional[Dict[str, Any]] = None) -> Any:
        self.instructions_received.append(instruction)
        await self.emit_event(EventType.THOUGHT, {"thought": f"Processing instruction: {instruction}"})
        return {"status": "SUCCESS", "instruction": instruction}


class TestBaseAdapter(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.guard = ActionGuard(default_tier=AutonomyTier.TIER_2_BALANCED)
        self.adapter = MockAgentAdapter("mock_grok", SourceMode.FRONTIER_AGENT, self.bus, self.guard)

    def test_adapter_lifecycle(self):
        async def _test():
            events = []
            self.bus.subscribe(lambda e: events.append(e))

            self.assertFalse(self.adapter.is_running)
            await self.adapter.start()
            self.assertTrue(self.adapter.is_running)

            await self.adapter.send_instruction("Scan trending tech on X")
            self.assertEqual(len(self.adapter.instructions_received), 1)

            await self.adapter.stop()
            self.assertFalse(self.adapter.is_running)

            self.assertEqual(len(events), 3)
            self.assertEqual(events[0].event_type, EventType.STATUS_UPDATE)
            self.assertEqual(events[1].event_type, EventType.THOUGHT)
            self.assertEqual(events[2].event_type, EventType.STATUS_UPDATE)

        asyncio.run(_test())

    def test_adapter_mutation_interception(self):
        async def _test():
            intercept_events = []
            self.bus.subscribe(
                lambda e: intercept_events.append(e),
                filter_event_type=EventType.INTERCEPT_REQUIRED,
            )

            # Request high-risk post
            payload = MutationPayload(
                action_type=ActionType.PUBLISH_POST,
                target="twitter/@mock_post",
                description="Post live announcement",
                content_preview="We just launched!",
                risk_level=RiskLevel.HIGH,
                quarantine_timer_sec=30,
            )

            eval_res = await self.adapter.request_mutation(payload)
            self.assertEqual(eval_res["status"], "QUARANTINED")
            self.assertTrue(eval_res["requires_approval"])

            # Verify that INTERCEPT_REQUIRED event was published to EventBus
            self.assertEqual(len(intercept_events), 1)
            self.assertEqual(intercept_events[0].payload["actionType"], "PUBLISH_POST")
            self.assertEqual(intercept_events[0].payload["target"], "twitter/@mock_post")

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
