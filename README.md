# ⚡ AgentRelay

> **Vibe code on the go — control and stream AI coding agents (Antigravity, Claude Code, OpenAI Codex) on your computer directly from your phone.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AgentRelay** turns your mobile phone into a high-fidelity remote command center for local AI coding agents. Whether you're using **Google Antigravity**, **Anthropic Claude Code**, or **OpenAI Codex**, you can walk away from your desk, prompt your agents on your phone, watch reasoning and tool calls stream live, and trigger one-tap Git recovery actions with zero latency.

---

## ✨ Key Capabilities

* **📱 Mobile-First Vibe-Coding Web App**: Clean, high-fidelity responsive UI styled with slate-50/white cards (`#F8FAFC`).
* **🤖 Multi-Agent Engine Support**:
  * ⚡ **Google Antigravity** (`gemini-2.5-pro`)
  * 🟠 **Anthropic Claude Code** (`claude-3-7-sonnet` with extended thinking)
  * 🟢 **OpenAI Codex** (`gpt-4o`, `o3-mini`, `codex`)
* **📁 Multi-Project Navigation & Agent Badges**: Switch between your local repositories (`AGENT-RELAY`, `MINDMAP`, `AEGIC-14C`, `TRACE`) with visual badges showing which AI agent manages each repo.
* **⚙️ Triple API Key Management**: Easily configure API keys for 1, 2, or all 3 engines directly inside the in-app Settings modal without editing terminal configs or restarting servers.
* **🧠 Real-Time Reasoning & Token Streaming**: Live streaming of thought blocks, token deltas, tool executions, and diff previews.
* **📊 Domain Telemetry**: Live tracking of linked projects, token cache savings (`⚡ 128 (33%)`), and ping latency (`24ms`).
* **🔍 One-Tap Quick Actions**:
  * **Auto-Audit & Resume**: Automatically scans uncommitted Git changes so the agent can resume seamlessly.
  * **Undo Changes**: Discards unintended modifications with one click (`git checkout .` / `git clean -fd`).
  * **Run Tests**: Executes local unit test suites (`python -m unittest`) and streams the test report to your phone.
* **🛡️ Hardened Security & Sandboxing**:
  * **PathGuard**: Blocks directory traversal out of the workspace and shields secrets (`.env`, `id_rsa`, `*.pem`).
  * **SecretRedactor**: Automatically scrubs API keys, private keys, and JWTs from streamed tokens before leaving your PC.
  * **CommandGuard**: Blocks hazardous system commands (`rm -rf /`, `format`, `shutdown`, `powershell -enc`).
  * **ExecutionRateGuard**: Prevents runaway loops and enforces turn timeouts.

---

## 🏗️ Architecture

```text
       [ Mobile Phone Browser (PWA) ]
                      │
                      │ HTTPS / WSS
                      ▼
       [ Cloud Relay Gateway (`relay_server.py`) ]
                      ▲
                      │ Outbound WSS (Port 58765)
                      │
       [ Local Desktop Bridge (`bridge.py`) ]
                      │
     ┌────────────────┼────────────────┐
     ▼                ▼                ▼
[ ⚡ Antigravity ] [ 🟠 Claude Code ] [ 🟢 OpenAI Codex ]
     │                │                │
     └────────────────┼────────────────┘
                      ▼
           [ Security Sandboxing Engine ]
                      ▼
           [ Local Workspace / Git Repos ]
```

---

## 🚀 Quickstart

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/rajditya2411-stack/AGENT-RELAY.git
cd AGENT-RELAY

pip install fastapi uvicorn websockets
# (Optional provider SDKs for live mode)
pip install google-antigravity anthropic openai
```

### 2. Start the Gateway Server
```powershell
python relay_server.py
```
* The gateway listens on `http://127.0.0.1:58765`.

### 3. Start the Desktop Bridge
In a second terminal:
```powershell
python bridge.py --relay ws://localhost:58765/ws/bridge --device my-pc --token default_secret
```

---

## 📱 How to Access from Mobile

### Option A: Local Wi-Fi (Same Network)
1. Find your PC's local IP address (`ipconfig` on Windows or `ifconfig` on Mac/Linux).
2. Open `http://<YOUR-PC-IP>:58765` in your mobile browser.

### Option B: 1-Command Remote Access with Cloudflare Tunnel (Anywhere in the World)
Leave your server running and run:
```bash
cloudflared tunnel --url http://localhost:58765
```
Cloudflare gives you an instant, free HTTPS URL (e.g. `https://my-relay.trycloudflare.com`) that you can open on your phone anywhere over 4G/5G!

### Option C: Deploy Gateway to Cloud (Vercel / Render / Railway)
You can deploy `relay_server.py` to Render, Railway, or Vercel, and have `bridge.py` on your computer connect to your cloud URL.

---

## ⚙️ Adding API Keys

You have two easy options to configure your AI providers:

1. **Via Mobile Web UI (Easiest)**:
   * Click **⚙️ Settings** in the top bar.
   * Enter your API keys under **AI Coding Engines** (`Google Gemini`, `Anthropic Claude`, `OpenAI Codex`).
   * Click **Save & Connect**. Credentials sync instantly to the bridge without restarting.

2. **Via Environment Variables**:
   ```powershell
   $env:GEMINI_API_KEY="AIzaSy..."
   $env:ANTHROPIC_API_KEY="sk-ant-..."
   $env:OPENAI_API_KEY="sk-proj-..."
   ```

*(If no API key is provided for an engine, AgentRelay automatically runs in interactive **Mock Mode** so you can test all features and UI workflows risk-free).*

---

## 🧪 Running Automated Tests

Run the complete test suite across all modules:

```bash
python -m unittest discover -s . -p "test_*.py"
```

All 26 automated unit and security tests will execute in isolated sandboxes with 100% green status.

---

## 📄 License
MIT License. Open source and built for vibe coders everywhere.
