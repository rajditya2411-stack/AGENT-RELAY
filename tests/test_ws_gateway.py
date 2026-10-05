"""
Unit Tests for Dual-Mode WebSocket Gateway Multiplexer (Phase 4)
Tests /ws/live connection, handshake, dynamic mode subscription, and cross-mode alert broadcasts.
"""

import json
import unittest
from fastapi.testclient import TestClient

from agentrelay.core.events import (
    ActionType,
    AgentEvent,
    AutonomyTier,
    EventType,
    MutationPayload,
    RiskLevel,
    SourceMode,
)
from agentrelay.server.app import create_app
from agentrelay.server.context import ServerContext


class TestWebSocketGateway(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = TestClient(cls.app)
        cls.ctx = ServerContext.get_instance()

    def test_ws_handshake_and_init(self):
        with self.client.websocket_connect("/ws/live?mode=DEV_SHIELD") as ws:
            data = ws.receive_json()
            self.assertEqual(data["type"], "init")
            self.assertEqual(data["activeMode"], "DEV_SHIELD")
            self.assertIn("autonomyTier", data)
            self.assertIn("agents", data)

    def test_ws_ping_pong(self):
        with self.client.websocket_connect("/ws/live") as ws:
            init_data = ws.receive_json()
            self.assertEqual(init_data["type"], "init")

            ws.send_json({"type": "ping", "timestamp": 123456})
            pong = ws.receive_json()
            self.assertEqual(pong["type"], "pong")
            self.assertEqual(pong["timestamp"], 123456)

    def test_ws_mode_switch_subscription(self):
        with self.client.websocket_connect("/ws/live?mode=DEV_SHIELD") as ws:
            ws.receive_json()  # Consume init

            # Switch mode to FRONTIER_AGENT via toggle
            ws.send_json({"type": "subscribe", "mode": "FRONTIER_AGENT"})
            ack = ws.receive_json()
            self.assertEqual(ack["type"], "subscription_updated")
            self.assertEqual(ack["mode"], "FRONTIER_AGENT")

    def test_ws_prompt_dispatch(self):
        with self.client.websocket_connect("/ws/live?mode=FRONTIER_AGENT") as ws:
            ws.receive_json()  # init

            ws.send_json({
                "type": "prompt",
                "agentId": "dots",
                "instruction": "Explain event bus architecture",
            })
            msg = ws.receive_json()
            if "type" in msg:
                self.assertEqual(msg["type"], "prompt_acknowledged")
            else:
                self.assertIn("eventType", msg)
                self.assertEqual(msg["agentId"], "dots")

    def test_ws_cross_mode_priority_alert_broadcast(self):
        """
        Verify that an INTERCEPT_REQUIRED event is broadcast immediately to a client
        even if the client is subscribed exclusively to DEV_SHIELD mode!
        """
        with self.client.websocket_connect("/ws/live?mode=DEV_SHIELD") as ws:
            ws.receive_json()  # init

            # Dispatch prompt to grokbot asking for a tweet
            ws.send_json({
                "type": "prompt",
                "agentId": "grokbot",
                "instruction": "Draft release tweet for cross-mode alert",
            })
            ack = ws.receive_json()
            self.assertEqual(ack["type"], "prompt_acknowledged")

            # Client in DEV_SHIELD mode should receive the INTERCEPT_REQUIRED alert
            received = ws.receive_json()
            self.assertEqual(received["eventType"], "INTERCEPT_REQUIRED")
            self.assertEqual(received["payload"]["actionType"], "PUBLISH_POST")
            self.assertIn("agentrelay", received["payload"]["target"].lower())


if __name__ == "__main__":
    unittest.main()
