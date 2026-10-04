"""
Unit Tests for EventBus and Normalized AgentEvents (v2.0 Phase 1)
"""

import asyncio
import unittest

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


class TestEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus(history_limit=20)

    def test_event_serialization_roundtrip(self):
        event = AgentEvent(
            source_mode=SourceMode.FRONTIER_AGENT,
            agent_id="grokbot",
            event_type=EventType.INTERCEPT_REQUIRED,
            autonomy_tier=AutonomyTier.TIER_2_BALANCED,
            payload={
                "actionType": "PUBLISH_POST",
                "target": "twitter/@handle",
                "riskLevel": "HIGH",
            },
        )

        d = event.to_dict()
        self.assertEqual(d["sourceMode"], "FRONTIER_AGENT")
        self.assertEqual(d["agentId"], "grokbot")
        self.assertEqual(d["autonomyTier"], 2)

        reconstructed = AgentEvent.from_dict(d)
        self.assertEqual(reconstructed.source_mode, SourceMode.FRONTIER_AGENT)
        self.assertEqual(reconstructed.agent_id, "grokbot")
        self.assertEqual(reconstructed.event_type, EventType.INTERCEPT_REQUIRED)
        self.assertEqual(reconstructed.autonomy_tier, AutonomyTier.TIER_2_BALANCED)

    def test_async_publish_and_subscribe(self):
        async def _test():
            received_events = []

            async def on_event(evt: AgentEvent):
                received_events.append(evt)

            sub_id = self.bus.subscribe(on_event)
            self.assertTrue(sub_id.startswith("sub_"))

            test_event = AgentEvent(
                source_mode=SourceMode.DEV_SHIELD,
                agent_id="claude_code",
                event_type=EventType.THOUGHT,
                autonomy_tier=AutonomyTier.TIER_1_GUARDED,
                payload={"thought": "Inspecting package.json"},
            )

            await self.bus.publish(test_event)
            self.assertEqual(len(received_events), 1)
            self.assertEqual(received_events[0].payload["thought"], "Inspecting package.json")

            # Check history
            history = self.bus.get_history()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].agent_id, "claude_code")

            # Unsubscribe
            self.assertTrue(self.bus.unsubscribe(sub_id))
            await self.bus.publish(test_event)
            self.assertEqual(len(received_events), 1)  # No new event received

        asyncio.run(_test())

    def test_subscription_filters(self):
        async def _test():
            frontier_events = []
            dev_events = []

            self.bus.subscribe(
                lambda e: frontier_events.append(e),
                filter_mode=SourceMode.FRONTIER_AGENT,
            )
            self.bus.subscribe(
                lambda e: dev_events.append(e),
                filter_mode=SourceMode.DEV_SHIELD,
            )

            evt1 = AgentEvent(
                source_mode=SourceMode.FRONTIER_AGENT,
                agent_id="muse",
                event_type=EventType.STATUS_UPDATE,
                autonomy_tier=AutonomyTier.TIER_2_BALANCED,
                payload={"status": "Online"},
            )
            evt2 = AgentEvent(
                source_mode=SourceMode.DEV_SHIELD,
                agent_id="antigravity",
                event_type=EventType.STATUS_UPDATE,
                autonomy_tier=AutonomyTier.TIER_2_BALANCED,
                payload={"status": "Online"},
            )

            await self.bus.publish(evt1)
            await self.bus.publish(evt2)

            self.assertEqual(len(frontier_events), 1)
            self.assertEqual(frontier_events[0].agent_id, "muse")

            self.assertEqual(len(dev_events), 1)
            self.assertEqual(dev_events[0].agent_id, "antigravity")

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
