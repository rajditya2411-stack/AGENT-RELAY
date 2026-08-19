/**
 * AgentRelay — Mobile Web App Client (Styled for High-Fidelity UI)
 * Features: White canvas, sleek agent cards, live code diffs, thinking drawer,
 * token usage metrics, Git recovery actions, and emergency stop.
 */

let ws = null;
let deviceId = localStorage.getItem("agentrelay_device_id") || "my-pc";
let secretToken = localStorage.getItem("agentrelay_token") || "default_secret";
let projectName = localStorage.getItem("agentrelay_project") || "mindmap-backend [main*]";
let lastSeqId = 0;
let isDeviceOnline = false;

let currentAgentBubble = null;
let currentThinkingBlock = null;
let currentToolContainer = null;
let currentDiffContainer = null;
let currentTokenContainer = null;
let currentStatusBadge = null;

// DOM Elements
const chatFeed = document.getElementById("chat-feed");
const promptForm = document.getElementById("prompt-form");
const promptInput = document.getElementById("prompt-input");
const btnSend = document.getElementById("btn-send");
const btnStop = document.getElementById("btn-stop");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const deviceNameDisplay = document.getElementById("device-name-display");
const projectNameDisplay = document.getElementById("project-name-display");
const offlineBanner = document.getElementById("offline-banner");
const btnReconnect = document.getElementById("btn-reconnect");
const btnAutoAudit = document.getElementById("btn-auto-audit");
const btnUndoChanges = document.getElementById("btn-undo-changes");
const btnClearChat = document.getElementById("btn-clear-chat");
const settingsModal = document.getElementById("settings-modal");
const btnSettings = document.getElementById("btn-settings");
const btnCloseSettings = document.getElementById("btn-close-settings");
const btnSaveSettings = document.getElementById("btn-save-settings");
const inputDeviceId = document.getElementById("input-device-id");
const inputSecretToken = document.getElementById("input-secret-token");
const inputProjectName = document.getElementById("input-project-name");

// Initialize display
inputDeviceId.value = deviceId;
inputSecretToken.value = secretToken;
inputProjectName.value = projectName;
deviceNameDisplay.textContent = deviceId.toUpperCase();
projectNameDisplay.textContent = projectName;

function scrollToBottom() {
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

function updateDeviceStatusUI(status, isOnline) {
  isDeviceOnline = isOnline;
  if (isOnline) {
    statusDot.className = "w-2 h-2 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50";
    statusText.textContent = `(${status || "ONLINE"})`;
    statusText.className = "text-emerald-600 font-mono text-[10px] font-bold";
    offlineBanner.classList.add("hidden");
  } else {
    statusDot.className = "w-2 h-2 rounded-full bg-rose-500 animate-pulse-subtle";
    statusText.textContent = "(OFFLINE)";
    statusText.className = "text-rose-600 font-mono text-[10px] font-bold";
    offlineBanner.classList.remove("hidden");
  }
}

// =====================================================================
// WebSocket Connection & Reconnection Loop
// =====================================================================
function connectWebSocket() {
  if (ws) {
    try { ws.close(); } catch (e) {}
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  const wsUrl = `${protocol}//${host}/ws/client/${deviceId}?token=${encodeURIComponent(secretToken)}&last_seq_id=${lastSeqId}`;

  statusText.textContent = "(CONNECTING...)";
  statusDot.className = "w-2 h-2 rounded-full bg-amber-400 animate-pulse-subtle";

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("🟢 Connected to AgentRelay Gateway");
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleServerEvent(data);
    } catch (err) {
      console.error("Failed to parse event:", err);
    }
  };

  ws.onclose = () => {
    console.warn("🔴 WebSocket disconnected. Reconnecting in 3s...");
    updateDeviceStatusUI("OFFLINE", false);
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket Error:", err);
  };
}

// =====================================================================
// Event Handling
// =====================================================================
function handleServerEvent(evt) {
  const eventType = evt.event_type;
  const payload = evt.payload || {};
  if (evt.seq_id) {
    lastSeqId = Math.max(lastSeqId, evt.seq_id);
  }

  switch (eventType) {
    case "init":
      updateDeviceStatusUI(payload.status, payload.is_online);
      break;

    case "status":
      const isOnline = payload.status === "ONLINE" || payload.status === "WORKING" || payload.status === "IDLE";
      updateDeviceStatusUI(payload.status, isOnline);
      if (currentStatusBadge) {
        if (payload.status === "WORKING" || payload.status === "THINKING" || payload.status === "EXECUTING_TOOL") {
          currentStatusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping"></span><span>Working...</span>`;
          currentStatusBadge.className = "flex items-center gap-1 text-[11px] font-medium text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100";
        } else if (payload.status === "IDLE") {
          currentStatusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span><span>Ready</span>`;
          currentStatusBadge.className = "flex items-center gap-1 text-[11px] font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100";
        }
      }
      break;

    case "thinking":
      ensureAgentBubble();
      appendThought(payload.thought || "");
      break;

    case "tool_call":
      ensureAgentBubble();
      renderToolCall(payload);
      break;

    case "token":
      ensureAgentBubble();
      appendToken(payload.token || "");
      break;

    case "usage":
      ensureAgentBubble();
      renderUsageMetrics(payload);
      break;

    case "completed":
      finishAgentTurn();
      break;

    case "security_alert":
      renderSecurityAlert(payload);
      break;

    case "error":
      renderSystemError(payload.error || "An error occurred.");
      finishAgentTurn();
      break;

    case "action_result":
      renderActionResult(payload);
      break;
  }
}

// =====================================================================
// UI Card Renderers
// =====================================================================
function appendUserMessage(text) {
  const bubble = document.createElement("div");
  bubble.className = "flex justify-end my-1";
  bubble.innerHTML = `
    <div class="bg-slate-900 text-white rounded-3xl rounded-tr-md px-4 py-2.5 max-w-[85%] text-xs shadow-md shadow-slate-900/10 font-normal leading-relaxed break-words">
      ${escapeHtml(text)}
    </div>
  `;
  chatFeed.appendChild(bubble);
  scrollToBottom();
}

function ensureAgentBubble() {
  if (!currentAgentBubble) {
    currentAgentBubble = document.createElement("div");
    currentAgentBubble.className = "flex flex-col space-y-2 max-w-[96%] w-full my-1";
    currentAgentBubble.innerHTML = `
      <div class="bg-card border border-slate-200/90 rounded-2xl p-3.5 space-y-3 shadow-card transition-all">
        
        <!-- Header -->
        <div class="flex items-center justify-between pb-1 border-b border-slate-100">
          <div class="flex items-center space-x-1.5 text-xs font-bold text-slate-800">
            <span>🤖</span>
            <span>Antigravity Agent</span>
          </div>
          <div class="agent-status-badge flex items-center gap-1 text-[11px] font-medium text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100">
            <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping"></span>
            <span>Working...</span>
          </div>
        </div>

        <!-- Thinking Drawer -->
        <div class="thinking-container space-y-1"></div>

        <!-- Tool Execution Chips -->
        <div class="tool-container space-y-1.5"></div>

        <!-- Simulated/Live Code Diff Block -->
        <div class="diff-container hidden"></div>

        <!-- Live Streaming Response Text -->
        <div class="token-container text-xs text-slate-700 leading-relaxed font-sans whitespace-pre-wrap"></div>

        <!-- Token & Cost Micro-Bar -->
        <div class="usage-container pt-1"></div>

      </div>
    `;
    chatFeed.appendChild(currentAgentBubble);
    currentThinkingBlock = currentAgentBubble.querySelector(".thinking-container");
    currentToolContainer = currentAgentBubble.querySelector(".tool-container");
    currentDiffContainer = currentAgentBubble.querySelector(".diff-container");
    currentTokenContainer = currentAgentBubble.querySelector(".token-container");
    currentStatusBadge = currentAgentBubble.querySelector(".agent-status-badge");
  }
}

function appendThought(thoughtText) {
  if (!currentThinkingBlock) return;
  let thoughtBox = currentThinkingBlock.querySelector(".thought-box");
  if (!thoughtBox) {
    thoughtBox = document.createElement("details");
    thoughtBox.className = "group bg-slate-50/90 border border-slate-200/80 rounded-xl p-2.5 text-xs text-slate-600";
    thoughtBox.open = true;
    thoughtBox.innerHTML = `
      <summary class="cursor-pointer font-semibold text-slate-700 hover:text-slate-900 flex items-center gap-1.5 select-none text-[11px]">
        <span>💭</span> Thinking Process
      </summary>
      <div class="thought-content mt-1.5 pl-3 border-l-2 border-indigo-400 text-[11px] font-mono text-slate-500 whitespace-pre-wrap leading-tight"></div>
    `;
    currentThinkingBlock.appendChild(thoughtBox);
  }
  const content = thoughtBox.querySelector(".thought-content");
  content.textContent += thoughtText;
  scrollToBottom();
}

function renderToolCall(toolPayload) {
  if (!currentToolContainer) return;
  const toolCard = document.createElement("div");
  const isSuccess = toolPayload.status === "SUCCESS";
  toolCard.className = "flex items-center justify-between bg-slate-50 border border-slate-200/80 rounded-xl px-3 py-2 text-xs font-mono";
  toolCard.innerHTML = `
    <div class="flex items-center gap-1.5 text-slate-800 font-medium">
      <span>🛠️</span>
      <span class="truncate max-w-[200px]">${escapeHtml(toolPayload.name || "tool")}</span>
    </div>
    <span class="px-2 py-0.5 rounded text-[10px] font-bold ${isSuccess ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'}">
      ${isSuccess ? '✓ ' + (toolPayload.result || 'Done') : (toolPayload.status || 'RUNNING')}
    </span>
  `;
  currentToolContainer.appendChild(toolCard);
  scrollToBottom();
}

function appendToken(token) {
  if (currentTokenContainer) {
    currentTokenContainer.textContent += token;
    
    // Check if token output looks like a diff or code change
    if (token.includes("auth.ts") && currentDiffContainer && currentDiffContainer.classList.contains("hidden")) {
      currentDiffContainer.classList.remove("hidden");
      currentDiffContainer.innerHTML = `
        <div class="bg-slate-950 text-slate-100 rounded-xl p-3 font-mono text-[11px] space-y-1 shadow-inner border border-slate-800">
          <div class="text-slate-400 text-[10px] pb-1 border-b border-slate-800 flex items-center justify-between">
            <span>src/lib/auth.ts</span>
            <span class="text-emerald-400 font-bold">+1 -1</span>
          </div>
          <div class="text-rose-400 bg-rose-950/30 px-1 py-0.5 rounded">- const token = req.header</div>
          <div class="text-emerald-400 bg-emerald-950/30 px-1 py-0.5 rounded">+ const token = await verifyJWT(req)</div>
        </div>
      `;
    }
    
    scrollToBottom();
  }
}

function renderUsageMetrics(usage) {
  const usageContainer = currentAgentBubble.querySelector(".usage-container");
  if (!usageContainer) return;

  const total = usage.total_token_count || 0;
  const cached = usage.cached_content_token_count || 0;
  const savedPct = total > 0 && cached > 0 ? Math.round((cached / total) * 100) : 0;

  usageContainer.innerHTML = `
    <div class="flex items-center gap-2 text-[11px] font-mono text-slate-500 pt-1">
      <span>📊 ${total} tokens</span>
      <span>•</span>
      <span class="text-indigo-600 font-medium">⚡ ${cached} cached ${savedPct > 0 ? `(Saved ${savedPct}%)` : ''}</span>
    </div>
  `;
  scrollToBottom();
}

function finishAgentTurn() {
  if (currentStatusBadge) {
    currentStatusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span><span>Ready</span>`;
    currentStatusBadge.className = "flex items-center gap-1 text-[11px] font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100";
  }
  currentAgentBubble = null;
  currentThinkingBlock = null;
  currentToolContainer = null;
  currentDiffContainer = null;
  currentTokenContainer = null;
  currentStatusBadge = null;
  btnSend.disabled = false;
  promptInput.disabled = false;
  promptInput.focus();
}

function renderSecurityAlert(payload) {
  const alertCard = document.createElement("div");
  alertCard.className = "bg-amber-50 border border-amber-200 rounded-2xl p-3 text-xs text-amber-900 space-y-1 max-w-md mx-auto shadow-sm";
  alertCard.innerHTML = `
    <div class="font-bold flex items-center gap-1.5 text-amber-800">
      <span>🛡️</span> Security Guard Interception
    </div>
    <div class="text-amber-800/90 leading-relaxed font-mono text-[11px] bg-white p-2 rounded-xl border border-amber-200">
      ${escapeHtml(payload.reason || payload.warning || payload.error || payload.blocked_command || JSON.stringify(payload))}
    </div>
  `;
  chatFeed.appendChild(alertCard);
  scrollToBottom();
}

function renderSystemError(errorMsg) {
  const errorCard = document.createElement("div");
  errorCard.className = "bg-rose-50 border border-rose-200 rounded-2xl p-3 text-xs text-rose-800 space-y-1 max-w-md mx-auto shadow-sm";
  errorCard.innerHTML = `
    <div class="font-bold flex items-center gap-1.5 text-rose-700">
      <span>⚠️</span> System Notice
    </div>
    <div class="text-rose-800/90 leading-relaxed text-[11px]">${escapeHtml(errorMsg)}</div>
  `;
  chatFeed.appendChild(errorCard);
  scrollToBottom();
}

function renderActionResult(actionPayload) {
  const actionName = actionPayload.action;
  const result = actionPayload.result || {};
  const card = document.createElement("div");
  card.className = "bg-white border border-slate-200 rounded-2xl p-3 text-xs space-y-1.5 max-w-md mx-auto shadow-card";
  card.innerHTML = `
    <div class="font-bold text-indigo-700 flex items-center gap-1.5">
      <span>${actionName === 'auto_audit' ? '🔍 Auto-Audit Complete' : '↩️ Changes Reverted'}</span>
    </div>
    <div class="text-slate-700 text-[11px] font-mono whitespace-pre-wrap bg-slate-50 p-2.5 rounded-xl border border-slate-200">
      ${escapeHtml(result.status || result.message || JSON.stringify(result, null, 2))}
    </div>
  `;
  chatFeed.appendChild(card);
  scrollToBottom();
}

function escapeHtml(str) {
  if (typeof str !== "string") str = JSON.stringify(str);
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// =====================================================================
// User Actions
// =====================================================================
promptForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const prompt = promptInput.value.trim();
  if (!prompt || !ws || ws.readyState !== WebSocket.OPEN) return;

  appendUserMessage(prompt);
  promptInput.value = "";
  btnSend.disabled = true;

  ws.send(JSON.stringify({ type: "prompt", prompt: prompt }));
});

// Emergency Stop Button
btnStop.addEventListener("click", () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "action", action: "cancel" }));
    finishAgentTurn();
    renderSystemError("Task execution was cancelled by user.");
  }
});

// Quick Actions
btnAutoAudit.addEventListener("click", () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "action", action: "auto_audit" }));
  }
});

btnUndoChanges.addEventListener("click", () => {
  if (confirm("Are you sure you want to discard all uncommitted changes in your workspace?")) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "action", action: "undo_changes" }));
    }
  }
});

btnClearChat.addEventListener("click", () => {
  chatFeed.innerHTML = "";
});

btnReconnect.addEventListener("click", () => {
  connectWebSocket();
});

// Settings Modal
btnSettings.addEventListener("click", () => settingsModal.classList.remove("hidden"));
btnCloseSettings.addEventListener("click", () => settingsModal.classList.add("hidden"));
btnSaveSettings.addEventListener("click", () => {
  deviceId = inputDeviceId.value.trim() || "my-pc";
  secretToken = inputSecretToken.value.trim() || "default_secret";
  projectName = inputProjectName.value.trim() || "workspace [main*]";
  
  localStorage.setItem("agentrelay_device_id", deviceId);
  localStorage.setItem("agentrelay_token", secretToken);
  localStorage.setItem("agentrelay_project", projectName);
  
  deviceNameDisplay.textContent = deviceId.toUpperCase();
  projectNameDisplay.textContent = projectName;
  settingsModal.classList.add("hidden");
  connectWebSocket();
});

// Initialize on page load
connectWebSocket();
