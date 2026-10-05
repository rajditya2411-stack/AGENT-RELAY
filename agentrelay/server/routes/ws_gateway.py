"""
AgentRelay v2.0 — Dual-Mode WebSocket Multiplexer Gateway
Single `/ws/live` channel handling Dev Shield terminal streams, Frontier Agent feeds,
and zero-latency cross-mode ActionGuard priority alerts.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from agentrelay.core.events import EventType, SourceMode
from agentrelay.server.context import ServerContext

logger = logging.getLogger("WSGateway")
router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/live")
async def live_websocket_endpoint(
    websocket: WebSocket,
    mode: str = Query("ALL", description="Initial view subscription: 'ALL', 'DEV_SHIELD', or 'FRONTIER_AGENT'"),
):
    """
    Multiplexed Dual-Mode WebSocket endpoint.
    - Delivers Dev Shield and Frontier Agent streams filtered by active mode.
    - Bypasses filters for INTERCEPT_REQUIRED priority alerts.
    - Accepts prompt directives and intercept resolutions.
    """
    ctx = ServerContext.get_instance()
    await websocket.accept()

    current_mode = mode.upper()
    await ctx.register_client(websocket, initial_mode=current_mode)

    try:
        # Send initial handshake state
        agents_status = [adapter.get_status() for adapter in ctx.adapters.values()]
        pending_intercepts = ctx.action_guard.get_pending_intercepts()

        await websocket.send_json({
            "type": "init",
            "activeMode": current_mode,
            "autonomyTier": ctx.action_guard.autonomy_tier.value,
            "agents": agents_status,
            "pendingIntercepts": pending_intercepts,
        })

        # Listen for client directives
        while True:
            raw_msg = await websocket.receive_text()
            try:
                msg = json.loads(raw_msg)
            except Exception:
                continue

            msg_type = msg.get("type")

            # 1. Mode Subscription Switch (The Toggle Switch)
            if msg_type == "subscribe":
                new_mode = msg.get("mode", "ALL").upper()
                ctx.update_client_mode(websocket, new_mode)
                await websocket.send_json({
                    "type": "subscription_updated",
                    "mode": new_mode,
                })
                logger.info(f"Client switched active viewport mode to: {new_mode}")

            # 2. Ping / Pong
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": msg.get("timestamp")})

            # 3. Resolve Intercept
            elif msg_type == "resolve_intercept":
                int_id = msg.get("interceptId")
                decision = msg.get("decision", "BLOCK")
                reason = msg.get("reason")
                try:
                    res = ctx.action_guard.resolve_intercept(int_id, decision, reason)
                    await websocket.send_json({"type": "intercept_resolved", "result": res})
                except KeyError:
                    await websocket.send_json({"type": "error", "message": f"Intercept '{int_id}' not found."})

            # 4. Agent Instruction
            elif msg_type == "prompt":
                agent_id = msg.get("agentId", "dots")
                instruction = msg.get("instruction", "")
                if agent_id in ctx.adapters:
                    adapter = ctx.adapters[agent_id]
                    if not adapter.is_running:
                        await adapter.start()
                    # Execute in background task so socket isn't blocked
                    asyncio.create_task(adapter.send_instruction(instruction))
                    await websocket.send_json({"type": "prompt_acknowledged", "agentId": agent_id})
                else:
                    await websocket.send_json({"type": "error", "message": f"Agent '{agent_id}' not found."})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"WebSocket gateway exception: {e}")
    finally:
        await ctx.unregister_client(websocket)
