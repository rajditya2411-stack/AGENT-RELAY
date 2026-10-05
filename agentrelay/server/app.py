"""
AgentRelay v2.0 — FastAPI Application Factory
Initializes and binds modular routes, WebSocket gateways, and static PWA assets.
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agentrelay.server.context import ServerContext
from agentrelay.server.routes import (
    agents_router,
    audit_router,
    guardrails_router,
    vault_router,
    ws_router,
)


def create_app(workspace_path: str = ".") -> FastAPI:
    """Create and configure the AgentRelay v2.0 FastAPI application."""
    # Ensure server context is initialized
    ServerContext.get_instance()

    app = FastAPI(
        title="AgentRelay v2.0 — Universal Agent OS",
        version="2.0.0",
        description="Universal Operating System and Security Shield for Dev and Frontier Autonomous Agents.",
    )

    # Enable CORS for Mobile PWA
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include Modular v2 Routers
    app.include_router(agents_router)
    app.include_router(guardrails_router)
    app.include_router(vault_router)
    app.include_router(audit_router)
    app.include_router(ws_router)

    # Mount static assets
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def serve_index():
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            return {"status": "AgentRelay v2.0 Gateway Online"}

    @app.get("/health", tags=["Health"])
    async def health_check():
        ctx = ServerContext.get_instance()
        return {
            "status": "healthy",
            "version": "2.0.0",
            "autonomyTier": ctx.action_guard.autonomy_tier.value,
            "connectedClients": len(ctx.connected_clients),
            "frontierAgents": list(ctx.adapters.keys()),
            "vaultLocked": ctx.vault.is_locked,
        }

    return app
