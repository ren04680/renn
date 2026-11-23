"""Run lifecycle: start a chat run, resume after an interrupt (clarification / approval), persist
RunRecords. Used by the CLI, the scenario runner, the tests and the API (same code path)."""
from __future__ import annotations

import json
import threading
import time
import traceback
import uuid

from langgraph.types import Command

from backend.core.context import ctx, has_context, new_context
from backend.core.graph import get_graph
from backend.core.trace import bus
from backend.db.models import RunRecord
from backend.db.session import get_session

_locks: dict[str, threading.Lock] = {}
_glock = threading.Lock()


def _lock_for(run_id: str) -> threading.Lock:
    with _glock:
        return _locks.setdefault(run_id, threading.Lock())


def _cfg(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 200}


def _record(run_id: str, **kw) -> None:
    try:
        with get_session() as s:
            r = s.get(RunRecord, run_id)
            if r is None:
                r = RunRecord(run_id=run_id, created_at=time.time(), updated_at=time.time())
                s.add(r)
            for k, v in kw.items():
                setattr(r, k, v if not isinstance(v, (dict, list)) else json.dumps(v, default=str))
            r.updated_at = time.time()
    except Exception:
        pass


def _package(run_id: str, result: dict) -> dict:
    c = ctx(run_id)
    intr = result.get("__interrupt__") if isinstance(result, dict) else None
    stats = {"llm_calls": c.llm_calls, "fallbacks": c.fallbacks, "tool_calls": dict(c.tool_calls),
             "elapsed_s": round(c.elapsed(), 2), "offline": c.offline, "critic_loops": c.cache.get("critic_loops", 0),
             "relaxations": sum(len(p.applied) for p in c.policies.values())}
    if intr:
        payload = intr[0].value
        _record(run_id, status="waiting", outcome=payload.get("kind", ""))
        bus.emit(run_id, "system", "run_status", f"waiting for patient ({payload.get('kind')})", {"status": "waiting", "interrupt": payload})
        return {"run_id": run_id, "status": "waiting", "interrupt": payload, "response": None, "stats": stats}
    resp = result.get("response") or {"kind": "failed", "text": "No response."}
    _record(run_id, status="done", outcome=resp.get("kind", ""), summary={"response": resp.get("text"), "stats": stats})
    bus.emit(run_id, "system", "run_status", f"run finished: {resp.get('kind')}", {"status": "done", "kind": resp.get("kind"), "stats": stats})
    return {"run_id": run_id, "status": "done", "interrupt": None, "response": resp, "stats": stats}


def start_run(text: str, patient_id: str = "GUEST", run_id: str | None = None) -> dict:
    run_id = run_id or uuid.uuid4().hex[:12]
    with _lock_for(run_id):
        c = new_context(run_id, patient_id)
        c.cache["text"] = text
        _record(run_id, patient_id=patient_id, kind="chat", user_text=text, status="running")
        bus.emit(run_id, "system", "run_status", f"run started for {patient_id} ({'offline' if c.offline else 'online'} mode)",
                 {"status": "started", "patient_id": patient_id, "offline": c.offline, "inject_fault": c.inject_fault})
        bus.emit(run_id, "human", "message", text, {"role": "user", "patient_id": patient_id})
        try:
            result = get_graph().invoke({"run_id": run_id, "patient_id": patient_id, "text": text, "last_message": text}, _cfg(run_id))
        except Exception as e:  # noqa: BLE001
            return _crash(run_id, e)
        return _package(run_id, result)


def resume_run(run_id: str, value: dict) -> dict:
    if not has_context(run_id):
        return {"run_id": run_id, "status": "error", "response": {"kind": "failed", "text": "This conversation has expired (server restarted). Please send the request again."}}
    with _lock_for(run_id):
        if isinstance(value, dict) and value.get("text"):
            bus.emit(run_id, "human", "message", value["text"], {"role": "user"})
        try:
            result = get_graph().invoke(Command(resume=value), _cfg(run_id))
        except Exception as e:  # noqa: BLE001
            return _crash(run_id, e)
        return _package(run_id, result)


def _crash(run_id: str, e: Exception) -> dict:
    tb = traceback.format_exc()
    bus.emit(run_id, "system", "error", f"run crashed: {type(e).__name__}: {e}", {"traceback": tb[-2000:]})
    _record(run_id, status="error", outcome="error")
    return {"run_id": run_id, "status": "error", "interrupt": None,
            "response": {"kind": "failed", "text": f"Internal error ({type(e).__name__}). Nothing was booked."}, "stats": {}}


def pending_interrupt(run_id: str) -> dict | None:
    try:
        snap = get_graph().get_state(_cfg(run_id))
        for t in snap.tasks:
            for i in t.interrupts:
                return i.value
    except Exception:
        return None
    return None
