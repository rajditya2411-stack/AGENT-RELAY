# AgentRelay — Remote Tunnel & Gateway Setup (Phase 2)

AgentRelay allows your phone to securely communicate with the Desktop Agent Bridge running on your computer from any cellular or Wi-Fi network.

---

## 🌐 Architecture Overview

```
[ Mobile Phone (PWA) ]
         │
         │ WSS / HTTPS
         ▼
[ Cloud Relay Gateway (FastAPI) ]
         ▲
         │ WSS (Outbound Persistent Socket)
         │
[ Desktop Agent Bridge (`bridge.py`) ]
         │
         ▼
[ Google Antigravity Agent ]
```

---

## 🚀 How to Run the Cloud Relay Locally & Remotely

### Step 1: Start the Relay Server
Run the FastAPI relay server on your machine or cloud VM:

```powershell
python relay_server.py
```
* The server starts on `http://localhost:8000`.
* Test health: `http://localhost:8000/health`

---

### Step 2: Expose the Relay to the Internet (Zero Configuration)

To connect your phone when you are away from home, choose one of these options:

#### Option A: Cloudflare Tunnels (Free & Recommended)
1. Download `cloudflared` from Cloudflare.
2. Run:
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
3. Cloudflare gives you a secure public URL (e.g. `https://random-subdomain.trycloudflare.com`).
4. Your WebSocket URL becomes: `wss://random-subdomain.trycloudflare.com/ws`

#### Option B: Ngrok (Fastest Setup)
1. Run:
   ```bash
   ngrok http 8000
   ```
2. Copy the forwarding HTTPS URL (e.g. `https://xxxx.ngrok-free.app`).
3. Your WebSocket URL becomes: `wss://xxxx.ngrok-free.app/ws`

---

### Step 3: Connect the Desktop Agent Bridge
In a separate terminal on your computer, connect the bridge to the relay:

```powershell
python bridge.py --relay ws://localhost:8000/ws/bridge --device my-pc --token secret123
```

You will see:
```text
[*] Connecting to Cloud Relay: ws://localhost:8000/ws/bridge/my-pc?token=secret123
🟢 Connected to Relay! Device registered as 'my-pc'
```

---

### Step 4: Testing Device Offline Detection
* While the bridge is running, check: `http://localhost:8000/api/devices/my-pc/status` -> `"status": "ONLINE"`
* Press `Ctrl+C` on `bridge.py` to stop the bridge.
* Check status again -> `"status": "DEVICE OFFLINE"`
* The relay immediately broadcasts the offline notice to all connected mobile clients.
