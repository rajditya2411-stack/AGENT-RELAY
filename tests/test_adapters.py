"""
Unit Tests for AgentRelay v2.0 Frontier Agent Connectors (Phase 2)
Tests GrokAdapter, DotsAdapter, and MuseAdapter lifecycle, event streaming,
and ActionGuard mutation interception.
"""

import asyncio
import tempfile
import unittest

from agentrelay.adapters.dots_adapter import DotsAdapter
from agentrelay.adapters.grok_adapter import GrokAdapter
from agentrelay.adapters.muse_adapter import MuseAdapter
from agentrelay.core.event_bus import EventBus
from agentrelay.core.events import (
    ActionType,
    AgentEvent,
    AutonomyTier,
    EventType,
    RiskLevel,
    SourceMode,
)
from agentrelay.guardrails.action_guard import ActionGuard


class TestFrontierAdapters(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.guard = ActionGuard(default_tier=AutonomyTier.TIER_2_BALANCED)

    def test_grok_adapter_lifecycle_and_pulse(self):
        async def _run():
            grok = GrokAdapter(
                event_bus=self.bus,
                action_guard=self.guard,
                mock_mode=True,
            )
            events = []
            self.bus.subscribe(lambda e: events.append(e))

            # Start adapter
            self.assertFalse(grok.is_running)
            await grok.start()
            self.assertTrue(grok.is_running)

            status = grok.get_status()
            self.assertEqual(status["agentId"], "grokbot")
            self.assertEqual(status["sourceMode"], "FRONTIER_AGENT")
            self.assertTrue(status["isRunning"])

            # Search pulse
            pulse = await grok.search_pulse("AgentRelay Security")
            self.assertTrue(pulse["mock"])
            self.assertIn("trending_topics", pulse)
            self.assertGreater(pulse["velocity_per_min"], 0)

            # Send instruction
            inst_res = await grok.send_instruction("Pulse check on autonomous AI safety")
            self.assertEqual(inst_res["status"], "SUCCESS")
            self.assertIn("searchPulse", inst_res)

            # Stop adapter
            await grok.stop()
            self.assertFalse(grok.is_running)

            # Verify event emission: STATUS_UPDATE, TOOL_START, THOUGHT, TOOL_COMPLETE
            event_types = [e.event_type for e in events]
            self.assertIn(EventType.STATUS_UPDATE, event_types)
            self.assertIn(EventType.TOOL_START, event_types)
            self.assertIn(EventType.THOUGHT, event_types)
            self.assertIn(EventType.TOOL_COMPLETE, event_types)

        asyncio.run(_run())

    def test_grok_mutation_interception_and_approval(self):
        async def _run():
            grok = GrokAdapter(
                event_bus=self.bus,
                action_guard=self.guard,
                mock_mode=True,
            )
            intercept_events = []
            self.bus.subscribe(
                lambda e: intercept_events.append(e),
                filter_event_type=EventType.INTERCEPT_REQUIRED,
            )

            await grok.start()

            # Attempt to publish tweet under Tier 2 (should be quarantined)
            res = await grok.publish_post(
                content="AgentRelay v2.0 is live with frontier agent shields!",
                target_handle="@agentrelay",
                risk_level=RiskLevel.HIGH,
                quarantine_timer_sec=30,
            )

            self.assertEqual(res["status"], "QUARANTINED")
            self.assertTrue(res["requires_approval"])
            intercept_id = res["intercept_id"]
            self.assertTrue(intercept_id.startswith("int_"))

            # Verify INTERCEPT_REQUIRED event was emitted
            self.assertEqual(len(intercept_events), 1)
            self.assertEqual(intercept_events[0].payload["actionType"], "PUBLISH_POST")
            self.assertEqual(intercept_events[0].payload["target"], "twitter/@agentrelay")

            # Resolve intercept via user APPROVAL
            resolution = self.guard.resolve_intercept(intercept_id, "APPROVE")
            self.assertEqual(resolution["status"], "ALLOWED")

            # Execute approved mutation
            exec_res = await grok.execute_approved_mutation(intercept_id)
            self.assertEqual(exec_res["status"], "PUBLISHED")
            self.assertEqual(len(grok.published_posts), 1)
            self.assertEqual(grok.published_posts[0]["postId"], exec_res["postId"])

            await grok.stop()

        asyncio.run(_run())

    def test_dots_adapter_reasoning_and_inspection(self):
        async def _run():
            dots = DotsAdapter(
                event_bus=self.bus,
                action_guard=self.guard,
                mock_mode=True,
            )
            thought_events = []
            self.bus.subscribe(
                lambda e: thought_events.append(e),
                filter_event_type=EventType.THOUGHT,
            )

            await dots.start()

            # Tree-of-thought streaming
            tree = await dots.stream_reasoning_tree(
                problem="Design zero-trust mutation gateway for autonomous agents",
                branching_factor=3,
            )
            self.assertEqual(len(tree["branches"]), 3)
            self.assertTrue(len(thought_events) >= 3)
            self.assertIn("optimal_branch", tree)

            # Repo architectural inspection
            report = await dots.inspect_repository(repo_path=".")
            self.assertGreater(report["totalFiles"], 0)
            self.assertIn("Core OS Kernel (Events & Pub/Sub)", report["layersIdentified"])
            self.assertIn("Security & Mutation Perimeter (ActionGuard)", report["layersIdentified"])

            # Send instruction
            inst_res = await dots.send_instruction("Inspect the repo architecture")
            self.assertEqual(inst_res["status"], "SUCCESS")
            self.assertIn("report", inst_res)

            await dots.stop()

        asyncio.run(_run())

    def test_muse_adapter_webhook_and_quarantine(self):
        async def _run():
            muse = MuseAdapter(
                event_bus=self.bus,
                action_guard=self.guard,
                mock_mode=True,
            )
            intercept_events = []
            self.bus.subscribe(
                lambda e: intercept_events.append(e),
                filter_event_type=EventType.INTERCEPT_REQUIRED,
            )

            await muse.start()

            # Inbound webhook ingestion
            webhook_payload = {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {
                                            "id": "wam_001",
                                            "from": "+14155552671",
                                            "text": {"body": "Inquiring about personal agent relay setup"},
                                            "timestamp": 1728000000,
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
            webhook_res = await muse.handle_webhook_payload(webhook_payload)
            self.assertEqual(webhook_res["status"], "PROCESSED")
            self.assertEqual(webhook_res["count"], 1)
            self.assertEqual(len(muse.inbound_messages), 1)

            # Outreach drafting
            draft_res = await muse.draft_outreach(
                recipient="+14155552671",
                topic="AgentRelay v2.0 Enterprise Onboarding",
            )
            self.assertIn("draft", draft_res)

            # Outbound WhatsApp message (should trigger ActionGuard quarantine)
            send_res = await muse.send_message(
                recipient="+14155552671",
                message=draft_res["draft"],
                risk_level=RiskLevel.HIGH,
            )
            self.assertEqual(send_res["status"], "QUARANTINED")
            self.assertTrue(send_res["requires_approval"])
            intercept_id = send_res["intercept_id"]

            self.assertEqual(len(intercept_events), 1)
            self.assertEqual(intercept_events[0].payload["actionType"], "SEND_MESSAGE")

            # Resolve intercept (APPROVE) and execute
            self.guard.resolve_intercept(intercept_id, "APPROVE")
            exec_res = await muse.execute_approved_mutation(intercept_id)
            self.assertEqual(exec_res["status"], "SENT")
            self.assertEqual(len(muse.sent_messages), 1)

            await muse.stop()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
