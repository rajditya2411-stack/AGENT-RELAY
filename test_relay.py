"""
AgentRelay — Async Automated Integration Test Suite for Phase 2 & 3
"""

import asyncio
import json
import sys
import unittest

from relay_server import (
    app,
    DEVICE_SESSIONS,
    DeviceSession,
    bridge_websocket_endpoint,
    client_websocket_endpoint,
    serve_mobile_web_app,
    health_check,
    get_device_status,
)


class MockWebSocket:
    """In-memory mock WebSocket for clean, socket-free async testing."""

    def __init__(self):
        self.sent_json_list = []
        self.receive_queue = asyncio.Queue()
        self.is_closed = False

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent_json_list.append(data)

    async def receive_text(self):
        msg = await self.receive_queue.get()
        if msg is None:
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()
        return msg

    async def close(self, code=1000):
        self.is_closed = True


class TestRelayServer(unittest.TestCase):
    def setUp(self):
        DEVICE_SESSIONS.clear()

    def test_sync_device_session_event_buffering_and_replay(self):
        session = DeviceSession("device-replay-test", "secret")
        e1 = session.add_event({"event_type": "token", "payload": {"token": "A"}})
        e2 = session.add_event({"event_type": "token", "payload": {"token": "B"}})
        e3 = session.add_event({"event_type": "token", "payload": {"token": "C"}})

        self.assertEqual(e1["seq_id"], 1)
        self.assertEqual(e2["seq_id"], 2)
        self.assertEqual(e3["seq_id"], 3)

        missed = session.get_events_since(1)
        self.assertEqual(len(missed), 2)
        self.assertEqual(missed[0]["payload"]["token"], "B")
        self.assertEqual(missed[1]["payload"]["token"], "C")

    def test_all_async_relay_endpoints(self):
        async def _test():
            # 1. Test serve_mobile_web_app
            res = await serve_mobile_web_app()
            self.assertTrue(hasattr(res, "path"))
            with open(res.path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("AgentRelay", content)
            self.assertIn("Auto-Audit &amp; Resume", content)

            # 2. Test health_check
            data = await health_check()
            self.assertEqual(data["status"], "healthy")
            self.assertEqual(data["online_devices"], 0)

            # 3. Test get_device_status
            data_offline = await get_device_status("my-laptop")
            self.assertFalse(data_offline["is_online"])
            self.assertEqual(data_offline["status"], "DEVICE OFFLINE")

            # 4. Test WebSocket flow
            device_id = "test-ws-001"
            token = "secret123"

            bridge_ws = MockWebSocket()
            client_ws = MockWebSocket()

            bridge_task = asyncio.create_task(
                bridge_websocket_endpoint(bridge_ws, device_id, token)
            )
            await asyncio.sleep(0.05)

            session = DEVICE_SESSIONS[device_id]
            self.assertTrue(session.is_online)

            client_task = asyncio.create_task(
                client_websocket_endpoint(client_ws, device_id, token, last_seq_id=0)
            )
            await asyncio.sleep(0.05)

            self.assertEqual(client_ws.sent_json_list[0]["event_type"], "init")
            self.assertTrue(client_ws.sent_json_list[0]["payload"]["is_online"])

            # Client sends prompt
            await client_ws.receive_queue.put(json.dumps({"type": "prompt", "prompt": "Fix auth"}))
            await asyncio.sleep(0.05)

            self.assertEqual(len(bridge_ws.sent_json_list), 1)
            self.assertEqual(bridge_ws.sent_json_list[0]["prompt"], "Fix auth")

            # Bridge sends back stream events
            await bridge_ws.receive_queue.put(json.dumps({
                "event_type": "token",
                "payload": {"token": "Fixed!"}
            }))
            await asyncio.sleep(0.05)

            self.assertEqual(client_ws.sent_json_list[-1]["event_type"], "token")
            self.assertEqual(client_ws.sent_json_list[-1]["payload"]["token"], "Fixed!")

            # Cleanup
            await bridge_ws.receive_queue.put(None)
            await client_ws.receive_queue.put(None)
            await asyncio.gather(bridge_task, client_task, return_exceptions=True)

            self.assertFalse(session.is_online)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
