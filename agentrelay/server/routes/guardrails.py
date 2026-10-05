"""
AgentRelay v2.0 — Guardrail Policies & ActionGuard Interceptor Router
Endpoints for real-time mobile approval, auto-block countdown management, and Autonomy Tier controls.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentrelay.core.events import AutonomyTier, EventType, SourceMode
from agentrelay.server.context import ServerContext

router = APIRouter(prefix="/api/v2/guardrails", tags=["Guardrails"])


class ResolveInterceptRequest(BaseModel):
    decision: str = Field(..., description="Decision: 'APPROVE', 'BLOCK', or 'MASK'")
    reason: Optional[str] = Field(default=None, description="Optional explanation or rationale")


class SetTierRequest(BaseModel):
    tier: int = Field(..., ge=1, le=3, description="Autonomy Tier: 1 (Guarded), 2 (Balanced), 3 (Autonomous)")


@router.get("/intercepts", response_model=List[Dict[str, Any]])
async def list_pending_intercepts():
    """List all active unexpired intercepts quarantined by ActionGuard."""
    ctx = ServerContext.get_instance()
    return ctx.action_guard.get_pending_intercepts()


@router.post("/intercepts/{intercept_id}/resolve")
async def resolve_intercept(intercept_id: str, request: ResolveInterceptRequest):
    """
    Resolve a quarantined intercept from mobile:
    - 'APPROVE': Grants permission to proceed with mutation.
    - 'BLOCK': Halts and aborts the requested action.
    - 'MASK': Sanitizes secrets before execution.
    """
    ctx = ServerContext.get_instance()
    try:
        result = ctx.action_guard.resolve_intercept(
            intercept_id=intercept_id,
            decision=request.decision,
            reason=request.reason,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Intercept '{intercept_id}' not found.")

    # Record resolution to forensic audit log
    record = result.get("record", {})
    ctx.audit_logger.record(
        agent_id=record.get("agentId", "user"),
        action_type="INTERCEPT_RESOLVED",
        target=record.get("target", "unknown"),
        payload={"decision": request.decision, "reason": request.reason, "intercept": record},
        status=result.get("status", "RESOLVED"),
        severity="INFO" if request.decision.upper() == "APPROVE" else "CRITICAL",
    )

    # Publish resolution event to EventBus
    from agentrelay.core.events import AgentEvent, SourceMode
    evt = AgentEvent(
        source_mode=SourceMode.DEV_SHIELD,
        agent_id=record.get("agentId", "user"),
        event_type=EventType.INTERCEPT_RESOLVED,
        autonomy_tier=ctx.action_guard.autonomy_tier,
        payload={"interceptId": intercept_id, "decision": request.decision, "status": result["status"]},
    )
    await ctx.event_bus.publish(evt)

    return result


@router.get("/tier")
async def get_autonomy_tier():
    """Get the currently active Autonomy Tier."""
    ctx = ServerContext.get_instance()
    tier = ctx.action_guard.autonomy_tier
    descriptions = {
        1: "Guarded: Zero mutations allowed without manual mobile approval (45s timer).",
        2: "Balanced: Low/info risk mutations auto-approved; High/Critical quarantined (30s timer).",
        3: "Autonomous: High velocity; all non-critical mutations auto-approved.",
    }
    return {
        "tier": tier.value,
        "name": tier.name,
        "description": descriptions.get(tier.value, ""),
    }


@router.post("/tier")
async def set_autonomy_tier(request: SetTierRequest):
    """Update the active Autonomy Tier."""
    ctx = ServerContext.get_instance()
    new_tier = AutonomyTier(request.tier)
    ctx.action_guard.set_autonomy_tier(new_tier)

    # Log tier change
    ctx.audit_logger.record(
        agent_id="mobile_user",
        action_type="TIER_CHANGE",
        target="action_guard/tier",
        payload={"previous_tier": ctx.action_guard.autonomy_tier.value, "new_tier": request.tier},
        status="EXECUTED",
        severity="INFO",
    )

    return {
        "status": "SUCCESS",
        "tier": new_tier.value,
        "name": new_tier.name,
    }


@router.post("/prune")
async def prune_expired_intercepts():
    """Auto-block and clear all expired intercepts."""
    ctx = ServerContext.get_instance()
    pruned = ctx.action_guard.prune_expired()
    return {"prunedCount": len(pruned), "prunedIds": [p.intercept_id for p in pruned]}


@router.get("/policies")
async def get_guardrail_policies():
    """Summary of active security policies."""
    ctx = ServerContext.get_instance()
    return {
        "autonomyTier": ctx.action_guard.autonomy_tier.value,
        "pathGuard": {
            "status": "ACTIVE",
            "workspaceRoot": str(ctx.action_guard.path_guard.workspace_root),
            "protectedFilenames": list(ctx.action_guard.path_guard.PROTECTED_FILENAMES),
            "protectedExtensions": list(ctx.action_guard.path_guard.PROTECTED_EXTENSIONS),
        },
        "commandGuard": {
            "status": "ACTIVE",
            "blockedPatternCount": len(ctx.action_guard.command_guard.BLOCKED_PATTERNS),
        },
        "secretRedactor": {
            "status": "ACTIVE",
            "patternCount": len(ctx.action_guard.secret_redactor.PATTERNS),
        },
    }
