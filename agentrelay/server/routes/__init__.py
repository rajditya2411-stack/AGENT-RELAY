"""
AgentRelay v2.0 — Modular API Routers
"""

from agentrelay.server.routes.agents import router as agents_router
from agentrelay.server.routes.guardrails import router as guardrails_router
from agentrelay.server.routes.vault import router as vault_router
from agentrelay.server.routes.audit import router as audit_router
from agentrelay.server.routes.ws_gateway import router as ws_router

__all__ = [
    "agents_router",
    "guardrails_router",
    "vault_router",
    "audit_router",
    "ws_router",
]
