"""
Automated unit and integration test suite for AgentRelay Phase 1.
"""

import asyncio
import subprocess
import sys
import unittest

from bridge import AgentBridge, BridgeEvent, EventType, GitRecoveryManager, MockAgentAdapter, ProjectManager


class TestBridgeEvent(unittest.TestCase):
    def test_event_serialization(self):
        event = BridgeEvent(
            event_type=EventType.TOKEN,
            payload={"token": "hello"},
            timestamp=1700000000.0,
        )
        json_str = event.to_json()
        self.assertIn('"event_type": "token"', json_str)
        self.assertIn('"token": "hello"', json_str)
        self.assertIn('"timestamp": 1700000000.0', json_str)


class TestMockAgentAdapter(unittest.TestCase):
    def test_mock_streaming_lifecycle(self):
        async def _run():
            adapter = MockAgentAdapter()
            events = []
            async for event in adapter.execute_task("Refactor authentication"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        event_types = [e.event_type for e in events]

        # Verify event stream structure
        self.assertIn(EventType.STATUS, event_types)
        self.assertIn(EventType.THINKING, event_types)
        self.assertIn(EventType.TOOL_CALL, event_types)
        self.assertIn(EventType.TOKEN, event_types)
        self.assertIn(EventType.USAGE, event_types)
        self.assertIn(EventType.COMPLETED, event_types)

        # Verify usage metadata payload
        usage_event = next(e for e in events if e.event_type == EventType.USAGE)
        self.assertIn("prompt_token_count", usage_event.payload)
        self.assertIn("total_token_count", usage_event.payload)
        self.assertIn("cached_content_token_count", usage_event.payload)
        self.assertGreater(usage_event.payload["total_token_count"], 0)


class TestGitRecoveryManager(unittest.TestCase):
    def test_recovery_manager_methods(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=False)
            manager = GitRecoveryManager(workspace_path=tmpdir)
            audit_res = manager.auto_audit()
            self.assertTrue(audit_res["success"])
            self.assertIn("has_changes", audit_res)

            undo_res = manager.undo_changes()
            self.assertTrue(undo_res["success"])

            test_res = manager.run_unit_tests()
            self.assertIn("summary", test_res)

    def test_project_manager(self):
        pm = ProjectManager()
        projects = pm.list_projects()
        self.assertGreaterEqual(len(projects), 4)
        project_ids = [p["id"] for p in projects]
        self.assertIn("agent-relay", project_ids)
        self.assertIn("mindmap", project_ids)


class TestAgentBridgeIntegration(unittest.TestCase):
    def test_bridge_run_prompt(self):
        async def _run():
            bridge = AgentBridge(use_mock=True)
            tokens_received = []
            async for event in bridge.run_prompt("Build feature X"):
                if event.event_type == EventType.TOKEN:
                    tokens_received.append(event.payload.get("token"))
            return bridge.mode, tokens_received

        mode, tokens_received = asyncio.run(_run())
        self.assertEqual(mode, "MOCK")
        self.assertGreater(len(tokens_received), 0)
        full_text = "".join(tokens_received)
        self.assertIn("Hello from AgentRelay", full_text)


class TestMultiProviderAdapters(unittest.TestCase):
    def test_claude_adapter_fallback_execution(self):
        from bridge import ClaudeAgentAdapter
        adapter = ClaudeAgentAdapter(model_name="claude-3-7-sonnet")
        
        async def _run():
            events = []
            async for event in adapter.execute_task("Write unit test for parser"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        event_types = [e.event_type for e in events]
        self.assertIn(EventType.STATUS, event_types)
        self.assertIn(EventType.THINKING, event_types)
        self.assertIn(EventType.TOKEN, event_types)
        self.assertIn(EventType.COMPLETED, event_types)

    def test_codex_adapter_fallback_execution(self):
        from bridge import CodexAgentAdapter
        adapter = CodexAgentAdapter(model_name="gpt-4o")

        async def _run():
            events = []
            async for event in adapter.execute_task("Optimize SQL query"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        event_types = [e.event_type for e in events]
        self.assertIn(EventType.STATUS, event_types)
        self.assertIn(EventType.THINKING, event_types)
        self.assertIn(EventType.TOKEN, event_types)
        self.assertIn(EventType.COMPLETED, event_types)

    def test_provider_switching_in_bridge(self):
        bridge = AgentBridge(use_mock=True, provider="gemini")
        self.assertEqual(bridge.mode, "MOCK")

        mode = bridge.switch_provider("claude")
        self.assertIn("Claude Code", mode)
        self.assertEqual(bridge.provider, "claude")

        mode = bridge.switch_provider("codex")
        self.assertIn("Codex", mode)
        self.assertEqual(bridge.provider, "codex")

        mode = bridge.switch_provider("gemini")
        self.assertEqual(mode, "MOCK")
        self.assertEqual(bridge.provider, "gemini")


if __name__ == "__main__":
    unittest.main()

