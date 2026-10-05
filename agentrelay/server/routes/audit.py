"""
AgentRelay v2.0 — Forensic Audit & Compliance Router
Endpoints for querying tamper-evident logs, verifying SHA-256 signatures, and downloading compliance bundles.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from agentrelay.server.context import ServerContext

router = APIRouter(prefix="/api/v2/audit", tags=["Audit"])


@router.get("/entries", response_model=List[Dict[str, Any]])
async def get_audit_entries(
    limit: int = Query(50, ge=1, le=500),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    severity: Optional[str] = Query(None, description="Filter by severity: 'INFO', 'LOW', 'HIGH', 'CRITICAL'"),
    status: Optional[str] = Query(None, description="Filter by status: 'EXECUTED', 'QUARANTINED', 'BLOCKED', 'APPROVED'"),
):
    """Retrieve cryptographic forensic trail entries."""
    ctx = ServerContext.get_instance()
    return ctx.audit_logger.get_entries(limit=limit, agent_id=agent_id, severity=severity, status=status)


@router.get("/verify")
async def verify_audit_integrity():
    """Verify cryptographic chain and tamper-evident signatures across the entire ledger."""
    ctx = ServerContext.get_instance()
    is_valid, reason = ctx.audit_logger.verify_chain_integrity()
    return {
        "chainIntact": is_valid,
        "entryCount": len(ctx.audit_logger.entries),
        "signingAlgorithm": ctx.audit_logger.signing_algorithm,
        "publicKeyHex": ctx.audit_logger.get_public_key_hex(),
        "verificationDetail": reason if not is_valid else "Cryptographic chain and all record digests verified intact.",
    }


@router.get("/export")
async def export_compliance_bundle():
    """Download signed compliance audit bundle in JSON format."""
    ctx = ServerContext.get_instance()
    bundle = ctx.audit_logger.export_compliance_bundle()
    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": "attachment; filename=agentrelay_compliance_bundle.json"},
    )


@router.get("/stats")
async def get_audit_stats():
    """Get summarized metric counts for the mobile telemetry dashboard."""
    ctx = ServerContext.get_instance()
    entries = ctx.audit_logger.entries
    return {
        "totalEntries": len(entries),
        "quarantinedCount": sum(1 for e in entries if e.get("status") == "QUARANTINED"),
        "criticalCount": sum(1 for e in entries if e.get("severity") == "CRITICAL"),
        "approvedCount": sum(1 for e in entries if e.get("status") in ("APPROVED", "RESOLVED")),
        "signingAlgorithm": ctx.audit_logger.signing_algorithm,
    }
