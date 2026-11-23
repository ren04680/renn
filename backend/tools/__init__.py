"""Importing this package registers every tool in the registry."""
from backend.tools import billing, booking, doctors, memory_tools, notify, policy, triage_tools, verify  # noqa: F401
from backend.tools.registry import AGENT_TOOLS, TOOLS, call_tool  # noqa: F401
