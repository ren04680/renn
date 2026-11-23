"""Unit 4 — Blackboard architecture.

A typed shared workspace. Agents never call each other directly: they read the blackboard and
write their results to it; the Supervisor reads it to decide who acts next. Every write is
recorded as {agent, ts, section, content}, persisted to SQLite (audit trail + UI viewer) and
emitted as a `blackboard_write` trace event.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.core.trace import bus

Status = Literal["pending", "running", "done", "failed", "skipped", "blocked"]
SECTIONS = ("goal", "subtasks", "facts", "proposals", "critic_verdicts", "decisions", "events")


class Subtask(BaseModel):
    id: str
    title: str
    kind: str  # recall|triage|gap_check|schedule|cost|verify|approve|book|notify|remember|billing_answer|...
    owner: str  # agent name
    status: Status = "pending"
    depends_on: list[str] = Field(default_factory=list)
    goal_ref: str | None = None  # which goal (G1/G2) for multi-goal requests
    params: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    attempts: int = 0


class Write(BaseModel):
    agent: str
    ts: float
    section: str
    content: Any


class Blackboard(BaseModel):
    run_id: str
    patient_id: str | None = None
    goal: str = ""
    subtasks: list[Subtask] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    proposals: list[dict[str, Any]] = Field(default_factory=list)
    critic_verdicts: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    writes: list[Write] = Field(default_factory=list)

    # ------------------------------------------------------------------ writes
    def write(self, agent: str, section: str, content: Any, msg: str | None = None, persist: bool = True) -> None:
        assert section in SECTIONS, section
        if section == "goal":
            self.goal = str(content)
        elif section == "subtasks":
            items = content if isinstance(content, list) else [content]
            for it in items:
                st = it if isinstance(it, Subtask) else Subtask(**it) if "title" in it else None
                if st is not None and not any(s.id == st.id for s in self.subtasks):
                    self.subtasks.append(st)
                else:
                    upd = it if isinstance(it, dict) else it.model_dump()
                    for s in self.subtasks:
                        if s.id == upd["id"]:
                            for k, v in upd.items():
                                if k != "id":
                                    setattr(s, k, v)
        elif section == "facts":
            self.facts.update(content)
        else:
            getattr(self, section).append(content)
        w = Write(agent=agent, ts=time.time(), section=section,
                  content=content.model_dump() if hasattr(content, "model_dump") else content)
        self.writes.append(w)
        if persist:
            _persist(self.run_id, w)
        summary = msg or _summarise(section, content)
        bus.emit(self.run_id, agent, "blackboard_write", summary, {"section": section, "content": w.content})

    # ------------------------------------------------------------------ helpers
    def set_status(self, agent: str, sid: str, status: Status, result: dict | None = None, msg: str | None = None) -> None:
        upd: dict[str, Any] = {"id": sid, "status": status}
        if result is not None:
            upd["result"] = result
        st = self.get(sid)
        if st and status == "running":
            upd["attempts"] = st.attempts + 1
        self.write(agent, "subtasks", upd, msg or f"subtask {sid} → {status}")

    def get(self, sid: str) -> Subtask | None:
        return next((s for s in self.subtasks if s.id == sid), None)

    def by_kind(self, kind: str, goal_ref: str | None = None) -> list[Subtask]:
        return [s for s in self.subtasks if s.kind == kind and (goal_ref is None or s.goal_ref == goal_ref)]

    def ready(self) -> list[Subtask]:
        done = {s.id for s in self.subtasks if s.status in ("done", "skipped")}
        return [s for s in self.subtasks if s.status == "pending" and all(d in done for d in s.depends_on)]

    def view(self) -> dict:
        d = self.model_dump()
        d["writes"] = [w.model_dump() for w in self.writes[-300:]]
        return d


def _summarise(section: str, content: Any) -> str:
    if section == "goal":
        return f"goal = {str(content)[:120]}"
    if section == "subtasks":
        items = content if isinstance(content, list) else [content]
        if items and isinstance(items[0], Subtask):
            return f"{len(items)} subtask(s) planned: " + ", ".join(f"{s.id}:{s.kind}" for s in items)
        if items and isinstance(items[0], dict):
            return ", ".join(f"{i.get('id')} → {i.get('status', 'updated')}" for i in items)
    if section == "facts":
        return "facts += " + ", ".join(content.keys())
    return f"{section} += 1"


def _persist(run_id: str, w: Write) -> None:
    from backend.db.models import BlackboardWrite
    from backend.db.session import get_session

    try:
        with get_session() as s:
            s.add(BlackboardWrite(run_id=run_id, agent=w.agent, ts=w.ts, section=w.section,
                                  content=json.dumps(w.content, default=str)))
    except Exception:  # never let audit persistence break a run
        pass


_registry: dict[str, Blackboard] = {}
_lock = threading.Lock()


def get_blackboard(run_id: str, patient_id: str | None = None) -> Blackboard:
    with _lock:
        bb = _registry.get(run_id)
        if bb is None:
            bb = _load(run_id) or Blackboard(run_id=run_id, patient_id=patient_id)
            _registry[run_id] = bb
        return bb


def drop_blackboard(run_id: str) -> None:
    with _lock:
        _registry.pop(run_id, None)


def _load(run_id: str) -> Blackboard | None:
    """Rebuild a blackboard by replaying its persisted writes (e.g. after a server restart)."""
    from backend.db.models import BlackboardWrite
    from backend.db.session import get_session

    try:
        with get_session() as s:
            rows = s.query(BlackboardWrite).filter_by(run_id=run_id).order_by(BlackboardWrite.id).all()
            data = [(r.agent, r.ts, r.section, json.loads(r.content)) for r in rows]
    except Exception:
        return None
    if not data:
        return None
    bb = Blackboard(run_id=run_id)
    for agent, ts, section, content in data:
        _apply_silent(bb, agent, ts, section, content)
    return bb


def _apply_silent(bb: Blackboard, agent: str, ts: float, section: str, content: Any) -> None:
    if section == "goal":
        bb.goal = str(content)
    elif section == "subtasks":
        for it in content if isinstance(content, list) else [content]:
            if "title" in it and not bb.get(it["id"]):
                bb.subtasks.append(Subtask(**it))
            else:
                st = bb.get(it["id"])
                if st:
                    for k, v in it.items():
                        if k != "id":
                            setattr(st, k, v)
    elif section == "facts":
        bb.facts.update(content)
    else:
        getattr(bb, section).append(content)
    bb.writes.append(Write(agent=agent, ts=ts, section=section, content=content))


def list_runs_with_blackboards(limit: int = 30) -> list[str]:
    with _lock:
        return list(_registry.keys())[-limit:]
