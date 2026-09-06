"""
AgentRelay — Secure Cloud Relay Server & Mobile Web App Gateway (Phases 2 & 3)
Serves the Mobile Web App PWA frontend and handles WebSocket pairing between Desktop Bridges and Phones.
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgentRelayServer")

app = FastAPI(title="AgentRelay Gateway & Web App", version="1.0.0")

# Enable CORS for Mobile Web App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure static directory exists
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class DeviceSession:
    """Represents a paired desktop device and its active sessions."""

    def __init__(self, device_id: str, secret_token: str = "default_secret"):
        self.device_id = device_id
        self.secret_token = secret_token
        self.bridge_ws: Optional[WebSocket] = None
        self.client_ws_list: Set[WebSocket] = set()
        self.is_online: bool = False
        self.last_seen: float = 0.0
        self.event_history: List[Dict[str, Any]] = []
        self.current_seq_id: int = 0

        # Multi-Project & Telemetry State
        self.projects: List[Dict[str, Any]] = [
            {"id": "agent-relay", "name": "AGENT-RELAY", "path": ".", "lang": "Python / FastAPI", "branch": "main*", "has_changes": False, "status_text": "Clean"},
            {"id": "mindmap", "name": "MINDMAP", "path": "../mindmap", "lang": "TypeScript / React", "branch": "main", "has_changes": True, "status_text": "2 uncommitted files"},
            {"id": "aegic-14c", "name": "AEGIC-14C", "path": "../aegic-14c", "lang": "Python / PyTorch", "branch": "dev*", "has_changes": False, "status_text": "Clean"},
            {"id": "trace", "name": "TRACE", "path": "../trace", "lang": "Go / Microservices", "branch": "master", "has_changes": True, "status_text": "1 uncommitted file"},
        ]
        self.active_task: Optional[Dict[str, Any]] = None
        self.recent_tasks: List[Dict[str, Any]] = []
        self.terminal_logs: List[str] = []
        self.audit_logs: List[Dict[str, Any]] = []
        self.chat_sessions: Dict[str, List[Dict[str, Any]]] = {
            "agent-relay": [
                {"id": "session-ar-1", "title": "WebSocket Reconnect Strategy with Jitter", "timestamp": time.time() - 3600, "tokens": 240},
                {"id": "session-ar-2", "title": "Stitch UI & Multi-Project Layout", "timestamp": time.time() - 1200, "tokens": 412},
            ],
            "mindmap": [
                {"id": "session-mm-1", "title": "Refactor authentication middleware in src/auth.ts", "timestamp": time.time() - 7200, "tokens": 342},
                {"id": "session-mm-2", "title": "Canvas Zoom & Pan Smoothness", "timestamp": time.time() - 1800, "tokens": 195},
            ],
            "aegic-14c": [
                {"id": "session-ae-1", "title": "Model Checkpoint Serialization", "timestamp": time.time() - 86400, "tokens": 510},
            ],
            "trace": [
                {"id": "session-tr-1", "title": "gRPC Trace Header Propagation", "timestamp": time.time() - 43200, "tokens": 288},
            ]
        }

    def add_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Appends an event with a monotonic sequence ID for reconnection replay."""
        self.current_seq_id += 1
        stored_event = {
            "seq_id": self.current_seq_id,
            "timestamp": event.get("timestamp", time.time()),
            "event_type": event.get("event_type", "unknown"),
            "payload": event.get("payload", {}),
        }
        self.event_history.append(stored_event)
        if len(self.event_history) > 1000:
            self.event_history.pop(0)
        return stored_event

    def get_events_since(self, last_seq_id: int) -> List[Dict[str, Any]]:
        """Returns all events recorded after last_seq_id."""
        return [e for e in self.event_history if e["seq_id"] > last_seq_id]


# Global session registry: device_id -> DeviceSession
DEVICE_SESSIONS: Dict[str, DeviceSession] = {}


def get_or_create_session(device_id: str, secret_token: str = "default_secret") -> DeviceSession:
    if device_id not in DEVICE_SESSIONS:
        DEVICE_SESSIONS[device_id] = DeviceSession(device_id, secret_token)
    return DEVICE_SESSIONS[device_id]


# Serve Mobile Web App at Root
@app.get("/")
async def serve_mobile_web_app():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "AgentRelay Mobile Web App. Please visit /static/index.html"}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "registered_devices": len(DEVICE_SESSIONS),
        "online_devices": sum(1 for s in DEVICE_SESSIONS.values() if s.is_online),
    }


@app.get("/api/devices/{device_id}/status")
async def get_device_status(device_id: str):
    session = DEVICE_SESSIONS.get(device_id)
    if not session:
        return {
            "device_id": device_id,
            "is_online": False,
            "last_seen": 0,
            "status": "DEVICE OFFLINE",
            "message": "Device has not registered yet.",
        }
    return {
        "device_id": device_id,
        "is_online": session.is_online,
        "last_seen": session.last_seen,
        "status": "ONLINE" if session.is_online else "DEVICE OFFLINE",
        "current_seq_id": session.current_seq_id,
        "project_count": len(session.projects),
        "active_task": session.active_task,
    }


@app.get("/api/devices/{device_id}/projects")
async def get_device_projects(device_id: str):
    session = get_or_create_session(device_id)
    return {
        "device_id": device_id,
        "projects": session.projects,
    }


@app.get("/api/devices/{device_id}/sessions")
async def get_project_sessions(device_id: str, project_id: str = Query("agent-relay")):
    session = get_or_create_session(device_id)
    return {
        "device_id": device_id,
        "project_id": project_id,
        "sessions": session.chat_sessions.get(project_id, []),
    }


@app.get("/api/devices/{device_id}/tasks")
async def get_device_tasks(device_id: str):
    session = get_or_create_session(device_id)
    return {
        "device_id": device_id,
        "active_task": session.active_task,
        "recent_tasks": session.recent_tasks,
    }


@app.get("/api/devices/{device_id}/terminal")
async def get_terminal_logs(device_id: str):
    session = get_or_create_session(device_id)
    return {
        "device_id": device_id,
        "lines": session.terminal_logs[-100:],
    }


@app.get("/api/devices/{device_id}/audit-logs")
async def get_audit_logs(device_id: str):
    session = get_or_create_session(device_id)
    return {
        "device_id": device_id,
        "logs": session.audit_logs[:50],
    }


@app.get("/api/devices/{device_id}/events")
async def get_device_events(device_id: str, since: int = Query(0, ge=0)):
    session = DEVICE_SESSIONS.get(device_id)
    if not session:
        raise HTTPException(status_code=404, detail="Device not found")
    return {
        "device_id": device_id,
        "events": session.get_events_since(since),
        "current_seq_id": session.current_seq_id,
    }


# =====================================================================
# Desktop Agent Bridge WebSocket Endpoint
# =====================================================================
@app.websocket("/ws/bridge/{device_id}")
async def bridge_websocket_endpoint(
    websocket: WebSocket,
    device_id: str,
    token: str = Query("default_secret"),
):
    """Bridge connection from user's computer."""
    await websocket.accept()
    session = get_or_create_session(device_id, token)

    if session.secret_token and session.secret_token != token:
        logger.warning(f"Bridge auth failed for device: {device_id}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    session.bridge_ws = websocket
    session.is_online = True
    session.last_seen = time.time()
    logger.info(f"🟢 Desktop Bridge CONNECTED: device_id='{device_id}'")

    # Broadcast ONLINE status to connected mobile clients
    status_event = session.add_event({
        "event_type": "status",
        "payload": {"status": "ONLINE", "message": "Desktop agent bridge connected."},
    })
    for client in list(session.client_ws_list):
        try:
            await client.send_json(status_event)
        except Exception:
            session.client_ws_list.discard(client)

    try:
        while True:
            raw_data = await websocket.receive_text()
            session.last_seen = time.time()
            try:
                msg = json.loads(raw_data)
            except json.JSONDecodeError:
                continue

            # Heartbeat ping from bridge
            if msg.get("event_type") == "heartbeat":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
                continue

            # Update session state from bridge telemetry
            evt_type = msg.get("event_type")
            evt_payload = msg.get("payload", {})

            if evt_type == "projects_list":
                session.projects = evt_payload.get("projects", session.projects)
            elif evt_type == "task_update":
                if evt_payload.get("status") == "RUNNING":
                    session.active_task = evt_payload
                    session.recent_tasks.insert(0, evt_payload)
                    if len(session.recent_tasks) > 20:
                        session.recent_tasks.pop()
                elif evt_payload.get("status") == "IDLE":
                    session.active_task = None
            elif evt_type == "terminal_line":
                line = evt_payload.get("line", "")
                session.terminal_logs.append(line)
                if len(session.terminal_logs) > 500:
                    session.terminal_logs.pop(0)
            elif evt_type == "audit_log":
                audit_entry = dict(evt_payload)
                audit_entry["timestamp"] = audit_entry.get("timestamp", time.time())
                session.audit_logs.insert(0, audit_entry)
                if len(session.audit_logs) > 100:
                    session.audit_logs.pop()

            # Store and broadcast bridge event to mobile clients
            stored_event = session.add_event(msg)
            for client in list(session.client_ws_list):
                try:
                    await client.send_json(stored_event)
                except Exception:
                    session.client_ws_list.discard(client)

    except WebSocketDisconnect:
        logger.warning(f"🔴 Desktop Bridge DISCONNECTED: device_id='{device_id}'")
    except Exception as e:
        logger.error(f"Bridge WS error: {e}")
    finally:
        session.bridge_ws = None
        session.is_online = False
        session.last_seen = time.time()

        # Broadcast DEVICE OFFLINE status to all clients
        offline_event = session.add_event({
            "event_type": "status",
            "payload": {
                "status": "DEVICE OFFLINE",
                "message": "Desktop computer is offline or asleep.",
            },
        })
        for client in list(session.client_ws_list):
            try:
                await client.send_json(offline_event)
            except Exception:
                session.client_ws_list.discard(client)


# =====================================================================
# Mobile Client WebSocket Endpoint
# =====================================================================
@app.websocket("/ws/client/{device_id}")
async def client_websocket_endpoint(
    websocket: WebSocket,
    device_id: str,
    token: str = Query("default_secret"),
    last_seq_id: int = Query(0),
):
    """Mobile Web App client connection."""
    await websocket.accept()
    session = get_or_create_session(device_id, token)
    session.client_ws_list.add(websocket)
    logger.info(f"📱 Mobile Client CONNECTED: device_id='{device_id}' (last_seq_id={last_seq_id})")

    # Send initial connection state, projects, tasks, terminal and audit logs
    try:
        await websocket.send_json({
            "event_type": "init",
            "payload": {
                "device_id": device_id,
                "is_online": session.is_online,
                "status": "ONLINE" if session.is_online else "DEVICE OFFLINE",
                "current_seq_id": session.current_seq_id,
                "projects": session.projects,
                "chat_sessions": session.chat_sessions,
                "active_task": session.active_task,
                "recent_tasks": session.recent_tasks[:5],
                "terminal_logs": session.terminal_logs[-30:],
                "audit_logs": session.audit_logs[:20],
            },
        })

        # Replay any missed events for seamless reconnection
        if last_seq_id > 0:
            missed_events = session.get_events_since(last_seq_id)
            if missed_events:
                logger.info(f"Replaying {len(missed_events)} events to client for device='{device_id}'")
                for evt in missed_events:
                    await websocket.send_json(evt)

        while True:
            raw_data = await websocket.receive_text()
            try:
                client_msg = json.loads(raw_data)
            except json.JSONDecodeError:
                continue

            msg_type = client_msg.get("type")

            # Heartbeat ping
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
                continue

            # Create new chat session for a project
            if msg_type == "new_session":
                proj_id = client_msg.get("project_id", "agent-relay")
                new_title = client_msg.get("title", f"Session #{len(session.chat_sessions.get(proj_id, [])) + 1}")
                new_sess = {
                    "id": f"session-{int(time.time())}",
                    "title": new_title,
                    "timestamp": time.time(),
                    "tokens": 0
                }
                if proj_id not in session.chat_sessions:
                    session.chat_sessions[proj_id] = []
                session.chat_sessions[proj_id].insert(0, new_sess)
                await websocket.send_json({
                    "event_type": "session_created",
                    "payload": {"project_id": proj_id, "session": new_sess, "sessions": session.chat_sessions[proj_id]}
                })
                continue

            # Forward prompt or action (audit / undo / run_tests / cancel) to Desktop Bridge
            if session.bridge_ws and session.is_online:
                await session.bridge_ws.send_json(client_msg)
            else:
                # Device is offline, inform the mobile client immediately
                await websocket.send_json({
                    "event_type": "error",
                    "payload": {
                        "error": "DEVICE OFFLINE: Command could not be delivered. Make sure your desktop bridge is running.",
                        "status": "DEVICE OFFLINE",
                    },
                })

    except WebSocketDisconnect:
        logger.info(f"Mobile Client disconnected: device_id='{device_id}'")
    except Exception as e:
        logger.error(f"Client WS error: {e}")
    finally:
        session.client_ws_list.discard(websocket)


if __name__ == "__main__":
    import argparse
    import uvicorn
    import socket

    parser = argparse.ArgumentParser(description="AgentRelay Cloud Relay Gateway")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=58765, help="Port to listen on (default: 58765)")
    args = parser.parse_args()

    # Find first working port
    chosen_port = args.port
    for candidate_port in [args.port, 8765, 58765, 54321]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((args.host, candidate_port))
                s.listen(1)
                chosen_port = candidate_port
                break
        except Exception:
            continue

    # Record active port for local bridge auto-discovery
    try:
        with open(".agentrelay_port", "w", encoding="utf-8") as f:
            f.write(str(chosen_port))
    except Exception:
        pass

    print("\n============================================================")
    print(f"AgentRelay Gateway running at: http://{args.host}:{chosen_port}")
    print(f"Open http://localhost:{chosen_port} in your browser")
    print("============================================================\n")

    # Silence harmless Windows 10054 connection reset tracebacks on browser refresh
    if sys.platform == "win32":
        def _win_exception_handler(loop, context):
            exc = context.get("exception")
            if isinstance(exc, ConnectionResetError):
                return
            loop.default_exception_handler(context)
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(_win_exception_handler)
        except Exception:
            pass

    uvicorn.run(app, host=args.host, port=chosen_port)
