"""Per-run context: limits, approval tokens, policy state. Lives in-process for the run's lifetime
(interrupts/resumes keep it; the blackboard is the durable record)."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from backend.config import MAX_TOOL_CALLS_PER_AGENT, RUN_TIMEOUT_SECONDS, settings
from backend.core.blackboard import Blackboard, get_blackboard
from backend.core.trace import Tracer


@dataclass
class RunContext:
    run_id: str
    patient_id: str
    kind: str = "chat"
    started: float = field(default_factory=time.time)
    tool_calls: dict[str, int] = field(default_factory=dict)
    approval_tokens: dict[str, str] = field(default_factory=dict)  # proposal_id -> token
    policies: dict[str, Any] = field(default_factory=dict)  # goal_ref -> RelaxationPolicy
    offline: bool = field(default_factory=lambda: settings.offline)
    inject_fault: bool = field(default_factory=lambda: settings.inject_fault)
    fault_used: bool = False
    llm_calls: int = 0
    fallbacks: int = 0
    paused_s: float = 0.0  # time spent waiting for the human (not counted against the timeout)
    paused_at: float | None = None
    cache: dict[str, Any] = field(default_factory=dict)

    @property
    def bb(self) -> Blackboard:
        return get_blackboard(self.run_id, self.patient_id)

    @property
    def trace(self) -> Tracer:
        return Tracer(self.run_id)

    def budget_ok(self, agent: str) -> bool:
        return self.tool_calls.get(agent, 0) < MAX_TOOL_CALLS_PER_AGENT

    def count_tool(self, agent: str) -> int:
        self.tool_calls[agent] = self.tool_calls.get(agent, 0) + 1
        return self.tool_calls[agent]

    def elapsed(self) -> float:
        return time.time() - self.started - self.paused_s

    def timed_out(self) -> bool:
        return self.elapsed() > RUN_TIMEOUT_SECONDS

    def pause(self) -> None:
        if self.paused_at is None:
            self.paused_at = time.time()

    def unpause(self) -> None:
        if self.paused_at is not None:
            self.paused_s += time.time() - self.paused_at
            self.paused_at = None

    def issue_approval(self, proposal_id: str) -> str:
        tok = secrets.token_hex(8)
        self.approval_tokens[proposal_id] = tok
        return tok

    def check_approval(self, proposal_id: str, token: str | None) -> bool:
        return bool(token) and self.approval_tokens.get(proposal_id) == token


_ctx: dict[str, RunContext] = {}
_lock = threading.Lock()


def new_context(run_id: str, patient_id: str, kind: str = "chat") -> RunContext:
    with _lock:
        c = RunContext(run_id=run_id, patient_id=patient_id, kind=kind)
        _ctx[run_id] = c
        return c


def ctx(run_id: str) -> RunContext:
    with _lock:
        c = _ctx.get(run_id)
        if c is None:
            c = RunContext(run_id=run_id, patient_id="GUEST")
            _ctx[run_id] = c
        return c


def has_context(run_id: str) -> bool:
    return run_id in _ctx
