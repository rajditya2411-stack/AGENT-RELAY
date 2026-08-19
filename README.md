# ⚡ AgentRelay

> **Control the AI coding agents running on your computer directly from your phone.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AgentRelay** turns your mobile phone into a remote command center for local AI coding agents (such as Google Antigravity, Claude Code, and Codex). You can be away from your desk, send instructions from your mobile browser, watch reasoning and code diffs stream in real time, and trigger one-tap Git recovery actions.

---

## ✨ Features

* **📱 Mobile-First Responsive Web Console**: Zero-install PWA running directly in any browser (Safari, Chrome).
* **🧠 Live Reasoning & Token Streaming**: Watch the agent think step-by-step with real-time output and tool call cards.
* **📊 Token Usage & Credit Savings**: Exact breakdown of prompt tokens, candidate tokens, and **⚡ Cached Tokens Saved**.
* **🔴 Instant Device Offline Detection**: Heartbeat detection alerts your phone immediately if your PC sleeps or loses connection.
* **🔍 One-Tap Git Recovery Actions**:
  * **Auto-Audit & Resume**: Automatically inspects uncommitted Git changes on reconnect so the agent can resume seamlessly.
  * **Undo Changes**: Reverts accidental modifications with one click (`git checkout .` / `git clean -fd`).
* **🛡️ Security & Sandboxing Engine**:
  * **PathGuard**: Blocks directory traversal out of the workspace and shields sensitive files (`.env`, `id_rsa`, `*.pem`).
  * **SecretRedactor**: Automatically scrubs API keys, private keys, and JWTs from streamed tokens before leaving your PC.
  * **CommandGuard**: Blocks hazardous system commands (`rm -rf /`, `format`, `shutdown`, `powershell -enc`).
  * **ExecutionRateGuard**: Prevents runaway agent loops and enforces turn timeouts.

---

## 🏗️ Architecture

```text
       [ Mobile Phone Browser (PWA) ]
                      │
                      │ HTTPS / WSS
                      ▼
       [ Cloud Relay Gateway (FastAPI) ]
                      ▲
                      │ Outbound WSS (Persistent Socket)
                      │
       [ Local Desktop Bridge (`bridge.py`) ]
                      │
            ┌─────────┴─────────┐
            ▼                   ▼
    [ Security Engine ]   [ Antigravity SDK ]
            │                   │
            └─────────┬─────────┘
                      ▼
           [ Local Workspace / Git ]
```

---

## 🚀 Quickstart

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/rajditya2411-stack/AGENT-RELAY.git
cd AGENT-RELAY

pip install fastapi uvicorn websockets google-antigravity
```

### 2. Start the Cloud Relay Server
```powershell
python relay_server.py
```
* Server starts on `http://127.0.0.1:8765`.

### 3. Start the Desktop Agent Bridge
In a second terminal:
```powershell
# (Optional) Set your API key for live Antigravity execution:
$env:GEMINI_API_KEY="AIzaSy..."

# Run bridge:
python bridge.py --relay ws://localhost:8765/ws/bridge --device my-pc --token default_secret
```

### 4. Open the Mobile Console
* **On your PC Browser:** Open `http://localhost:8765`
* **On your Phone (Same Wi-Fi):** Open `http://<YOUR-PC-IP>:8765`
* **On your Phone (Anywhere / Cellular):** Expose with Cloudflare Tunnel:
  ```bash
  cloudflared tunnel --url http://localhost:8765
  ```

---

## 🧪 Running Automated Tests

Run the complete test suite across all 4 phases:

```bash
# Security & Sandboxing tests
python test_security.py

# Bridge & Adapter tests
python test_bridge.py

# Relay Server & WebSocket tests
python test_relay.py
```

---

## 📄 License
MIT License.
