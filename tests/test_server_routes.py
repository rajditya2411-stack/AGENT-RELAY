"""
Unit Tests for AgentRelay v2.0 Modular Routers (Phase 4)
Tests /api/v2/agents, /api/v2/guardrails, /api/v2/vault, /api/v2/audit, and /health.
"""

import unittest
from fastapi.testclient import TestClient

from agentrelay.server.app import create_app
from agentrelay.server.context import ServerContext


class TestServerRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = TestClient(cls.app)
        cls.ctx = ServerContext.get_instance()

    def test_health_endpoint(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["version"], "2.0.0")
        self.assertIn("dots", data["frontierAgents"])

    def test_agents_endpoints(self):
        # 1. List agents
        res = self.client.get("/api/v2/agents")
        self.assertEqual(res.status_code, 200)
        agents = res.json()
        agent_ids = [a["agentId"] for a in agents]
        self.assertIn("claude_code", agent_ids)
        self.assertIn("dots", agent_ids)
        self.assertIn("grokbot", agent_ids)
        self.assertIn("muse", agent_ids)

        # 2. Start agent
        res = self.client.post("/api/v2/agents/dots/start")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "SUCCESS")

        # 3. Instruct agent
        res = self.client.post(
            "/api/v2/agents/dots/instruct",
            json={"instruction": "Audit codebase modularity"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "SUCCESS")

        # 4. Get history
        res = self.client.get("/api/v2/agents/dots/history")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json()["count"], 1)

        # 5. Stop agent
        res = self.client.post("/api/v2/agents/dots/stop")
        self.assertEqual(res.status_code, 200)

    def test_guardrails_endpoints(self):
        # 1. Get tier
        res = self.client.get("/api/v2/guardrails/tier")
        self.assertEqual(res.status_code, 200)
        self.assertIn("tier", res.json())

        # 2. Update tier
        res = self.client.post("/api/v2/guardrails/tier", json={"tier": 1})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["tier"], 1)

        # Reset back to tier 2
        self.client.post("/api/v2/guardrails/tier", json={"tier": 2})

        # 3. Trigger a mutation that gets quarantined
        res_instruct = self.client.post(
            "/api/v2/agents/grokbot/instruct",
            json={"instruction": "Draft public release announcement tweet"},
        )
        self.assertEqual(res_instruct.status_code, 200)

        # 4. Check pending intercepts
        res_ints = self.client.get("/api/v2/guardrails/intercepts")
        self.assertEqual(res_ints.status_code, 200)
        intercepts = res_ints.json()
        self.assertGreaterEqual(len(intercepts), 1)

        int_id = intercepts[0]["interceptId"]

        # 5. Resolve intercept (APPROVE)
        res_resolve = self.client.post(
            f"/api/v2/guardrails/intercepts/{int_id}/resolve",
            json={"decision": "APPROVE", "reason": "Approved in unit test"},
        )
        self.assertEqual(res_resolve.status_code, 200)
        self.assertEqual(res_resolve.json()["status"], "ALLOWED")

        # 6. Policies summary
        res_policies = self.client.get("/api/v2/guardrails/policies")
        self.assertEqual(res_policies.status_code, 200)
        self.assertEqual(res_policies.json()["pathGuard"]["status"], "ACTIVE")

    def test_vault_endpoints(self):
        # 1. Status
        res = self.client.get("/api/v2/vault/status")
        self.assertEqual(res.status_code, 200)
        self.assertIn("isLocked", res.json())

        # 2. Store key
        res = self.client.post(
            "/api/v2/vault/keys",
            json={"provider": "openai", "key": "sk-proj-test1234567890abcdef12345678", "rotate": False},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("openai", res.json()["configuredProviders"])

        # 3. Rotate key
        res = self.client.post(
            "/api/v2/vault/keys",
            json={"provider": "openai", "key": "sk-proj-testROTATED1234567890abcdef", "rotate": True},
        )
        self.assertEqual(res.status_code, 200)

        # 4. Delete key
        res = self.client.delete("/api/v2/vault/keys/openai")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["cleared"])

    def test_audit_endpoints(self):
        # 1. Query entries
        res = self.client.get("/api/v2/audit/entries?limit=10")
        self.assertEqual(res.status_code, 200)
        entries = res.json()
        self.assertIsInstance(entries, list)

        # 2. Verify integrity
        res = self.client.get("/api/v2/audit/verify")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["chainIntact"])

        # 3. Stats
        res = self.client.get("/api/v2/audit/stats")
        self.assertEqual(res.status_code, 200)
        self.assertIn("totalEntries", res.json())

        # 4. Export compliance bundle
        res = self.client.get("/api/v2/audit/export")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("complianceBundleVersion", data)
        self.assertIn("signingAlgorithm", data)


if __name__ == "__main__":
    unittest.main()
