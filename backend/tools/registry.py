"""Tool registry: every tool call goes through `call_tool`, which enforces
  * per-agent tool permissions (an agent can only call the tools in its own tool set)
  * the per-agent budget (MAX_TOOL_CALLS_PER_AGENT)
  * argument validation (pydantic)
and emits `tool_call` / `tool_result` trace events (with the agent's stated reason)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from backend.config import MAX_TOOL_CALLS_PER_AGENT
from backend.core.context import RunContext


@dataclass
class ToolSpec:
    name: str
    fn: Callable[..., dict]
    args: type[BaseModel]
    description: str
    gated: bool = False


TOOLS: dict[str, ToolSpec] = {}

AGENT_TOOLS: dict[str, list[str]] = {
    "supervisor": ["read_blackboard", "write_blackboard", "dispatch"],
    "triage": ["emergency_screen", "classify_symptoms", "get_specialty_info"],
    "scheduling": ["search_doctors", "get_availability", "find_joint_slots", "relax_constraint", "hold_slot",
                   "release_hold", "book_slot", "book_joint", "reschedule_appointment", "add_to_waitlist"],
    "memory": ["recall_memory", "get_visit_history", "get_patient_profile", "save_memory"],
    "billing": ["get_fee", "check_insurance", "estimate_cost", "get_patient_appointments"],
    "critic": ["verify_ids_exist", "verify_slot_free", "compare_to_original_request"],
    "notification": ["send_notification"],
    "event_watcher": ["cancel_doctor_block", "get_affected_appointments", "find_alternatives", "hold_slot",
                      "release_hold", "send_notification", "offer_to_waitlist", "recall_memory",
                      "get_patient_profile", "verify_slot_free", "reschedule_appointment", "book_slot",
                      "estimate_cost"],
}


def tool(name: str, args: type[BaseModel], description: str, gated: bool = False):
    def deco(fn):
        TOOLS[name] = ToolSpec(name=name, fn=fn, args=args, description=description, gated=gated)
        return fn

    return deco


def _short(d: dict, n: int = 140) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in d.items() if v not in (None, [], "", {}))
    return s if len(s) <= n else s[: n - 1] + "…"


def call_tool(c: RunContext, agent: str, name: str, args: dict | None = None, reason: str = "") -> dict:
    args = dict(args or {})
    args.pop("reason", None)
    spec = TOOLS.get(name)
    if spec is None:
        res = {"ok": False, "error": f"Unknown tool '{name}'."}
        c.trace(agent, "error", res["error"], {"tool": name})
        return res
    if name not in AGENT_TOOLS.get(agent, []):
        res = {"ok": False, "error": f"Permission denied: agent '{agent}' may not call '{name}'."}
        c.trace(agent, "error", res["error"], {"tool": name})
        return res
    if not c.budget_ok(agent):
        res = {"ok": False, "error": f"Tool budget exhausted ({MAX_TOOL_CALLS_PER_AGENT} calls for {agent}). Stop and report honestly."}
        c.trace(agent, "error", res["error"], {"tool": name, "limit": MAX_TOOL_CALLS_PER_AGENT})
        return res
    n = c.count_tool(agent)
    try:
        parsed = spec.args(**args)
    except ValidationError as e:
        res = {"ok": False, "error": f"Invalid arguments for {name}: {e.errors()[0].get('msg')} ({e.errors()[0].get('loc')})"}
        c.trace(agent, "tool_call", f"{name}({_short(args)})", {"tool": name, "args": args, "reason": reason, "n": n})
        c.trace(agent, "tool_result", res["error"], {"tool": name, "ok": False, "result": res})
        return res
    kw = parsed.model_dump()
    c.trace(agent, "tool_call", f"{name}({_short(kw)})" + (f"  ← why: {reason}" if reason else ""),
            {"tool": name, "args": kw, "reason": reason, "n": n, "gated": spec.gated})
    try:
        res = spec.fn(c, **kw)
    except Exception as e:  # noqa: BLE001 - a tool must never crash the agent
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    summary = res.get("summary") or res.get("error") or ("ok" if res.get("ok") else "failed")
    c.trace(agent, "tool_result", f"{name} → {summary}", {"tool": name, "ok": res.get("ok", False), "result": res})
    return res


def openai_tool_schemas(agent: str, exclude: tuple[str, ...] = ()) -> list[dict]:
    """JSON schemas for LLM tool-calling (bind_tools). Adds a `reason` arg so the model explains itself."""
    out = []
    for n in AGENT_TOOLS.get(agent, []):
        if n in exclude or n not in TOOLS:
            continue
        spec = TOOLS[n]
        schema = spec.args.model_json_schema()
        schema.setdefault("properties", {})["reason"] = {
            "type": "string", "description": "One short sentence: why you are calling this tool now."}
        schema.pop("title", None)
        out.append({"type": "function", "function": {"name": n, "description": spec.description, "parameters": schema}})
    return out


def describe_tools(agent: str) -> list[dict[str, Any]]:
    return [{"name": n, "description": TOOLS[n].description, "gated": TOOLS[n].gated}
            for n in AGENT_TOOLS.get(agent, []) if n in TOOLS]
