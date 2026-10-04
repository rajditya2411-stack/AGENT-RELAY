"""
AgentRelay v2.0 — Adapters Package
Connectors for Dev Coding and Frontier Assistant agents.
"""

from agentrelay.adapters.base_adapter import BaseAdapter
from agentrelay.adapters.dots_adapter import DotsAdapter
from agentrelay.adapters.grok_adapter import GrokAdapter
from agentrelay.adapters.muse_adapter import MuseAdapter

__all__ = [
    "BaseAdapter",
    "GrokAdapter",
    "DotsAdapter",
    "MuseAdapter",
]
