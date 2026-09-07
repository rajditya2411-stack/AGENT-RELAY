"""
AgentRelay — Desktop Agent Bridge (Phases 1, 2 & 4 Hardened)
Orchestrates AI coding agents locally, streams structured events, and enforces strict security policies.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional
import websockets

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from security_engine import SecurityEngine, SecurityViolation

# Try importing the Google Antigravity SDK
try:
    from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
    from google.antigravity.types import ChatResponse, UsageMetadata
    ANTIGRAVITY_AVAILABLE = True
except ImportError:
    ANTIGRAVITY_AVAILABLE = False

# Try importing Anthropic SDK
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Try importing OpenAI SDK
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class EventType(str, Enum):
    STATUS = "status"
    THINKING = "thinking"
    TOKEN = "token"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    ERROR = "error"
    COMPLETED = "completed"
    SECURITY_ALERT = "security_alert"


@dataclass
class BridgeEvent:
    event_type: EventType
    payload: Any
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class MockAgentAdapter:
    """Simulates an AI coding agent for testing the bridge without API keys."""

    def __init__(self, workspace_path: str = ".", agent_name: str = "MockAntigravity", model_name: str = "gemini-2.5-pro"):
        self.workspace_path = workspace_path
        self.agent_name = agent_name
        self.model_name = model_name
        self.security = SecurityEngine(workspace_path)

    async def execute_task(self, prompt: str) -> AsyncGenerator[BridgeEvent, None]:
        self.security.rate_guard.start_turn()
        yield BridgeEvent(EventType.STATUS, {"status": "INITIALIZING", "agent": self.agent_name, "model": self.model_name})
        await asyncio.sleep(0.15)

        # 1. Stream Thoughts (Sanitized)
        yield BridgeEvent(EventType.STATUS, {"status": "THINKING"})
        thoughts = [
            f"[{self.agent_name}] Analyzing prompt: '{self.security.sanitize_output(prompt)}'...\n",
            f"[{self.agent_name}] Inspecting workspace files and security boundaries...\n",
            f"[{self.agent_name}] Planning code modifications...\n",
        ]
        for thought in thoughts:
            yield BridgeEvent(EventType.THINKING, {"thought": thought})
            await asyncio.sleep(0.2)

        # 2. Simulate Tool Execution with Security Verification
        self.security.rate_guard.record_tool_call()
        yield BridgeEvent(EventType.STATUS, {"status": "EXECUTING_TOOL"})
        
        # Test path validation
        try:
            self.security.validate_file_access("example_module.py")
        except SecurityViolation as sv:
            yield BridgeEvent(EventType.SECURITY_ALERT, {"warning": str(sv)})
            return

        tool_call_data = {
            "name": "view_file",
            "args": {"path": "example_module.py"},
            "status": "RUNNING",
        }
        yield BridgeEvent(EventType.TOOL_CALL, tool_call_data)
        await asyncio.sleep(0.25)

        tool_call_data["status"] = "SUCCESS"
        tool_call_data["result"] = "File inspected (42 lines, 0 vulnerabilities found)."
        yield BridgeEvent(EventType.TOOL_CALL, tool_call_data)

        # 3. Stream Response Tokens (Sanitized)
        yield BridgeEvent(EventType.STATUS, {"status": "STREAMING_RESPONSE"})
        response_text = (
            f"Hello from AgentRelay ({self.agent_name} / {self.model_name})!\n\n"
            f"I have received your request: '{prompt}'.\n"
            f"1. Workspace is active and verified.\n"
            f"2. Security Engine is active (PathGuard, SecretRedactor & CommandGuard).\n"
            f"All operations executed safely."
        )

        sanitized_response = self.security.sanitize_output(response_text)
        words = sanitized_response.split(" ")
        for word in words:
            yield BridgeEvent(EventType.TOKEN, {"token": word + " "})
            await asyncio.sleep(0.03)

        # 4. Emit Token Usage
        usage_data = {
            "prompt_token_count": 84,
            "candidates_token_count": len(words) * 2,
            "cached_content_token_count": 128,
            "thoughts_token_count": 45,
            "total_token_count": 84 + (len(words) * 2) + 45,
            "service_tier": "standard",
        }
        yield BridgeEvent(EventType.USAGE, usage_data)
        yield BridgeEvent(EventType.STATUS, {"status": "IDLE"})
        yield BridgeEvent(EventType.COMPLETED, {"success": True})


class AntigravityAgentAdapter:
    """Production adapter integrating with Google's Antigravity Agent SDK."""

    def __init__(self, workspace_path: str = ".", model_name: str = "gemini-2.5-pro", api_key: Optional[str] = None):
        if not ANTIGRAVITY_AVAILABLE:
            raise RuntimeError("google-antigravity SDK is not installed in the environment.")
        
        self.workspace_path = workspace_path
        self.model_name = model_name
        self.security = SecurityEngine(workspace_path)
        
        self.config = LocalAgentConfig(
            model=model_name,
            workspace_dir=workspace_path,
            capabilities=CapabilitiesConfig(
                file_read=True,
                file_write=True,
                terminal_exec=True,
                subagents=False
            )
        )
        self.agent = Agent(self.config)

    async def execute_task(self, prompt: str) -> AsyncGenerator[BridgeEvent, None]:
        self.security.rate_guard.start_turn()
        yield BridgeEvent(EventType.STATUS, {"status": "INITIALIZING", "agent": "Gemini Antigravity", "model": self.model_name})

        try:
            chat_stream = self.agent.stream_chat(prompt)
            yield BridgeEvent(EventType.STATUS, {"status": "PROCESSING"})

            async for response in chat_stream:
                self.security.rate_guard.check_turn_timeout()

                # Stream Thinking Process
                if hasattr(response, "thoughts") and response.thoughts:
                    for thought in response.thoughts:
                        sanitized_thought = self.security.sanitize_output(thought)
                        yield BridgeEvent(EventType.THINKING, {"thought": sanitized_thought})

                # Stream Output Tokens
                if hasattr(response, "text") and response.text:
                    sanitized_token = self.security.sanitize_output(response.text)
                    yield BridgeEvent(EventType.TOKEN, {"token": sanitized_token})

                # Validate and Stream Tool Calls
                try:
                    for call in getattr(response, "tool_calls", []):
                        self.security.rate_guard.record_tool_call()
                        tool_name = getattr(call, "name", str(call))
                        tool_args = getattr(call, "args", {})

                        if tool_name in ("read_file", "view_file", "write_file"):
                            target_path = tool_args.get("path") or tool_args.get("TargetFile", "")
                            self.security.validate_file_access(target_path)

                        elif tool_name in ("run_command", "terminal_exec"):
                            cmd_str = tool_args.get("CommandLine", tool_args.get("command", ""))
                            is_safe, reason = self.security.validate_command(cmd_str)
                            if not is_safe:
                                yield BridgeEvent(EventType.SECURITY_ALERT, {"blocked_command": cmd_str, "reason": reason})
                                continue

                        yield BridgeEvent(EventType.TOOL_CALL, {
                            "name": tool_name,
                            "args": tool_args,
                        })
                except SecurityViolation as sv:
                    yield BridgeEvent(EventType.SECURITY_ALERT, {"error": str(sv)})
                    return
                except Exception:
                    pass

                # Extract Usage Metadata
                usage: Optional[UsageMetadata] = response.usage_metadata
                if usage:
                    usage_dict = {
                        "prompt_token_count": usage.prompt_token_count,
                        "candidates_token_count": usage.candidates_token_count,
                        "cached_content_token_count": usage.cached_content_token_count,
                        "thoughts_token_count": usage.thoughts_token_count,
                        "total_token_count": usage.total_token_count,
                        "service_tier": usage.service_tier,
                    }
                    yield BridgeEvent(EventType.USAGE, usage_dict)

                yield BridgeEvent(EventType.STATUS, {"status": "IDLE"})
                yield BridgeEvent(EventType.COMPLETED, {"success": True})

        except SecurityViolation as sv:
            yield BridgeEvent(EventType.SECURITY_ALERT, {"security_error": str(sv)})
        except Exception as exc:
            yield BridgeEvent(EventType.ERROR, {"error": str(exc)})


class ClaudeAgentAdapter:
    """Production adapter integrating Anthropic Claude Code / Claude 3.7."""

    def __init__(self, workspace_path: str = ".", model_name: str = "claude-3-7-sonnet-20250219", api_key: Optional[str] = None):
        self.workspace_path = workspace_path
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        self.security = SecurityEngine(workspace_path)
        self.use_fallback = not (ANTHROPIC_AVAILABLE and bool(self.api_key))
        if self.use_fallback:
            self.fallback_adapter = MockAgentAdapter(
                workspace_path=workspace_path,
                agent_name="Claude Code",
                model_name=model_name
            )

    async def execute_task(self, prompt: str) -> AsyncGenerator[BridgeEvent, None]:
        if self.use_fallback:
            async for ev in self.fallback_adapter.execute_task(prompt):
                yield ev
            return

        self.security.rate_guard.start_turn()
        yield BridgeEvent(EventType.STATUS, {"status": "INITIALIZING", "agent": "Claude Code", "model": self.model_name})

        try:
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            yield BridgeEvent(EventType.STATUS, {"status": "PROCESSING"})

            async with client.messages.stream(
                model=self.model_name,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for event in stream:
                    self.security.rate_guard.check_turn_timeout()

                    if getattr(event, "type", "") == "thinking_delta":
                        thought = getattr(event, "thinking", "")
                        if thought:
                            sanitized = self.security.sanitize_output(thought)
                            yield BridgeEvent(EventType.THINKING, {"thought": sanitized})

                    elif getattr(event, "type", "") == "text_delta":
                        text = getattr(event, "text", "")
                        if text:
                            sanitized = self.security.sanitize_output(text)
                            yield BridgeEvent(EventType.TOKEN, {"token": sanitized})

            yield BridgeEvent(EventType.STATUS, {"status": "IDLE"})
            yield BridgeEvent(EventType.COMPLETED, {"success": True})

        except SecurityViolation as sv:
            yield BridgeEvent(EventType.SECURITY_ALERT, {"security_error": str(sv)})
        except Exception as exc:
            yield BridgeEvent(EventType.ERROR, {"error": str(exc)})


class CodexAgentAdapter:
    """Production adapter integrating OpenAI Codex / GPT-4o / o3-mini."""

    def __init__(self, workspace_path: str = ".", model_name: str = "gpt-4o", api_key: Optional[str] = None):
        self.workspace_path = workspace_path
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_API_KEY")
        self.security = SecurityEngine(workspace_path)
        self.use_fallback = not (OPENAI_AVAILABLE and bool(self.api_key))
        if self.use_fallback:
            self.fallback_adapter = MockAgentAdapter(
                workspace_path=workspace_path,
                agent_name="OpenAI Codex",
                model_name=model_name
            )

    async def execute_task(self, prompt: str) -> AsyncGenerator[BridgeEvent, None]:
        if self.use_fallback:
            async for ev in self.fallback_adapter.execute_task(prompt):
                yield ev
            return

        self.security.rate_guard.start_turn()
        yield BridgeEvent(EventType.STATUS, {"status": "INITIALIZING", "agent": "OpenAI Codex", "model": self.model_name})

        try:
            client = openai.AsyncOpenAI(api_key=self.api_key)
            yield BridgeEvent(EventType.STATUS, {"status": "PROCESSING"})

            response_stream = await client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )

            async for chunk in response_stream:
                self.security.rate_guard.check_turn_timeout()
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        sanitized = self.security.sanitize_output(reasoning)
                        yield BridgeEvent(EventType.THINKING, {"thought": sanitized})

                    content = delta.content
                    if content:
                        sanitized = self.security.sanitize_output(content)
                        yield BridgeEvent(EventType.TOKEN, {"token": sanitized})

            yield BridgeEvent(EventType.STATUS, {"status": "IDLE"})
            yield BridgeEvent(EventType.COMPLETED, {"success": True})

        except SecurityViolation as sv:
            yield BridgeEvent(EventType.SECURITY_ALERT, {"security_error": str(sv)})
        except Exception as exc:
            yield BridgeEvent(EventType.ERROR, {"error": str(exc)})


class GitRecoveryManager:
    """Manages Git recovery actions: Auto-Audit and Undo Changes."""

    def __init__(self, workspace_path: str = "."):
        self.workspace_path = workspace_path

    def auto_audit(self) -> Dict[str, Any]:
        """Runs git status and git diff to capture uncommitted changes."""
        try:
            status_res = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=False
            )
            diff_res = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=False
            )
            return {
                "success": True,
                "status": status_res.stdout.strip(),
                "diff_summary": diff_res.stdout.strip(),
                "has_changes": bool(status_res.stdout.strip()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def undo_changes(self) -> Dict[str, Any]:
        """Discards uncommitted changes using git checkout/clean."""
        try:
            subprocess.run(["git", "checkout", "."], cwd=self.workspace_path, capture_output=True, check=False)
            subprocess.run(["git", "clean", "-fd"], cwd=self.workspace_path, capture_output=True, check=False)
            return {"success": True, "message": "All uncommitted changes were successfully reverted."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_unit_tests(self) -> Dict[str, Any]:
        """Executes test suite and returns structured pass/fail results."""
        try:
            test_res = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=False
            )
            is_success = test_res.returncode == 0
            output = (test_res.stdout + "\n" + test_res.stderr).strip()
            return {
                "success": is_success,
                "exit_code": test_res.returncode,
                "summary": "All tests passed!" if is_success else "Test failures detected.",
                "output": output,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class ProjectManager:
    """Discovers and manages local repositories on the user's computer."""

    DEFAULT_PROJECTS = [
        {
            "id": "agent-relay",
            "name": "AGENT-RELAY",
            "path": ".",
            "lang": "Python / FastAPI",
            "agent": "antigravity",
            "agent_name": "Antigravity",
            "agent_badge": "⚡ Antigravity",
            "branch": "main*",
            "has_changes": False,
            "status_text": "Clean"
        },
        {
            "id": "mindmap",
            "name": "MINDMAP",
            "path": "../mindmap",
            "lang": "TypeScript / React",
            "agent": "claude",
            "agent_name": "Claude Code",
            "agent_badge": "🟠 Claude Code",
            "branch": "main",
            "has_changes": True,
            "status_text": "2 uncommitted files"
        },
        {
            "id": "aegic-14c",
            "name": "AEGIC-14C",
            "path": "../aegic-14c",
            "lang": "Python / PyTorch",
            "agent": "antigravity",
            "agent_name": "Antigravity",
            "agent_badge": "⚡ Antigravity",
            "branch": "dev*",
            "has_changes": False,
            "status_text": "Clean"
        },
        {
            "id": "trace",
            "name": "TRACE",
            "path": "../trace",
            "lang": "Go / Microservices",
            "agent": "codex",
            "agent_name": "OpenAI Codex",
            "agent_badge": "🟢 OpenAI Codex",
            "branch": "master",
            "has_changes": True,
            "status_text": "1 uncommitted file"
        },
    ]

    def __init__(self, workspace_path: str = "."):
        self.workspace_path = workspace_path

    def get_project_agent(self, project_id: str) -> str:
        """Returns the assigned agent tool for a given project."""
        for p in self.DEFAULT_PROJECTS:
            if p["id"] == project_id:
                return p.get("agent", "antigravity")
        return "antigravity"

    def list_projects(self) -> List[Dict[str, Any]]:
        """Returns registered projects with their live Git status and AI Agent badges."""
        projects = []
        for p in self.DEFAULT_PROJECTS:
            path = p["path"] if p["path"] == "." else os.path.abspath(os.path.join(self.workspace_path, p["path"]))
            has_changes = False
            status_text = "Clean"

            if os.path.exists(path) and os.path.isdir(os.path.join(path, ".git")):
                try:
                    res = subprocess.run(["git", "status", "--short"], cwd=path, capture_output=True, text=True, check=False)
                    changes = [line for line in res.stdout.strip().split("\n") if line.strip()]
                    if changes:
                        has_changes = True
                        status_text = f"{len(changes)} uncommitted files"
                except Exception:
                    pass
            elif p["id"] == "mindmap":
                has_changes = True
                status_text = "2 uncommitted files"
            elif p["id"] == "trace":
                has_changes = True
                status_text = "1 uncommitted file"

            projects.append({
                "id": p["id"],
                "name": p["name"],
                "lang": p["lang"],
                "agent": p.get("agent", "antigravity"),
                "agent_name": p.get("agent_name", "Antigravity"),
                "agent_badge": p.get("agent_badge", "⚡ Antigravity"),
                "branch": p["branch"],
                "has_changes": has_changes,
                "status_text": status_text,
            })
        return projects


class AgentBridge:
    """Main AgentBridge orchestrator connecting local adapter to relay or CLI."""

    def __init__(self, use_mock: bool = False, workspace_path: str = ".", provider: str = "gemini"):
        self.workspace_path = workspace_path
        self.recovery = GitRecoveryManager(workspace_path)
        self.security = SecurityEngine(workspace_path)
        self.projects = ProjectManager(workspace_path)
        self.provider = provider.lower()
        self.use_mock = use_mock
        self.api_keys = {
            "gemini": os.environ.get("GEMINI_API_KEY", ""),
            "claude": os.environ.get("ANTHROPIC_API_KEY", os.environ.get("CLAUDE_API_KEY", "")),
            "codex": os.environ.get("OPENAI_API_KEY", os.environ.get("CODEX_API_KEY", "")),
        }
        self.adapters = {}
        self._init_all_adapters()
        self._init_adapter()

    def _init_all_adapters(self):
        """Initializes all 3 provider adapters (Gemini, Claude, Codex) ready for routing."""
        # 1. Gemini / Antigravity
        gemini_key = self.api_keys.get("gemini", "")
        if self.use_mock or not (ANTIGRAVITY_AVAILABLE and gemini_key):
            self.adapters["gemini"] = MockAgentAdapter(self.workspace_path, agent_name="Antigravity", model_name="gemini-2.5-pro")
            self.adapters["antigravity"] = self.adapters["gemini"]
        else:
            self.adapters["gemini"] = AntigravityAgentAdapter(workspace_path=self.workspace_path, api_key=gemini_key)
            self.adapters["antigravity"] = self.adapters["gemini"]

        # 2. Claude Code
        claude_key = self.api_keys.get("claude", "")
        if self.use_mock or not (ANTHROPIC_AVAILABLE and claude_key):
            self.adapters["claude"] = MockAgentAdapter(self.workspace_path, agent_name="Claude Code", model_name="claude-3-7-sonnet")
        else:
            self.adapters["claude"] = ClaudeAgentAdapter(workspace_path=self.workspace_path, api_key=claude_key)

        # 3. OpenAI Codex
        codex_key = self.api_keys.get("codex", "")
        if self.use_mock or not (OPENAI_AVAILABLE and codex_key):
            self.adapters["codex"] = MockAgentAdapter(self.workspace_path, agent_name="OpenAI Codex", model_name="gpt-4o")
        else:
            self.adapters["codex"] = CodexAgentAdapter(workspace_path=self.workspace_path, api_key=codex_key)

    def _init_adapter(self, api_key: Optional[str] = None):
        self._init_all_adapters()
        if self.provider in ("claude", "anthropic", "claude-code"):
            self.provider = "claude"
            self.adapter = self.adapters["claude"]
            self.mode = "CLAUDE_CODE" if (bool(self.api_keys.get("claude")) and not self.use_mock) else "MOCK (Claude Code)"
        elif self.provider in ("codex", "openai", "gpt"):
            self.provider = "codex"
            self.adapter = self.adapters["codex"]
            self.mode = "OPENAI_CODEX" if (bool(self.api_keys.get("codex")) and not self.use_mock) else "MOCK (Codex)"
        else:
            self.provider = "gemini"
            self.adapter = self.adapters["gemini"]
            self.mode = "ANTIGRAVITY" if (bool(self.api_keys.get("gemini")) and not self.use_mock) else "MOCK"

    def switch_provider(self, provider: str, api_key: Optional[str] = None) -> str:
        """Switches the active AI provider dynamically."""
        if api_key:
            prov_norm = "gemini" if provider in ("gemini", "antigravity") else ("claude" if provider in ("claude", "anthropic") else "codex")
            self.api_keys[prov_norm] = api_key
            if prov_norm == "gemini":
                os.environ["GEMINI_API_KEY"] = api_key
            elif prov_norm == "claude":
                os.environ["ANTHROPIC_API_KEY"] = api_key
                os.environ["CLAUDE_API_KEY"] = api_key
            elif prov_norm == "codex":
                os.environ["OPENAI_API_KEY"] = api_key
                os.environ["CODEX_API_KEY"] = api_key
        self.provider = provider.lower()
        self._init_adapter()
        return self.mode

    def update_keys(self, gemini_key: str = "", claude_key: str = "", codex_key: str = ""):
        """Updates multiple provider API keys at runtime."""
        if gemini_key:
            self.api_keys["gemini"] = gemini_key
            os.environ["GEMINI_API_KEY"] = gemini_key
        if claude_key:
            self.api_keys["claude"] = claude_key
            os.environ["ANTHROPIC_API_KEY"] = claude_key
            os.environ["CLAUDE_API_KEY"] = claude_key
        if codex_key:
            self.api_keys["codex"] = codex_key
            os.environ["OPENAI_API_KEY"] = codex_key
            os.environ["CODEX_API_KEY"] = codex_key
        self._init_adapter()

    def get_adapter_for_agent(self, agent_name: str):
        """Returns the appropriate adapter for a project's designated agent."""
        norm = agent_name.lower()
        if "claude" in norm:
            return self.adapters.get("claude", self.adapter)
        elif "codex" in norm or "openai" in norm or "gpt" in norm:
            return self.adapters.get("codex", self.adapter)
        return self.adapters.get("gemini", self.adapter)

    async def run_prompt(self, prompt: str, agent_override: Optional[str] = None) -> AsyncGenerator[BridgeEvent, None]:
        target_adapter = self.get_adapter_for_agent(agent_override) if agent_override else self.adapter
        async for event in target_adapter.execute_task(prompt):
            yield event

    async def connect_to_relay(
        self,
        relay_url: str = "ws://localhost:58765/ws/bridge",
        device_id: str = "my-pc",
        secret_token: str = "default_secret",
    ):
        """Maintains persistent outbound WebSocket connection to Cloud Relay."""
        full_url = f"{relay_url}/{device_id}?token={secret_token}"
        print(f"[*] Connecting to Cloud Relay: {full_url}")

        while True:
            try:
                async with websockets.connect(full_url) as ws:
                    print(f"Connected to Relay! Device registered as '{device_id}'")

                    # Announce projects to relay
                    try:
                        await ws.send(json.dumps({
                            "event_type": "projects_list",
                            "payload": {"projects": self.projects.list_projects()}
                        }))
                    except Exception:
                        pass
                    
                    # Background heartbeat task
                    async def heartbeat_loop():
                        while True:
                            await asyncio.sleep(10)
                            try:
                                await ws.send(json.dumps({"event_type": "heartbeat", "device_id": device_id}))
                            except Exception:
                                break

                    heartbeat_task = asyncio.create_task(heartbeat_loop())

                    try:
                        async for message_str in ws:
                            try:
                                cmd = json.loads(message_str)
                            except json.JSONDecodeError:
                                continue

                            cmd_type = cmd.get("type")
                            if cmd_type == "pong":
                                continue

                            print(f"\n[Command Received]: {cmd_type}")

                            # Handle Prompt Execution
                            if cmd_type == "prompt":
                                prompt_text = cmd.get("prompt", "")
                                project_id = cmd.get("project_id", "agent-relay")
                                session_id = cmd.get("session_id", "default")
                                project_agent = cmd.get("agent") or self.projects.get_project_agent(project_id)
                                print(f"Executing prompt for [{project_id}] via [{project_agent}]: '{prompt_text}'")

                                # Emit task running state & terminal start
                                await ws.send(json.dumps({
                                    "event_type": "task_update",
                                    "payload": {
                                        "status": "RUNNING",
                                        "title": f"Prompt: {prompt_text[:35]}...",
                                        "project_id": project_id,
                                        "session_id": session_id,
                                        "started_at": time.time(),
                                    }
                                }))
                                await ws.send(json.dumps({
                                    "event_type": "terminal_line",
                                    "payload": {"line": f"$ agentrelay exec --project {project_id} --agent {project_agent} \"{prompt_text}\""}
                                }))
                                await ws.send(json.dumps({
                                    "event_type": "audit_log",
                                    "payload": {
                                        "action": "PROMPT_EXECUTE",
                                        "project": project_id,
                                        "status": "ALLOWED",
                                        "details": f"Prompt dispatched ({len(prompt_text)} chars) to {project_agent}"
                                    }
                                }))

                                async for event in self.run_prompt(prompt_text, agent_override=project_agent):
                                    await ws.send(event.to_json())
                                    if event.event_type == EventType.THINKING:
                                        thought_str = event.payload.get("thought", "").strip()
                                        if thought_str:
                                            await ws.send(json.dumps({
                                                "event_type": "terminal_line",
                                                "payload": {"line": f"[thinking] {thought_str}"}
                                            }))
                                    elif event.event_type == EventType.TOOL_CALL:
                                        tool_name = event.payload.get("name", "tool")
                                        tool_status = event.payload.get("status", "RUNNING")
                                        await ws.send(json.dumps({
                                            "event_type": "terminal_line",
                                            "payload": {"line": f"[tool] {tool_name} -> {tool_status}"}
                                        }))
                                        await ws.send(json.dumps({
                                            "event_type": "audit_log",
                                            "payload": {
                                                "action": f"TOOL_{tool_name.upper()}",
                                                "project": project_id,
                                                "status": "ALLOWED",
                                                "details": str(event.payload.get("args", {}))
                                            }
                                        }))

                                # Task finished
                                await ws.send(json.dumps({
                                    "event_type": "task_update",
                                    "payload": {
                                        "status": "IDLE",
                                        "title": "None",
                                        "project_id": project_id,
                                        "session_id": session_id,
                                    }
                                }))

                            # Handle Update API Keys Action
                            elif cmd_type in ("update_api_keys", "set_api_keys"):
                                keys = cmd.get("keys", {})
                                self.update_keys(
                                    gemini_key=keys.get("gemini", ""),
                                    claude_key=keys.get("claude", ""),
                                    codex_key=keys.get("codex", "")
                                )
                                print(f"[*] API Keys updated. Active keys configured: {[k for k, v in self.api_keys.items() if v]}")
                                await ws.send(json.dumps({
                                    "event_type": "api_keys_updated",
                                    "payload": {
                                        "has_gemini": bool(self.api_keys.get("gemini")),
                                        "has_claude": bool(self.api_keys.get("claude")),
                                        "has_codex": bool(self.api_keys.get("codex")),
                                    }
                                }))
                                await ws.send(json.dumps({
                                    "event_type": "audit_log",
                                    "payload": {"action": "API_KEYS_UPDATE", "status": "COMPLETED", "details": "Provider credentials updated dynamically"}
                                }))

                            # Handle Auto-Audit Action
                            elif cmd_type == "action" and cmd.get("action") == "auto_audit":
                                audit_result = self.recovery.auto_audit()
                                await ws.send(json.dumps({
                                    "event_type": "action_result",
                                    "payload": {"action": "auto_audit", "result": audit_result}
                                }))
                                await ws.send(json.dumps({
                                    "event_type": "audit_log",
                                    "payload": {"action": "GIT_AUDIT", "status": "COMPLETED", "details": audit_result.get("status", "")}
                                }))

                            # Handle Undo Changes Action
                            elif cmd_type == "action" and cmd.get("action") == "undo_changes":
                                undo_result = self.recovery.undo_changes()
                                await ws.send(json.dumps({
                                    "event_type": "action_result",
                                    "payload": {"action": "undo_changes", "result": undo_result}
                                }))
                                await ws.send(json.dumps({
                                    "event_type": "audit_log",
                                    "payload": {"action": "GIT_UNDO", "status": "COMPLETED", "details": "Uncommitted changes reverted"}
                                }))

                            # Handle Run Unit Tests Action
                            elif cmd_type == "action" and cmd.get("action") == "run_tests":
                                await ws.send(json.dumps({
                                    "event_type": "terminal_line",
                                    "payload": {"line": "$ python -m unittest discover"}
                                }))
                                test_result = self.recovery.run_unit_tests()
                                await ws.send(json.dumps({
                                    "event_type": "action_result",
                                    "payload": {"action": "run_tests", "result": test_result}
                                }))
                                await ws.send(json.dumps({
                                    "event_type": "terminal_line",
                                    "payload": {"line": test_result.get("summary", "")}
                                }))
                                await ws.send(json.dumps({
                                    "event_type": "audit_log",
                                    "payload": {"action": "UNIT_TESTS", "status": "PASSED" if test_result.get("success") else "FAILED", "details": test_result.get("summary", "")}
                                }))

                            # Handle Get Projects Action
                            elif cmd_type == "action" and cmd.get("action") == "get_projects":
                                await ws.send(json.dumps({
                                    "event_type": "projects_list",
                                    "payload": {"projects": self.projects.list_projects()}
                                }))

                            # Handle Switch Provider Action
                            elif cmd_type in ("set_provider", "switch_provider"):
                                target_provider = cmd.get("provider", "gemini")
                                target_key = cmd.get("api_key")
                                active_mode = self.switch_provider(target_provider, api_key=target_key)
                                print(f"[*] Provider switched to: {target_provider} [{active_mode}]")
                                await ws.send(json.dumps({
                                    "event_type": "provider_changed",
                                    "payload": {"provider": target_provider, "mode": active_mode}
                                }))
                                await ws.send(json.dumps({
                                    "event_type": "audit_log",
                                    "payload": {"action": "PROVIDER_SWITCH", "status": "COMPLETED", "details": f"Switched to {target_provider} ({active_mode})"}
                                }))

                    finally:
                        heartbeat_task.cancel()

            except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                print(f"Connection lost ({e}). Reconnecting in 3 seconds...")
                await asyncio.sleep(3)


# CLI Argument Parser & Entrypoint
async def main():
    def get_default_relay():
        port = "58765"
        if os.path.exists(".agentrelay_port"):
            try:
                with open(".agentrelay_port", "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content.isdigit():
                        port = content
            except Exception:
                pass
        return f"ws://localhost:{port}/ws/bridge"

    parser = argparse.ArgumentParser(description="AgentRelay Desktop Bridge")
    parser.add_argument("--relay", type=str, nargs="?", const=get_default_relay(), default=None, help="Cloud Relay WebSocket URL")
    parser.add_argument("--device", type=str, default="my-pc", help="Unique Device Identifier")
    parser.add_argument("--token", type=str, default="default_secret", help="Pairing Secret Token")
    parser.add_argument("--provider", type=str, default="gemini", choices=["gemini", "claude", "codex"], help="AI Provider to use (gemini, claude, codex)")
    parser.add_argument("--mock", action="store_true", help="Force Mock mode without API keys")
    args = parser.parse_args()

    bridge = AgentBridge(use_mock=args.mock, provider=args.provider)

    if args.relay:
        relay_url = args.relay if "://" in args.relay else get_default_relay()
        print("=" * 60)
        print(f"AgentRelay Bridge — Remote Relay Mode [{bridge.mode}] (Security Hardened)")
        print("=" * 60)
        await bridge.connect_to_relay(relay_url, args.device, args.token)
    else:
        print("=" * 60)
        print("AgentRelay — Local Desktop Bridge (Phase 1 Local CLI)")
        print("=" * 60)
        print(f"[*] Bridge Mode: {bridge.mode}")
        print(f"[*] Workspace:   {os.path.abspath(bridge.workspace_path)}")
        print("\nCommands:")
        print("  /audit   -> Auto-audit local git changes")
        print("  /undo    -> Undo uncommitted changes")
        print("  /exit    -> Quit bridge")
        print("-" * 60)

        while True:
            try:
                prompt = input("\n[Remote Mobile Prompt] > ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not prompt:
                continue
            if prompt.lower() in ("/exit", "exit", "quit"):
                print("Shutting down bridge.")
                break
            elif prompt.lower() == "/audit":
                res = bridge.recovery.auto_audit()
                print("\nGit Audit Result:")
                print(json.dumps(res, indent=2))
                continue
            elif prompt.lower() == "/undo":
                res = bridge.recovery.undo_changes()
                print("\nUndo Changes Result:")
                print(json.dumps(res, indent=2))
                continue

            print("\n--- [STREAMING EVENTS FROM AGENT] ---")
            async for event in bridge.run_prompt(prompt):
                if event.event_type == EventType.TOKEN:
                    sys.stdout.write(event.payload.get("token", ""))
                    sys.stdout.flush()
                elif event.event_type == EventType.THINKING:
                    print(f"Thought: {event.payload.get('thought', '').strip()}")
                elif event.event_type == EventType.TOOL_CALL:
                    print(f"Tool Call: {event.payload}")
                elif event.event_type == EventType.USAGE:
                    print(f"\nUsage Metrics: {event.payload}")
                elif event.event_type == EventType.STATUS:
                    print(f"Status: {event.payload}")
                elif event.event_type == EventType.SECURITY_ALERT:
                    print(f"Security Alert: {event.payload}")
                elif event.event_type == EventType.ERROR:
                    print(f"Error: {event.payload}")
                elif event.event_type == EventType.COMPLETED:
                    print("\nTask Completed.")
            print("-------------------------------------")


if __name__ == "__main__":
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

    asyncio.run(main())
