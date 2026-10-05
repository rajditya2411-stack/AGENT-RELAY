"""
AgentRelay v2.0 — Agent Lifecycle & Dispatch Router
Endpoints for managing Frontier and Dev agents.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agentrelay.core.events import SourceMode
from agentrelay.server.context import ServerContext

router = APIRouter(prefix="/api/v2/agents", tags=["Agents"])


class InstructRequest(BaseModel):
    instruction: str = Field(..., description="Prompt or directive for the agent")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Optional extra execution context")


@router.get("", response_model=List[Dict[str, Any]])
async def list_agents():
    """List all registered Dev Coding and Frontier Assistant agents with live status."""
    ctx = ServerContext.get_instance()
    agent_list = []

    # Dev Agents (via Bridge / CLI status)
    dev_agents = [
        {"agentId": "claude_code", "name": "Anthropic Claude Code", "sourceMode": "DEV_SHIELD", "model": "claude-3-7-sonnet", "isRunning": True, "activeTask": None},
        {"agentId": "antigravity", "name": "Google Antigravity", "sourceMode": "DEV_SHIELD", "model": "gemini-2.5-pro", "isRunning": True, "activeTask": None},
        {"agentId": "codex", "name": "OpenAI Codex", "sourceMode": "DEV_SHIELD", "model": "o3-mini", "isRunning": True, "activeTask": None},
    ]
    agent_list.extend(dev_agents)

    # Frontier Assistant Adapters
    for agent_id, adapter in ctx.adapters.items():
        status = adapter.get_status()
        status["tier"] = ctx.action_guard.autonomy_tier.value
        agent_list.append(status)

    return agent_list


@router.post("/{agent_id}/start")
async def start_agent(agent_id: str):
    """Start an agent connection or sandbox."""
    ctx = ServerContext.get_instance()
    if agent_id not in ctx.adapters:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found.")
    adapter = ctx.adapters[agent_id]
    await adapter.start()
    return {"status": "SUCCESS", "message": f"Agent '{agent_id}' started.", "agent": adapter.get_status()}


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str):
    """Gracefully stop an agent connection."""
    ctx = ServerContext.get_instance()
    if agent_id not in ctx.adapters:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found.")
    adapter = ctx.adapters[agent_id]
    await adapter.stop()
    return {"status": "SUCCESS", "message": f"Agent '{agent_id}' stopped.", "agent": adapter.get_status()}


@router.post("/{agent_id}/instruct")
async def instruct_agent(agent_id: str, request: InstructRequest):
    """Send an instruction to a Frontier or Dev agent."""
    ctx = ServerContext.get_instance()
    if agent_id not in ctx.adapters:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found.")
    adapter = ctx.adapters[agent_id]
    if not adapter.is_running:
        await adapter.start()
    result = await adapter.send_instruction(request.instruction, request.context)
    return {"status": "SUCCESS", "agentId": agent_id, "result": result}


@router.get("/{agent_id}/history")
async def get_agent_history(agent_id: str, limit: int = Query(50, ge=1, le=200)):
    """Retrieve event history for a specific agent."""
    ctx = ServerContext.get_instance()
    events = ctx.event_bus.get_history(limit=limit, agent_id=agent_id)
    return {"agentId": agent_id, "count": len(events), "events": [e.to_dict() for e in events]}
