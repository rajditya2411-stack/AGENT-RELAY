"""
Unit Tests for ActionGuard & Universal Mutation Interception (v2.0 Phase 1)
"""

import time
import unittest
from pathlib import Path

from agentrelay.core.events import (
    ActionType,
    AutonomyTier,
    MutationPayload,
    RiskLevel,
)
from agentrelay.guardrails.action_guard import ActionGuard
from agentrelay.guardrails.path_guard import SecurityViolation


class TestActionGuard(unittest.TestCase):
    def setUp(self):
        self.workspace = str(Path(__file__).parent.parent.resolve())
        self.guard = ActionGuard(workspace_path=self.workspace, default_tier=AutonomyTier.TIER_2_BALANCED)

    def test_legacy_path_validation(self):
        # Normal safe file
        safe_path = self.guard.validate_file_access(str(Path(self.workspace) / "bridge.py"))
        self.assertTrue(safe_path.exists())

        # Traversal blocked
        with self.assertRaises(SecurityViolation):
            self.guard.validate_file_access(str(Path(self.workspace) / "../../../etc/passwd"))

        # Protected secret file blocked
        with self.assertRaises(SecurityViolation):
            self.guard.validate_file_access(str(Path(self.workspace) / ".env"))

    def test_legacy_command_validation(self):
        is_safe, _ = self.guard.validate_command("npm run build")
        self.assertTrue(is_safe)

        is_safe, reason = self.guard.validate_command("rm -rf /")
        self.assertFalse(is_safe)
        self.assertIn("blocked", reason.lower())

    def test_tier1_quarantine_all_mutations(self):
        self.guard.set_autonomy_tier(AutonomyTier.TIER_1_GUARDED)

        payload = MutationPayload(
            action_type=ActionType.PUBLISH_POST,
            target="twitter/@agentrelay",
            description="Announce release",
            content_preview="Launching AgentRelay v2.0!",
            risk_level=RiskLevel.MEDIUM,
            quarantine_timer_sec=30,
        )

        result = self.guard.evaluate_mutation("grokbot", payload)
        self.assertEqual(result["status"], "QUARANTINED")
        self.assertTrue(result["requires_approval"])
        # Tier 1 enforces at least 45s quarantine timer
        self.assertGreaterEqual(result["quarantine_timer_sec"], 45)

        intercept_id = result["intercept_id"]
        pending = self.guard.get_pending_intercepts()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["interceptId"], intercept_id)

    def test_tier2_balanced_eval(self):
        self.guard.set_autonomy_tier(AutonomyTier.TIER_2_BALANCED)

        # Low risk safe action (e.g. read / tool call)
        safe_payload = MutationPayload(
            action_type=ActionType.EXTERNAL_API_CALL,
            target="https://api.github.com/repos",
            description="Check repo stars",
            content_preview="GET /repos/agentrelay",
            risk_level=RiskLevel.LOW,
        )
        res_safe = self.guard.evaluate_mutation("dots", safe_payload)
        self.assertEqual(res_safe["status"], "ALLOWED")
        self.assertFalse(res_safe["requires_approval"])

        # High risk action (e.g. tweet or git push)
        high_risk_payload = MutationPayload(
            action_type=ActionType.PUBLISH_POST,
            target="twitter/@agentrelay",
            description="Tweet update",
            content_preview="Deploying to production",
            risk_level=RiskLevel.HIGH,
            quarantine_timer_sec=30,
        )
        res_high = self.guard.evaluate_mutation("grokbot", high_risk_payload)
        self.assertEqual(res_high["status"], "QUARANTINED")
        self.assertTrue(res_high["requires_approval"])

    def test_tier3_autonomous_eval(self):
        self.guard.set_autonomy_tier(AutonomyTier.TIER_3_AUTONOMOUS)

        # Medium risk action is auto-allowed in Tier 3
        med_payload = MutationPayload(
            action_type=ActionType.EXTERNAL_API_CALL,
            target="https://graph.facebook.com/v19.0",
            description="Query Graph API",
            content_preview="GET /insights",
            risk_level=RiskLevel.MEDIUM,
        )
        res_med = self.guard.evaluate_mutation("muse", med_payload)
        self.assertEqual(res_med["status"], "ALLOWED")
        self.assertFalse(res_med["requires_approval"])

        # Critical risk action is still quarantined
        crit_payload = MutationPayload(
            action_type=ActionType.EXECUTE_TRANSACTION,
            target="wallet/primary",
            description="Transfer funds",
            content_preview="Send 500 USD",
            risk_level=RiskLevel.CRITICAL,
        )
        res_crit = self.guard.evaluate_mutation("muse", crit_payload)
        self.assertEqual(res_crit["status"], "QUARANTINED")
        self.assertTrue(res_crit["requires_approval"])

    def test_resolve_intercept_approve_and_block(self):
        self.guard.set_autonomy_tier(AutonomyTier.TIER_1_GUARDED)

        payload = MutationPayload(
            action_type=ActionType.SEND_MESSAGE,
            target="whatsapp/+1234567890",
            description="Send quote to client",
            content_preview="Your project quote is $5,000",
            risk_level=RiskLevel.HIGH,
            quarantine_timer_sec=60,
        )

        res = self.guard.evaluate_mutation("muse", payload)
        int_id = res["intercept_id"]

        # User approves
        resolve_res = self.guard.resolve_intercept(int_id, "APPROVE", reason="User confirmed quote")
        self.assertEqual(resolve_res["status"], "ALLOWED")
        self.assertEqual(resolve_res["record"]["status"], "APPROVED")

        # Once resolved, pending list is empty
        self.assertEqual(len(self.guard.get_pending_intercepts()), 0)

    def test_resolve_intercept_mask_credentials(self):
        self.guard.set_autonomy_tier(AutonomyTier.TIER_1_GUARDED)

        payload = MutationPayload(
            action_type=ActionType.PUBLISH_POST,
            target="twitter/@leak",
            description="Leaked token in tweet",
            content_preview="Check our key AIzaSyD98fGhJkLmNoPqRsTuVwXyZ1234567890",
            risk_level=RiskLevel.HIGH,
            quarantine_timer_sec=60,
        )

        res = self.guard.evaluate_mutation("grokbot", payload)
        int_id = res["intercept_id"]

        # Verify initial preview has been sanitized
        self.assertIn("[REDACTED_GEMINI_KEY]", res["record"]["contentPreview"])

        # User chooses to MASK & PROCEED
        resolve_res = self.guard.resolve_intercept(int_id, "MASK", reason="Sanitize credentials before post")
        self.assertEqual(resolve_res["status"], "MASKED")
        self.assertIn("[REDACTED_GEMINI_KEY]", resolve_res["record"]["contentPreview"])


if __name__ == "__main__":
    unittest.main()
