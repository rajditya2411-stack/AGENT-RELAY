/**
 * AgentRelay — High-Fidelity Mobile Web App Client
 * Implements Stitch UI Layout, Multi-Project Navigation, Chat Execution,
 * Quick Actions, and Live Terminal/Tasks/Logs empty states.
 */

// Global State
let ws = null;
let deviceId = localStorage.getItem("agentrelay_device_id") || "my-pc";
let secretToken = localStorage.getItem("agentrelay_token") || "default_secret";
let geminiApiKey = localStorage.getItem("agentrelay_gemini_key") || "";
let claudeApiKey = localStorage.getItem("agentrelay_claude_key") || "";
let codexApiKey = localStorage.getItem("agentrelay_codex_key") || "";

let lastSeqId = 0;
let isDeviceOnline = false;
let pingStartTime = 0;
let rttLatency = 24;

let activeTab = "home"; // "home" | "terminal" | "tasks" | "logs"
let activeProject = null;
let activeSession = null;

// Telemetry & Data Lists with Assigned AI Agents
let projects = [
  { id: "agent-relay", name: "AGENT-RELAY", lang: "Python / FastAPI", agent: "antigravity", agent_name: "Antigravity", agent_badge: "⚡ Antigravity", branch: "main*", has_changes: false, status_text: "Clean" },
  { id: "mindmap", name: "MINDMAP", lang: "TypeScript / React", agent: "claude", agent_name: "Claude Code", agent_badge: "🟠 Claude Code", branch: "main", has_changes: true, status_text: "2 uncommitted files" },
  { id: "aegic-14c", name: "AEGIC-14C", lang: "Python / PyTorch", agent: "antigravity", agent_name: "Antigravity", agent_badge: "⚡ Antigravity", branch: "dev*", has_changes: false, status_text: "Clean" },
  { id: "trace", name: "TRACE", lang: "Go / Microservices", agent: "codex", agent_name: "OpenAI Codex", agent_badge: "🟢 OpenAI Codex", branch: "master", has_changes: true, status_text: "1 uncommitted file" },
];

let chatSessions = {
  "agent-relay": [
    { id: "session-ar-1", title: "WebSocket Reconnect Strategy with Jitter", timestamp: Date.now() - 3600000, tokens: 240 },
    { id: "session-ar-2", title: "Stitch UI & Multi-Project Layout", timestamp: Date.now() - 1200000, tokens: 412 },
  ],
  "mindmap": [
    { id: "session-mm-1", title: "Refactor authentication middleware in src/auth.ts", timestamp: Date.now() - 7200000, tokens: 342 },
    { id: "session-mm-2", title: "Canvas Zoom & Pan Smoothness", timestamp: Date.now() - 1800000, tokens: 195 },
  ],
  "aegic-14c": [
    { id: "session-ae-1", title: "Model Checkpoint Serialization", timestamp: Date.now() - 86400000, tokens: 510 },
  ],
  "trace": [
    { id: "session-tr-1", title: "gRPC Trace Header Propagation", timestamp: Date.now() - 43200000, tokens: 288 },
  ]
};

let activeTask = null;
let recentTasks = [];
let terminalLines = [];
let auditLogs = [];

// DOM References
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const deviceNameDisplay = document.getElementById("device-name-display");
const telemetryDevice = document.getElementById("telemetry-device");
const telemetryProjectsVal = document.getElementById("telemetry-projects-val");
const telemetryCacheVal = document.getElementById("telemetry-cache-val");
const telemetryLatencyVal = document.getElementById("telemetry-latency-val");
const projectCountBadge = document.getElementById("project-count-badge");
const offlineBanner = document.getElementById("offline-banner");
const btnReconnect = document.getElementById("btn-reconnect");

// Views
const viewHome = document.getElementById("view-home");
const viewProjectSessions = document.getElementById("view-project-sessions");
const viewChat = document.getElementById("view-chat");
const viewTerminal = document.getElementById("view-terminal");
const viewTasks = document.getElementById("view-tasks");
const viewLogs = document.getElementById("view-logs");

// Projects & Sessions DOM
const projectsList = document.getElementById("projects-list");
const btnBackToProjects = document.getElementById("btn-back-to-projects");
const sessionsProjectBadge = document.getElementById("sessions-project-badge");
const btnStartNewChat = document.getElementById("btn-start-new-chat");
const sessionsListContainer = document.getElementById("sessions-list-container");

// Chat DOM
const btnBackToSessions = document.getElementById("btn-back-to-sessions");
const chatProjectTitle = document.getElementById("chat-project-title");
const chatAgentStatus = document.getElementById("chat-agent-status");
const chatFeed = document.getElementById("chat-feed");
const promptForm = document.getElementById("prompt-form");
const promptInput = document.getElementById("prompt-input");
const btnSend = document.getElementById("btn-send");
const btnStop = document.getElementById("btn-stop");

// Chat Quick Actions
const btnAutoAudit = document.getElementById("btn-auto-audit");
const btnUndoChanges = document.getElementById("btn-undo-changes");
const btnRunTests = document.getElementById("btn-run-tests");
const btnClearChat = document.getElementById("btn-clear-chat");

// Terminal DOM
const terminalEmptyState = document.getElementById("terminal-empty-state");
const terminalContent = document.getElementById("terminal-content");
const terminalLinesContainer = document.getElementById("terminal-lines");
const btnClearTerminal = document.getElementById("btn-clear-terminal");

// Tasks DOM
const tasksEmptyState = document.getElementById("tasks-empty-state");
const tasksContent = document.getElementById("tasks-content");

// Logs DOM
const logsEmptyState = document.getElementById("logs-empty-state");
const logsContent = document.getElementById("logs-content");

// Nav Buttons
const navBtnHome = document.getElementById("nav-btn-home");
const navBtnTerminal = document.getElementById("nav-btn-terminal");
const navBtnTasks = document.getElementById("nav-btn-tasks");
const navBtnLogs = document.getElementById("nav-btn-logs");

// Settings Modal
const settingsModal = document.getElementById("settings-modal");
const btnSettings = document.getElementById("btn-settings");
const btnCloseSettings = document.getElementById("btn-close-settings");
const btnSaveSettings = document.getElementById("btn-save-settings");
const inputDeviceId = document.getElementById("input-device-id");
const inputSecretToken = document.getElementById("input-secret-token");
const inputGeminiKey = document.getElementById("input-gemini-key");
const inputClaudeKey = document.getElementById("input-claude-key");
const inputCodexKey = document.getElementById("input-codex-key");
const badgeGeminiKey = document.getElementById("badge-gemini-key");
const badgeClaudeKey = document.getElementById("badge-claude-key");
const badgeCodexKey = document.getElementById("badge-codex-key");

// Bubble Elements for Streaming
let currentAgentBubble = null;
let currentThinkingBlock = null;
let currentToolContainer = null;
let currentDiffContainer = null;
let currentTokenContainer = null;
let currentStatusBadge = null;

// =====================================================================
// Navigation Tab Logic
// =====================================================================
function switchTab(tabName) {
  activeTab = tabName;
  const navBtns = [
    { name: "home", el: navBtnHome },
    { name: "terminal", el: navBtnTerminal },
    { name: "tasks", el: navBtnTasks },
    { name: "logs", el: navBtnLogs },
  ];

  navBtns.forEach((btn) => {
    if (btn.name === tabName) {
      btn.el.className = "nav-btn flex flex-col items-center gap-1 py-1 px-4 rounded-2xl bg-brand-600 text-white transition active:scale-95 shadow-md shadow-brand-600/20";
    } else {
      btn.el.className = "nav-btn flex flex-col items-center gap-1 py-1 px-4 rounded-2xl text-slate-500 hover:text-slate-900 transition active:scale-95";
    }
  });

  // Hide all main views
  viewHome.classList.add("hidden");
  viewProjectSessions.classList.add("hidden");
  viewChat.classList.add("hidden");
  viewTerminal.classList.add("hidden");
  viewTasks.classList.add("hidden");
  viewLogs.classList.add("hidden");

  if (tabName === "home") {
    if (activeSession) {
      viewChat.classList.remove("hidden");
    } else if (activeProject) {
      viewProjectSessions.classList.remove("hidden");
    } else {
      viewHome.classList.remove("hidden");
    }
  } else if (tabName === "terminal") {
    viewTerminal.classList.remove("hidden");
    renderTerminalView();
  } else if (tabName === "tasks") {
    viewTasks.classList.remove("hidden");
    renderTasksView();
  } else if (tabName === "logs") {
    viewLogs.classList.remove("hidden");
    renderLogsView();
  }
}

navBtnHome.addEventListener("click", () => switchTab("home"));
navBtnTerminal.addEventListener("click", () => switchTab("terminal"));
navBtnTasks.addEventListener("click", () => switchTab("tasks"));
navBtnLogs.addEventListener("click", () => switchTab("logs"));

// =====================================================================
// Projects & Sessions Navigation
// =====================================================================
function getAgentBadgeHtml(proj) {
  const agentType = (proj.agent || "antigravity").toLowerCase();
  if (agentType.includes("claude")) {
    return `<span class="inline-flex items-center gap-1 text-[10px] font-semibold text-orange-700 bg-orange-50 px-2 py-0.5 rounded-full border border-orange-200/80">🟠 Claude Code</span>`;
  } else if (agentType.includes("codex") || agentType.includes("openai")) {
    return `<span class="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200/80">🟢 OpenAI Codex</span>`;
  }
  return `<span class="inline-flex items-center gap-1 text-[10px] font-semibold text-brand-700 bg-brand-50 px-2 py-0.5 rounded-full border border-brand-200/80">⚡ Antigravity</span>`;
}

function renderProjectsList() {
  projectsList.innerHTML = "";
  projectCountBadge.textContent = `${projects.length} DETECTED`;
  telemetryProjectsVal.textContent = `${projects.length} Linked`;

  projects.forEach((proj) => {
    const card = document.createElement("div");
    card.className = "group bg-white border border-slate-200/90 hover:border-brand-200 rounded-3xl p-4 shadow-card hover:shadow-md transition-all cursor-pointer flex items-center justify-between";
    
    // Status Badge
    const gitBadge = proj.has_changes
      ? `<span class="inline-flex items-center gap-1 text-[10px] font-mono font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">● ${proj.status_text}</span>`
      : `<span class="inline-flex items-center gap-1 text-[10px] font-mono font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">✓ ${proj.status_text}</span>`;

    const agentBadge = getAgentBadgeHtml(proj);

    card.innerHTML = `
      <div class="flex items-center space-x-3.5 flex-1 min-w-0">
        <div class="w-10 h-10 rounded-2xl bg-brand-50 border border-brand-100 text-brand-600 flex items-center justify-center text-base shrink-0 group-hover:bg-brand-600 group-hover:text-white transition">
          <span>📁</span>
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <h4 class="text-sm font-bold text-slate-900 truncate tracking-tight">${escapeHtml(proj.name)}</h4>
            <span class="text-[10px] font-mono text-slate-400 font-medium">[${escapeHtml(proj.branch)}]</span>
            ${agentBadge}
          </div>
          <div class="flex items-center gap-2 mt-1">
            <span class="text-[11px] text-slate-500 font-mono">${escapeHtml(proj.lang)}</span>
            <span class="text-slate-300">•</span>
            ${gitBadge}
          </div>
        </div>
      </div>
      <button class="w-9 h-9 rounded-2xl bg-slate-50 group-hover:bg-brand-50 group-hover:text-brand-600 text-slate-400 border border-slate-200/70 flex items-center justify-center text-sm font-bold transition shrink-0 ml-3 shadow-sm">
        ↗
      </button>
    `;

    card.addEventListener("click", () => openProject(proj));
    projectsList.appendChild(card);
  });
}

function openProject(proj) {
  activeProject = proj;
  const agentBadge = getAgentBadgeHtml(proj);
  sessionsProjectBadge.innerHTML = `<span class="font-bold text-slate-900">${escapeHtml(proj.name)}</span> <span class="text-slate-400 font-normal">[${escapeHtml(proj.branch)}]</span> • ${agentBadge}`;
  renderProjectSessions(proj.id);
  viewHome.classList.add("hidden");
  viewChat.classList.add("hidden");
  viewProjectSessions.classList.remove("hidden");
}

btnBackToProjects.addEventListener("click", () => {
  activeProject = null;
  activeSession = null;
  viewProjectSessions.classList.add("hidden");
  viewChat.classList.add("hidden");
  viewHome.classList.remove("hidden");
});

function renderProjectSessions(projId) {
  sessionsListContainer.innerHTML = "";
  const sessions = chatSessions[projId] || [];

  if (sessions.length === 0) {
    sessionsListContainer.innerHTML = `
      <div class="bg-white border border-slate-200/80 rounded-2xl p-6 text-center text-xs text-slate-400">
        No past sessions. Click <b>+ New Chat</b> to begin.
      </div>
    `;
    return;
  }

  sessions.forEach((s) => {
    const sCard = document.createElement("div");
    sCard.className = "bg-white border border-slate-200/90 hover:border-brand-300 rounded-2xl p-3.5 shadow-sm hover:shadow-card transition flex items-center justify-between cursor-pointer";
    
    const timeAgo = formatTimeAgo(s.timestamp);
    sCard.innerHTML = `
      <div class="space-y-1 min-w-0 flex-1 pr-2">
        <h5 class="text-xs font-bold text-slate-800 truncate">${escapeHtml(s.title)}</h5>
        <div class="flex items-center gap-2 text-[10px] text-slate-400 font-mono">
          <span>🕒 ${timeAgo}</span>
          <span>•</span>
          <span>⚡ ${s.tokens || 0} tokens</span>
        </div>
      </div>
      <span class="text-xs text-slate-400 font-bold shrink-0">→</span>
    `;

    sCard.addEventListener("click", () => openChatSession(s));
    sessionsListContainer.appendChild(sCard);
  });
}

btnStartNewChat.addEventListener("click", () => {
  if (!activeProject) return;
  const newSession = {
    id: `session-${Date.now()}`,
    title: `Chat Session #${(chatSessions[activeProject.id] || []).length + 1}`,
    timestamp: Date.now(),
    tokens: 0,
  };
  if (!chatSessions[activeProject.id]) chatSessions[activeProject.id] = [];
  chatSessions[activeProject.id].unshift(newSession);

  // Notify server of new session
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "new_session",
      project_id: activeProject.id,
      title: newSession.title,
    }));
  }

  openChatSession(newSession);
});

function openChatSession(session) {
  activeSession = session;
  chatProjectTitle.textContent = `${activeProject.name} [${activeProject.branch}]`;
  const agentBadgeStr = activeProject.agent_badge || "⚡ Antigravity";
  chatAgentStatus.textContent = `${agentBadgeStr} Agent`;
  viewProjectSessions.classList.add("hidden");
  viewHome.classList.add("hidden");
  viewChat.classList.remove("hidden");

  // Show clean welcome hint if chat feed empty
  if (chatFeed.children.length === 0) {
    chatFeed.innerHTML = `
      <div class="bg-white border border-slate-200/80 rounded-2xl p-4 text-center text-slate-500 text-xs shadow-card space-y-1 my-2">
        <div class="text-xl mb-1">${agentBadgeStr.split(" ")[0]} 📱 💻</div>
        <div class="font-bold text-slate-800 text-sm">${escapeHtml(activeProject.name)}</div>
        <p class="leading-relaxed text-slate-500">Workspace connected. Running via <b>${escapeHtml(agentBadgeStr)}</b> engine.</p>
      </div>
    `;
  }
}

btnBackToSessions.addEventListener("click", () => {
  activeSession = null;
  viewChat.classList.add("hidden");
  viewProjectSessions.classList.remove("hidden");
});

// =====================================================================
// Terminal, Tasks, Logs View Logic (With Clean Empty States)
// =====================================================================
function renderTerminalView() {
  if (terminalLines.length === 0) {
    terminalEmptyState.classList.remove("hidden");
    terminalContent.classList.add("hidden");
  } else {
    terminalEmptyState.classList.add("hidden");
    terminalContent.classList.remove("hidden");
    terminalLinesContainer.innerHTML = terminalLines.map(line => `
      <div class="text-slate-300 leading-tight whitespace-pre-wrap"><span class="text-emerald-400 font-bold mr-1.5">&gt;</span>${escapeHtml(line)}</div>
    `).join("");
    terminalContent.scrollTop = terminalContent.scrollHeight;
  }
}

btnClearTerminal.addEventListener("click", () => {
  terminalLines = [];
  renderTerminalView();
});

function renderTasksView() {
  if (!activeTask && recentTasks.length === 0) {
    tasksEmptyState.classList.remove("hidden");
    tasksContent.classList.add("hidden");
  } else {
    tasksEmptyState.classList.add("hidden");
    tasksContent.classList.remove("hidden");
    tasksContent.innerHTML = "";

    // Active Running Task
    if (activeTask && activeTask.status === "RUNNING") {
      const activeCard = document.createElement("div");
      activeCard.className = "bg-white border-2 border-brand-500/80 rounded-3xl p-4 shadow-card space-y-2.5";
      activeCard.innerHTML = `
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-brand-500 animate-ping"></span>
            <span class="text-xs font-bold text-slate-900">RUNNING DIRECTIVE</span>
          </div>
          <span class="text-[10px] font-mono font-bold text-brand-700 bg-brand-50 px-2 py-0.5 rounded-full border border-brand-200">
            ${escapeHtml(activeTask.project_id || "agent-relay")}
          </span>
        </div>
        <p class="text-xs font-semibold text-slate-800">${escapeHtml(activeTask.title || "Agent task in progress...")}</p>
        <div class="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
          <div class="bg-brand-600 h-full w-[60%] rounded-full animate-pulse"></div>
        </div>
      `;
      tasksContent.appendChild(activeCard);
    }

    // Recent Completed Tasks
    recentTasks.forEach((t) => {
      const tCard = document.createElement("div");
      tCard.className = "bg-white border border-slate-200/80 rounded-2xl p-3.5 shadow-sm space-y-1";
      tCard.innerHTML = `
        <div class="flex items-center justify-between text-[11px]">
          <span class="font-bold text-slate-800">${escapeHtml(t.title || "Agent Directive")}</span>
          <span class="text-emerald-600 font-bold">✓ COMPLETED</span>
        </div>
        <div class="text-[10px] text-slate-400 font-mono">${escapeHtml(t.project_id || "agent-relay")}</div>
      `;
      tasksContent.appendChild(tCard);
    });
  }
}

function renderLogsView() {
  if (auditLogs.length === 0) {
    logsEmptyState.classList.remove("hidden");
    logsContent.classList.add("hidden");
  } else {
    logsEmptyState.classList.add("hidden");
    logsContent.classList.remove("hidden");
    logsContent.innerHTML = auditLogs.map(log => {
      const isBlocked = log.status === "BLOCKED";
      const badgeClass = isBlocked ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700";
      return `
        <div class="bg-white border border-slate-200/80 rounded-2xl p-3 shadow-sm flex items-start justify-between text-xs space-y-1">
          <div class="space-y-0.5">
            <div class="flex items-center gap-1.5 font-bold text-slate-800">
              <span>${isBlocked ? '🛡️' : '📝'}</span>
              <span>${escapeHtml(log.action || "ACTION")}</span>
            </div>
            <div class="text-[11px] text-slate-500 font-mono">${escapeHtml(log.details || "")}</div>
          </div>
          <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded ${badgeClass}">
            ${escapeHtml(log.status || "LOG")}
          </span>
        </div>
      `;
    }).join("");
  }
}

// =====================================================================
// WebSocket Connection & Real-Time Events
// =====================================================================
function connectWebSocket() {
  if (ws) {
    try { ws.close(); } catch (e) {}
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  const wsUrl = `${protocol}//${host}/ws/client/${deviceId}?token=${encodeURIComponent(secretToken)}&last_seq_id=${lastSeqId}`;

  statusText.textContent = "CONNECTING...";
  statusDot.className = "w-2 h-2 rounded-full bg-amber-400 animate-pulse-subtle";

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("🟢 Connected to AgentRelay Gateway");
    startHeartbeatPing();
    syncApiKeysToBridge();
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
    updateDeviceStatusUI("OFFLINE", false);
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket Error:", err);
  };
}

function startHeartbeatPing() {
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      pingStartTime = Date.now();
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 10000);
}

function updateDeviceStatusUI(status, isOnline) {
  isDeviceOnline = isOnline;
  if (isOnline) {
    statusDot.className = "w-2 h-2 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50";
    statusText.textContent = "ONLINE";
    statusText.className = "text-emerald-700 text-[10px] font-bold";
    offlineBanner.classList.add("hidden");
  } else {
    statusDot.className = "w-2 h-2 rounded-full bg-rose-500 animate-pulse-subtle";
    statusText.textContent = "OFFLINE";
    statusText.className = "text-rose-700 text-[10px] font-bold";
    offlineBanner.classList.remove("hidden");
  }
}

function handleServerEvent(evt) {
  const eventType = evt.event_type;
  const payload = evt.payload || {};
  if (evt.seq_id) lastSeqId = Math.max(lastSeqId, evt.seq_id);

  if (evt.type === "pong" && pingStartTime > 0) {
    rttLatency = Math.max(12, Date.now() - pingStartTime);
    telemetryLatencyVal.textContent = `${rttLatency}ms`;
    return;
  }

  switch (eventType) {
    case "init":
      updateDeviceStatusUI(payload.status, payload.is_online);
      if (payload.projects && payload.projects.length) {
        projects = payload.projects;
        renderProjectsList();
      }
      if (payload.chat_sessions) chatSessions = payload.chat_sessions;
      if (payload.active_task) activeTask = payload.active_task;
      if (payload.recent_tasks) recentTasks = payload.recent_tasks;
      if (payload.terminal_logs) terminalLines = payload.terminal_logs;
      if (payload.audit_logs) auditLogs = payload.audit_logs;
      break;

    case "status":
      const isOnline = payload.status === "ONLINE" || payload.status === "WORKING" || payload.status === "IDLE";
      updateDeviceStatusUI(payload.status, isOnline);
      if (chatAgentStatus) {
        if (payload.status === "WORKING" || payload.status === "THINKING" || payload.status === "EXECUTING_TOOL") {
          chatAgentStatus.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-brand-500 animate-ping"></span><span>Working...</span>`;
          chatAgentStatus.className = "inline-flex items-center gap-1 text-[10px] font-mono text-brand-700 bg-brand-50 px-2 py-0.5 rounded-full border border-brand-200";
        } else {
          chatAgentStatus.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span><span>Ready</span>`;
          chatAgentStatus.className = "inline-flex items-center gap-1 text-[10px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200";
        }
      }
      break;

    case "projects_list":
      if (payload.projects) {
        projects = payload.projects;
        renderProjectsList();
      }
      break;

    case "task_update":
      activeTask = payload.status === "RUNNING" ? payload : null;
      if (payload.status === "RUNNING") recentTasks.unshift(payload);
      if (activeTab === "tasks") renderTasksView();
      break;

    case "terminal_line":
      if (payload.line) {
        terminalLines.push(payload.line);
        if (terminalLines.length > 300) terminalLines.shift();
        if (activeTab === "terminal") renderTerminalView();
      }
      break;

    case "audit_log":
      auditLogs.unshift(payload);
      if (auditLogs.length > 100) auditLogs.pop();
      if (activeTab === "logs") renderLogsView();
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

    case "action_result":
      renderActionResult(payload);
      break;

    case "error":
      renderSystemError(payload.error || "Execution error");
      finishAgentTurn();
      break;
  }
}

// =====================================================================
// Chat Bubbles & Streaming UI
// =====================================================================
function scrollToBottom() {
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

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
    currentAgentBubble.className = "flex flex-col space-y-2 max-w-[98%] w-full my-1";
    currentAgentBubble.innerHTML = `
      <div class="bg-card border border-slate-200/90 rounded-3xl p-4 space-y-3 shadow-card transition-all">
        <div class="flex items-center justify-between pb-2 border-b border-slate-100">
          <div class="flex items-center space-x-2 text-xs font-bold text-slate-800">
            <span>🤖</span>
            <span>Antigravity Agent</span>
          </div>
          <div class="agent-status-badge flex items-center gap-1 text-[10px] font-mono text-brand-700 bg-brand-50 px-2 py-0.5 rounded-full border border-brand-200">
            <span class="w-1.5 h-1.5 rounded-full bg-brand-500 animate-ping"></span>
            <span>Working...</span>
          </div>
        </div>

        <div class="thinking-container space-y-1"></div>
        <div class="tool-container space-y-1.5"></div>
        <div class="diff-container hidden"></div>
        <div class="token-container text-xs text-slate-700 leading-relaxed font-sans whitespace-pre-wrap"></div>
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
    thoughtBox.className = "group bg-slate-50/90 border border-slate-200/80 rounded-2xl p-2.5 text-xs text-slate-600";
    thoughtBox.open = true;
    thoughtBox.innerHTML = `
      <summary class="cursor-pointer font-bold text-slate-700 hover:text-slate-900 flex items-center gap-1.5 select-none text-[11px]">
        <span>💭</span> Thinking Process
      </summary>
      <div class="thought-content mt-1.5 pl-3 border-l-2 border-brand-500 text-[11px] font-mono text-slate-500 whitespace-pre-wrap leading-tight"></div>
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
  toolCard.className = "flex items-center justify-between bg-slate-50 border border-slate-200/80 rounded-2xl px-3 py-2 text-xs font-mono";
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

    if (token.includes("auth.ts") && currentDiffContainer && currentDiffContainer.classList.contains("hidden")) {
      currentDiffContainer.classList.remove("hidden");
      currentDiffContainer.innerHTML = `
        <div class="bg-slate-950 text-slate-100 rounded-2xl p-3 font-mono text-[11px] space-y-1 shadow-inner border border-slate-800">
          <div class="text-slate-400 text-[10px] pb-1 border-b border-slate-800 flex items-center justify-between">
            <span>src/auth.ts</span>
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
  const usageContainer = currentAgentBubble ? currentAgentBubble.querySelector(".usage-container") : null;
  if (!usageContainer) return;

  const total = usage.total_token_count || 0;
  const cached = usage.cached_content_token_count || 0;
  const savedPct = total > 0 && cached > 0 ? Math.round((cached / total) * 100) : 0;

  usageContainer.innerHTML = `
    <div class="flex items-center gap-2 text-[10px] font-mono text-slate-500 pt-1 border-t border-slate-100">
      <span>📊 ${total} tokens</span>
      <span>•</span>
      <span class="text-brand-600 font-medium">⚡ ${cached} cached (Saved ${savedPct}%)</span>
    </div>
  `;
  telemetryCacheVal.textContent = `⚡ ${cached} (${savedPct}%)`;
  scrollToBottom();
}

function finishAgentTurn() {
  if (currentStatusBadge) {
    currentStatusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span><span>Ready</span>`;
    currentStatusBadge.className = "agent-status-badge flex items-center gap-1 text-[10px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200";
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

function renderActionResult(payload) {
  const actionName = payload.action;
  const result = payload.result || {};
  const card = document.createElement("div");
  card.className = "bg-white border border-slate-200 rounded-2xl p-3.5 text-xs space-y-2 max-w-md mx-auto shadow-card";

  let title = "Action Complete";
  if (actionName === "auto_audit") { title = "🔍 Auto-Audit Complete"; }
  else if (actionName === "undo_changes") { title = "↩️ Changes Reverted"; }
  else if (actionName === "run_tests") { title = "🧪 Test Suite Results"; }

  card.innerHTML = `
    <div class="font-bold text-brand-700 flex items-center gap-1.5">
      <span>${title}</span>
    </div>
    <div class="text-slate-700 text-[11px] font-mono whitespace-pre-wrap bg-slate-50 p-2.5 rounded-xl border border-slate-200 max-h-48 overflow-y-auto">
      ${escapeHtml(result.summary || result.status || result.message || JSON.stringify(result, null, 2))}
    </div>
  `;
  chatFeed.appendChild(card);
  scrollToBottom();
}

function renderSystemError(errorMsg) {
  const card = document.createElement("div");
  card.className = "bg-rose-50 border border-rose-200 rounded-2xl p-3 text-xs text-rose-800 space-y-1 max-w-md mx-auto shadow-sm";
  card.innerHTML = `
    <div class="font-bold flex items-center gap-1.5 text-rose-700">
      <span>⚠️</span> Notice
    </div>
    <div class="text-rose-800/90 text-[11px]">${escapeHtml(errorMsg)}</div>
  `;
  chatFeed.appendChild(card);
  scrollToBottom();
}

// =====================================================================
// Event Listeners: Prompt Form & Quick Actions
// =====================================================================
promptForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = promptInput.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

  appendUserMessage(text);
  promptInput.value = "";
  btnSend.disabled = true;

  ws.send(JSON.stringify({
    type: "prompt",
    prompt: text,
    project_id: activeProject ? activeProject.id : "agent-relay",
    session_id: activeSession ? activeSession.id : "default",
    agent: activeProject ? (activeProject.agent || "antigravity") : "antigravity",
  }));
});

btnStop.addEventListener("click", () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "action", action: "cancel" }));
    finishAgentTurn();
    renderSystemError("Task execution was cancelled by user.");
  }
});

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

btnRunTests.addEventListener("click", () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "action", action: "run_tests" }));
  }
});

btnClearChat.addEventListener("click", () => {
  chatFeed.innerHTML = "";
});

btnReconnect.addEventListener("click", () => {
  connectWebSocket();
});

// Settings & API Key Helpers
function updateKeyBadges() {
  if (badgeGeminiKey) {
    badgeGeminiKey.textContent = geminiApiKey ? "✓ Configured" : "Not set";
    badgeGeminiKey.className = geminiApiKey ? "text-[9px] font-mono text-emerald-600 font-bold" : "text-[9px] font-mono text-slate-400";
  }
  if (badgeClaudeKey) {
    badgeClaudeKey.textContent = claudeApiKey ? "✓ Configured" : "Not set";
    badgeClaudeKey.className = claudeApiKey ? "text-[9px] font-mono text-emerald-600 font-bold" : "text-[9px] font-mono text-slate-400";
  }
  if (badgeCodexKey) {
    badgeCodexKey.textContent = codexApiKey ? "✓ Configured" : "Not set";
    badgeCodexKey.className = codexApiKey ? "text-[9px] font-mono text-emerald-600 font-bold" : "text-[9px] font-mono text-slate-400";
  }
}

function syncApiKeysToBridge() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "update_api_keys",
      keys: {
        gemini: geminiApiKey,
        claude: claudeApiKey,
        codex: codexApiKey,
      }
    }));
  }
}

// Settings Modal Handlers
btnSettings.addEventListener("click", () => {
  inputDeviceId.value = deviceId;
  inputSecretToken.value = secretToken;
  if (inputGeminiKey) inputGeminiKey.value = geminiApiKey;
  if (inputClaudeKey) inputClaudeKey.value = claudeApiKey;
  if (inputCodexKey) inputCodexKey.value = codexApiKey;
  updateKeyBadges();
  settingsModal.classList.remove("hidden");
});

btnCloseSettings.addEventListener("click", () => settingsModal.classList.add("hidden"));

btnSaveSettings.addEventListener("click", () => {
  deviceId = inputDeviceId.value.trim() || "my-pc";
  secretToken = inputSecretToken.value.trim() || "default_secret";
  geminiApiKey = inputGeminiKey ? inputGeminiKey.value.trim() : geminiApiKey;
  claudeApiKey = inputClaudeKey ? inputClaudeKey.value.trim() : claudeApiKey;
  codexApiKey = inputCodexKey ? inputCodexKey.value.trim() : codexApiKey;

  localStorage.setItem("agentrelay_device_id", deviceId);
  localStorage.setItem("agentrelay_token", secretToken);
  localStorage.setItem("agentrelay_gemini_key", geminiApiKey);
  localStorage.setItem("agentrelay_claude_key", claudeApiKey);
  localStorage.setItem("agentrelay_codex_key", codexApiKey);

  deviceNameDisplay.textContent = deviceId.toUpperCase();
  telemetryDevice.textContent = deviceId.toUpperCase();
  updateKeyBadges();
  settingsModal.classList.add("hidden");

  syncApiKeysToBridge();
  connectWebSocket();
});

// Utilities
function escapeHtml(str) {
  if (typeof str !== "string") str = JSON.stringify(str);
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatTimeAgo(ts) {
  if (!ts) return "Recently";
  const diffSec = Math.floor((Date.now() - ts) / 1000);
  if (diffSec < 60) return "Just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

// Initial Boot
inputDeviceId.value = deviceId;
inputSecretToken.value = secretToken;
if (inputGeminiKey) inputGeminiKey.value = geminiApiKey;
if (inputClaudeKey) inputClaudeKey.value = claudeApiKey;
if (inputCodexKey) inputCodexKey.value = codexApiKey;
deviceNameDisplay.textContent = deviceId.toUpperCase();
telemetryDevice.textContent = deviceId.toUpperCase();
updateKeyBadges();

renderProjectsList();
connectWebSocket();
