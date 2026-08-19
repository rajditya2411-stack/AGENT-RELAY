"""
AgentRelay — Secure Cloud Relay Server & Mobile Web App Gateway (Phases 2 & 3)
Serves the Mobile Web App PWA frontend and handles WebSocket pairing between Desktop Bridges and Phones.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgentRelayServer")

app = FastAPI(title="AgentRelay Gateway & Web App", version="0.3.0")

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
        # Keep last 1000 events in memory
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

    # Send initial connection state and sync replay
    try:
        await websocket.send_json({
            "event_type": "init",
            "payload": {
                "device_id": device_id,
                "is_online": session.is_online,
                "status": "ONLINE" if session.is_online else "DEVICE OFFLINE",
                "current_seq_id": session.current_seq_id,
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

            # Forward prompt or action (audit / undo / cancel) to Desktop Bridge
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

    parser = argparse.ArgumentParser(description="AgentRelay Cloud Relay Gateway")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    args = parser.parse_args()

    print(f"\n============================================================")
    print(f"⚡ AgentRelay Gateway running at: http://{args.host}:{args.port}")
    print(f"📱 Open http://localhost:{args.port} in your browser")
    print(f"============================================================\n")

    # Silence harmless Windows 10054 connection reset tracebacks on browser refresh
    if sys.platform == "win32":
        import asyncio
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

    try:
        uvicorn.run(app, host=args.host, port=args.port)
    except OSError as e:
        print(f"⚠️ Port {args.port} error ({e}). Trying fallback port 8080...")
        uvicorn.run(app, host=args.host, port=8080)
