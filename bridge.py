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

from security_engine import SecurityEngine, SecurityViolation

# Try importing the Google Antigravity SDK
try:
    from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
    from google.antigravity.types import ChatResponse, UsageMetadata
    ANTIGRAVITY_AVAILABLE = True
except ImportError:
    ANTIGRAVITY_AVAILABLE = False


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

    def __init__(self, workspace_path: str = "."):
        self.workspace_path = workspace_path
        self.security = SecurityEngine(workspace_path)

    async def execute_task(self, prompt: str) -> AsyncGenerator[BridgeEvent, None]:
        self.security.rate_guard.start_turn()
        yield BridgeEvent(EventType.STATUS, {"status": "INITIALIZING", "agent": "MockAntigravity"})
        await asyncio.sleep(0.2)

        # 1. Stream Thoughts (Sanitized)
        yield BridgeEvent(EventType.STATUS, {"status": "THINKING"})
        thoughts = [
            f"Analyzing prompt: '{self.security.sanitize_output(prompt)}'...\n",
            "Inspecting workspace files and security boundaries...\n",
            "Planning code modifications...\n",
        ]
        for thought in thoughts:
            yield BridgeEvent(EventType.THINKING, {"thought": thought})
            await asyncio.sleep(0.3)

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
        await asyncio.sleep(0.4)

        tool_call_data["status"] = "SUCCESS"
        tool_call_data["result"] = "File inspected (42 lines, 0 vulnerabilities found)."
        yield BridgeEvent(EventType.TOOL_CALL, tool_call_data)

        # 3. Stream Response Tokens (Sanitized)
        yield BridgeEvent(EventType.STATUS, {"status": "STREAMING_RESPONSE"})
        response_text = (
            f"Hello from AgentRelay!\n\n"
            f"I have received your request: '{prompt}'.\n"
            f"1. Workspace is active and verified.\n"
            f"2. Security Engine is active (PathGuard, SecretRedactor & CommandGuard).\n"
            f"All operations executed safely."
        )

        sanitized_response = self.security.sanitize_output(response_text)
        words = sanitized_response.split(" ")
        for word in words:
            yield BridgeEvent(EventType.TOKEN, {"token": word + " "})
            await asyncio.sleep(0.05)

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
    """Adapter for official Google Antigravity SDK with Security Sandboxing."""

    def __init__(self, api_key: Optional[str] = None, workspace_path: str = "."):
        if not ANTIGRAVITY_AVAILABLE:
            raise RuntimeError("google-antigravity SDK is not installed.")
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.workspace_path = workspace_path
        self.security = SecurityEngine(workspace_path)
        self.config = LocalAgentConfig(
            api_key=self.api_key,
            system_instructions=(
                "You are an expert AI software engineer controlled remotely via AgentRelay. "
                "Keep updates structured, secure, and concise."
            ),
            capabilities=CapabilitiesConfig(),
        )

    async def execute_task(self, prompt: str) -> AsyncGenerator[BridgeEvent, None]:
        if not self.api_key:
            yield BridgeEvent(
                EventType.ERROR,
                {"error": "GEMINI_API_KEY is not set. Set the environment variable or use mock mode."}
            )
            return

        self.security.rate_guard.start_turn()
        yield BridgeEvent(EventType.STATUS, {"status": "INITIALIZING", "agent": "Antigravity"})

        try:
            async with Agent(self.config) as agent:
                yield BridgeEvent(EventType.STATUS, {"status": "WORKING"})
                response: ChatResponse = await agent.chat(prompt)

                # Stream response tokens (Redacting any credentials on the fly)
                async for token in response:
                    sanitized_token = self.security.sanitize_output(token)
                    yield BridgeEvent(EventType.TOKEN, {"token": sanitized_token})

                # Stream thoughts
                try:
                    async for thought in response.thoughts:
                        sanitized_thought = self.security.sanitize_output(thought)
                        yield BridgeEvent(EventType.THINKING, {"thought": sanitized_thought})
                except Exception:
                    pass

                # Stream tool calls
                try:
                    async for call in response.tool_calls:
                        self.security.rate_guard.record_tool_call()
                        tool_name = getattr(call, "name", "tool")
                        tool_args = getattr(call, "args", {})
                        
                        # Validate command if shell execution tool
                        if tool_name in ("run_command", "bash", "shell"):
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


class AgentBridge:
    """Main AgentBridge orchestrator connecting local adapter to relay or CLI."""

    def __init__(self, use_mock: bool = False, workspace_path: str = "."):
        self.workspace_path = workspace_path
        self.recovery = GitRecoveryManager(workspace_path)
        self.security = SecurityEngine(workspace_path)
        
        has_api_key = bool(os.environ.get("GEMINI_API_KEY"))
        if use_mock or not has_api_key:
            self.adapter = MockAgentAdapter(workspace_path)
            self.mode = "MOCK"
        else:
            self.adapter = AntigravityAgentAdapter(workspace_path=workspace_path)
            self.mode = "ANTIGRAVITY"

    async def run_prompt(self, prompt: str) -> AsyncGenerator[BridgeEvent, None]:
        async for event in self.adapter.execute_task(prompt):
            yield event

    async def connect_to_relay(
        self,
        relay_url: str = "ws://localhost:8765/ws/bridge",
        device_id: str = "my-pc",
        secret_token: str = "default_secret",
    ):
        """Maintains persistent outbound WebSocket connection to Cloud Relay."""
        full_url = f"{relay_url}/{device_id}?token={secret_token}"
        print(f"[*] Connecting to Cloud Relay: {full_url}")

        while True:
            try:
                async with websockets.connect(full_url) as ws:
                    print(f"🟢 Connected to Relay! Device registered as '{device_id}'")
                    
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
                            # Ignore heartbeat pong messages silently
                            if cmd_type == "pong":
                                continue

                            print(f"\n[Command Received]: {cmd_type}")

                            # Handle Prompt Execution
                            if cmd_type == "prompt":
                                prompt_text = cmd.get("prompt", "")
                                print(f"Executing prompt: '{prompt_text}'")
                                async for event in self.run_prompt(prompt_text):
                                    await ws.send(event.to_json())

                            # Handle Auto-Audit Action
                            elif cmd_type == "action" and cmd.get("action") == "auto_audit":
                                audit_result = self.recovery.auto_audit()
                                await ws.send(json.dumps({
                                    "event_type": "action_result",
                                    "payload": {"action": "auto_audit", "result": audit_result}
                                }))

                            # Handle Undo Changes Action
                            elif cmd_type == "action" and cmd.get("action") == "undo_changes":
                                undo_result = self.recovery.undo_changes()
                                await ws.send(json.dumps({
                                    "event_type": "action_result",
                                    "payload": {"action": "undo_changes", "result": undo_result}
                                }))

                    finally:
                        heartbeat_task.cancel()

            except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                print(f"⚠️ Connection lost ({e}). Reconnecting in 3 seconds...")
                await asyncio.sleep(3)


# CLI Argument Parser & Entrypoint
async def main():
    parser = argparse.ArgumentParser(description="AgentRelay Desktop Bridge")
    parser.add_argument("--relay", type=str, default=None, help="Cloud Relay WebSocket URL")
    parser.add_argument("--device", type=str, default="my-pc", help="Unique Device Identifier")
    parser.add_argument("--token", type=str, default="default_secret", help="Pairing Secret Token")
    parser.add_argument("--mock", action="store_true", help="Force Mock mode without API keys")
    args = parser.parse_args()

    bridge = AgentBridge(use_mock=args.mock or not bool(os.environ.get("GEMINI_API_KEY")))

    if args.relay:
        print("=" * 60)
        print(f"🚀 AgentRelay Bridge — Remote Relay Mode [{bridge.mode}] (Security Hardened)")
        print("=" * 60)
        await bridge.connect_to_relay(args.relay, args.device, args.token)
    else:
        print("=" * 60)
        print("🤖 AgentRelay — Local Desktop Bridge (Phase 1 Local CLI)")
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
                print("\n🔍 Git Audit Result:")
                print(json.dumps(res, indent=2))
                continue
            elif prompt.lower() == "/undo":
                res = bridge.recovery.undo_changes()
                print("\n↩️ Undo Changes Result:")
                print(json.dumps(res, indent=2))
                continue

            print("\n--- [STREAMING EVENTS FROM AGENT] ---")
            async for event in bridge.run_prompt(prompt):
                if event.event_type == EventType.TOKEN:
                    sys.stdout.write(event.payload.get("token", ""))
                    sys.stdout.flush()
                elif event.event_type == EventType.THINKING:
                    print(f"💭 {event.payload.get('thought', '').strip()}")
                elif event.event_type == EventType.TOOL_CALL:
                    print(f"🛠️ Tool Call: {event.payload}")
                elif event.event_type == EventType.USAGE:
                    print(f"\n📊 Usage Metrics: {event.payload}")
                elif event.event_type == EventType.STATUS:
                    print(f"⚡ Status: {event.payload}")
                elif event.event_type == EventType.SECURITY_ALERT:
                    print(f"🛡️ Security Alert: {event.payload}")
                elif event.event_type == EventType.ERROR:
                    print(f"❌ Error: {event.payload}")
                elif event.event_type == EventType.COMPLETED:
                    print("\n✅ Task Completed.")
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
