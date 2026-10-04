"""
AgentRelay v2.0 — Execution Rate Guardrail
Protects against runaway agent loops and infinite tool executions.
"""

import time
from agentrelay.guardrails.path_guard import SecurityViolation


class ExecutionRateGuard:
    """Protects against runaway agent loops and infinite tool executions."""

    def __init__(self, max_tool_calls_per_turn: int = 25, turn_timeout_seconds: float = 300.0):
        self.max_tool_calls = max_tool_calls_per_turn
        self.turn_timeout = turn_timeout_seconds
        self.tool_call_count = 0
        self.turn_start_time = 0.0

    def start_turn(self):
        self.tool_call_count = 0
        self.turn_start_time = time.time()

    def record_tool_call(self):
        self.tool_call_count += 1
        # Check loop limit
        if self.tool_call_count > self.max_tool_calls:
            raise SecurityViolation(
                f"Runaway Loop Prevention: Exceeded max allowed tool calls ({self.max_tool_calls}) in a single turn."
            )
        # Check turn timeout
        elapsed = time.time() - self.turn_start_time
        if elapsed > self.turn_timeout:
            raise SecurityViolation(
                f"Execution Timeout: Task exceeded maximum allowed duration ({self.turn_timeout}s)."
            )
