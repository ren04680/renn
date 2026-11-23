"""Structured trace events: {run_id, ts, agent, type, payload, msg, seq}.

- kept in memory (global sequence) so the API can stream them over SSE
- appended to logs/run_<id>.jsonl
- optionally echoed to the CLI as `[agent] message` (same style as the original trace)
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from backend.config import LOGS_DIR

EVENT_TYPES = {
    "thought", "tool_call", "tool_result", "blackboard_write", "memory_hit", "relaxation",
    "critic_verdict", "approval_request", "decision", "notification", "event_trigger", "error",
    "fallback", "run_status", "message", "offer",
}

AGENTS = ["supervisor", "triage", "scheduling", "memory", "billing", "critic", "notification",
          "event_watcher", "guardrail", "human", "system"]

_COLORS = {
    "supervisor": "\033[95m", "triage": "\033[91m", "scheduling": "\033[94m", "memory": "\033[92m",
    "billing": "\033[93m", "critic": "\033[96m", "notification": "\033[36m", "event_watcher": "\033[35m",
    "guardrail": "\033[31m", "human": "\033[97m", "system": "\033[90m",
}


class TraceBus:
    def __init__(self, max_events: int = 50000) -> None:
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._seq = 0
        self.max_events = max_events
        self.echo = False  # CLI printing
        self.echo_types: set[str] | None = None

    def emit(self, run_id: str, agent: str, type_: str, msg: str = "", payload: Any = None) -> dict:
        assert type_ in EVENT_TYPES, type_
        with self._lock:
            self._seq += 1
            ev = {
                "seq": self._seq, "run_id": run_id, "ts": round(time.time(), 3), "agent": agent,
                "type": type_, "msg": msg, "payload": _jsonable(payload),
            }
            self._events.append(ev)
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events // 2:]
        try:
            with open(LOGS_DIR / f"run_{run_id}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except OSError:
            pass
        if self.echo and (self.echo_types is None or type_ in self.echo_types):
            c = _COLORS.get(agent, "")
            tag = f"{type_}" if type_ not in ("thought", "decision") else ""
            print(f"{c}[{agent}]\033[0m {('(' + tag + ') ') if tag else ''}{msg}", flush=True)
        return ev

    def since(self, seq: int, run_id: str | None = None, limit: int = 1000) -> list[dict]:
        with self._lock:
            evs = [e for e in self._events if e["seq"] > seq]
        if run_id:
            evs = [e for e in evs if e["run_id"] == run_id]
        return evs[:limit]

    def for_run(self, run_id: str) -> list[dict]:
        with self._lock:
            return [e for e in self._events if e["run_id"] == run_id]

    @property
    def last_seq(self) -> int:
        return self._seq

    def clear(self) -> None:
        with self._lock:
            self._events = []


def _jsonable(x: Any) -> Any:
    if x is None or isinstance(x, (str, int, float, bool)):
        return x
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_jsonable(v) for v in x]
    if hasattr(x, "model_dump"):
        return _jsonable(x.model_dump())
    return str(x)


bus = TraceBus()


class Tracer:
    """Convenience wrapper bound to one run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def __call__(self, agent: str, type_: str, msg: str = "", payload: Any = None) -> dict:
        return bus.emit(self.run_id, agent, type_, msg, payload)

    def thought(self, agent: str, msg: str, payload: Any = None) -> dict:
        return bus.emit(self.run_id, agent, "thought", msg, payload)

    def decision(self, agent: str, msg: str, payload: Any = None) -> dict:
        return bus.emit(self.run_id, agent, "decision", msg, payload)
