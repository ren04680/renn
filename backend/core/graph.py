"""The multi-agent LangGraph.

  START → guard ─(emergency)→ escalate → END
            └→ supervisor ⇄ {memory, triage, gap_check→clarify(interrupt)→guard, scheduling, billing,
                              critic, approval(interrupt), book, notification, remember} → finish → END

Hub-and-spoke: specialists never call each other; they read/write the blackboard and return to the
Supervisor, which dispatches the next ready subtask. Human-in-the-loop via LangGraph `interrupt()`.
"""
from __future__ import annotations

import copy

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend import tools  # noqa: F401  (registers tools)
from backend.agents import billing, critic, event_watcher, memory, notification, scheduling, supervisor, triage  # noqa: F401
from backend.config import MAX_CLARIFY_ROUNDS, MAX_CRITIC_LOOPS
from backend.core import guardrails
from backend.core.context import ctx
from backend.core.state import GraphState
from backend.tools.common import date_label
from backend.tools.registry import call_tool

MAX_RACE_RETRIES = 2


# ----------------------------------------------------------------------------- helpers
def _st(c, state):
    return c.bb.get(state.get("current")) if state.get("current") else None


def _start(c, st):
    c.bb.set_status(st.owner if st.owner != "human" else "supervisor", st.id, "running")


def _done(c, st, result=None, agent=None):
    c.bb.set_status(agent or st.owner, st.id, "done", result or {})


def _outcome(c, agent, **o):
    c.bb.write(agent, "facts", {"outcome": o}, msg=f"outcome: {o.get('status')}")


# ----------------------------------------------------------------------------- nodes
def guard(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    msg = state.get("last_message") or state.get("text", "")
    r = guardrails.emergency_screen(msg)
    if r["emergency"]:
        c.trace("guardrail", "decision", f"EMERGENCY language detected ({', '.join(m['match'] for m in r['matches'])}) — "
                "all scheduling stopped. Hard rule, no agent can override.", r)
        return {"next": "escalate"}
    c.trace("guardrail", "decision", "emergency_screen: clear (hard rule passed) → hand over to Supervisor", r)
    return {"next": "supervisor"}


def escalate(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    msg = guardrails.ESCALATION_MESSAGE
    if c.patient_id != "GUEST":
        call_tool(c, "notification", "send_notification", {
            "patient_id": c.patient_id, "subject": "EMERGENCY — please call 108", "channel": "sms", "kind": "emergency",
            "body": "We detected emergency symptoms in your message. Call 108 / 112 or go to the nearest ER now. "
                    "Kothrud Care Hospital and Shivajinagar General Hospital ERs are open 24×7."},
            reason="emergency escalation must reach the patient immediately")
    for s in c.bb.subtasks:
        if s.status == "pending":
            c.bb.set_status("supervisor", s.id, "skipped", {"why": "emergency escalation"})
    _outcome(c, "guardrail", status="emergency", message=msg, text=state.get("last_message"))
    c.bb.write("guardrail", "events", {"type": "emergency_escalated", "text": state.get("last_message")})
    return {"response": supervisor.compose_response(c)}


def supervisor_node(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    if state.get("replan") or not c.bb.subtasks:
        rnd = c.cache.get("plan_round", 0) + 1
        c.cache["plan_round"] = rnd
        if rnd > 1:
            for s in c.bb.subtasks:
                if s.status in ("pending", "running", "blocked"):
                    c.bb.set_status("supervisor", s.id, "skipped", {"why": "re-planned after clarification"})
            c.policies.clear()
        supervisor.plan(c, rnd)
    if c.timed_out():
        c.trace("supervisor", "error", "Global run timeout reached → honest fallback (no guess).")
        _outcome(c, "supervisor", status="failed", reason="the request took too long to process safely.")
        return {"next": "finish", "replan": False}
    st = supervisor.next_subtask(c)
    if st is None:
        if not c.bb.facts.get("outcome"):
            _outcome(c, "supervisor", status="failed", reason="no further step was possible.")
        c.trace.decision("supervisor", "All subtasks resolved → goal complete. Composing the answer.")
        return {"next": "finish", "replan": False, "current": None}
    supervisor.explain_dispatch(c, st)
    node = supervisor.OWNER_NODE[st.kind]
    return {"next": node, "current": st.id, "replan": False}


def memory_node(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    _start(c, st)
    fact = memory.recall(c, st.goal_ref)
    _done(c, st, {"patient_id": fact.get("patient_id"), "prefs": fact.get("prefs")})
    return {}


def triage_node(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    _start(c, st)
    res = triage.run(c, st.goal_ref)
    _done(c, st, {"specialty": res.get("specialty"), "urgency": res.get("urgency")})
    if res.get("urgency") == "emergency":
        return {"next": "escalate"}
    return {}


def gap_check_node(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    _start(c, st)
    r = supervisor.gap_check(c)
    if r.get("emergency"):
        c.bb.set_status("supervisor", st.id, "done", r)
        return {"next": "escalate"}
    if r.get("info"):
        c.bb.set_status("supervisor", st.id, "done", {"info": True})
        supervisor.skip_downstream(c, ("triage", "schedule", "cost", "verify", "approve", "book", "notify", "remember"), "nothing to book")
        c.trace.decision("supervisor", "Request is outside what the agents may do → honest answer instead of an action.")
        _outcome(c, "supervisor", status="info", text=r["info"])
        return {"next": "supervisor"}
    if r.get("fail"):
        c.bb.set_status("supervisor", st.id, "failed", r)
        supervisor.skip_downstream(c, ("schedule", "cost", "verify", "approve", "book", "notify", "remember"), "gap not resolvable")
        _outcome(c, "supervisor", status="failed", reason=r["fail"])
        return {"next": "supervisor"}
    if r.get("question"):
        c.bb.set_status("supervisor", st.id, "blocked", r, msg=f"{st.id} blocked — missing {r.get('missing')}")
        c.cache["clarify_question"] = r["question"]
        c.cache["clarify_purpose"] = r.get("purpose", "specialty")
        c.cache["clarify_suggestions"] = r.get("suggestions", [])
        return {"next": "clarify"}
    goals = c.cache["goals"]
    c.trace.decision("supervisor", "Gap check passed: " + "; ".join(
        f"{ref}={g.get('specialty')} for {g.get('patient_name') or g.get('patient_id')}" + (f" (doctor {g['doctor_id']})" if g.get("doctor_id") else "")
        for ref, g in goals.items()))
    _done(c, st, {"goals": {k: {kk: v.get(kk) for kk in ("specialty", "patient_id", "doctor_id")} for k, v in goals.items()}}, agent="supervisor")
    return {"next": "supervisor"}


def clarify(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    q = c.cache.get("clarify_question", "Could you tell me a bit more?")
    purpose = c.cache.get("clarify_purpose", "specialty")
    sugg = c.cache.get("clarify_suggestions", [])
    key = f"clarify_asked_{c.cache.get('clarify_rounds', 0)}_{purpose}"
    if not c.cache.get(key):
        c.cache[key] = True
        c.trace("supervisor", "approval_request", f"Asking the patient ({purpose}): {q.replace('**', '')}",
                {"kind": "clarification", "question": q, "purpose": purpose})
    c.pause()
    answer = interrupt({"kind": "clarification", "question": q, "run_id": c.run_id, "purpose": purpose, "suggestions": sugg})
    c.unpause()
    ans = answer.get("text", "") if isinstance(answer, dict) else str(answer)
    if purpose == "specialty":
        c.cache["clarify_rounds"] = c.cache.get("clarify_rounds", 0) + 1
    else:
        # a "which day / what time / where" answer must not change WHAT was already decided (specialty, doctor)
        c.cache["carry_goals"] = {ref: {k: g.get(k) for k in ("specialty", "doctor_id")} for ref, g in c.cache["goals"].items()}
    c.trace("human", "message", ans, {"role": "user", "clarification": True})
    c.cache["text"] = f"{c.cache['text']}. {ans}"
    if c.cache.get("clarify_rounds", 0) > MAX_CLARIFY_ROUNDS:
        _outcome(c, "supervisor", status="failed", reason="the request stayed unclear after two clarifications.")
        return {"next": "finish"}
    return {"text": c.cache["text"], "last_message": ans, "replan": True, "next": "guard"}


def scheduling_node(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    _start(c, st)
    joint = st.params.get("joint_with")
    if st.params.get("solved_with"):
        partner = c.bb.get(st.params["solved_with"])
        _done(c, st, {"outcome": "solved jointly", "with": partner.id if partner else None})
        return {}
    if joint:
        refs = [st.goal_ref] + list(joint)
        res = scheduling.run_joint(c, refs, st.params.get("coupling") or {})
    else:
        res = scheduling.run(c, st.goal_ref)
    out = res.get("outcome")
    if out == "proposed":
        p = res["proposal"]
        c.cache["proposal"] = p
        c.bb.write("scheduling", "proposals", copy.deepcopy(p), msg=f"proposal {p['proposal_id']}: " + "; ".join(
            f"{i['slot_id']} {i['doctor_name']} {i['date']} {i['start']}" for i in p["items"]))
        _done(c, st, {"outcome": "proposed", "proposal_id": p["proposal_id"]})
        if joint:
            for s in c.bb.subtasks:
                if s.params.get("solved_with") == st.id and s.status == "pending":
                    c.bb.set_status("scheduling", s.id, "done", {"outcome": "solved jointly", "with": st.id})
    elif out == "waitlisted":
        g = c.cache["goals"][st.goal_ref]
        _done(c, st, {"outcome": "waitlisted", "waitlist_id": res["waitlist_id"]})
        supervisor.skip_downstream(c, ("cost", "verify", "approve", "book"), "waitlisted — nothing to approve")
        _outcome(c, "scheduling", status="waitlisted", waitlist_id=res["waitlist_id"], position=res.get("position"),
                 specialty=res["constraints"]["specialty"], patient_id=g.get("patient_id"), patient_name=g.get("patient_name"),
                 date_from=res["constraints"].get("date_from"), date_to=res["constraints"]["date_to"],
                 relaxations=res.get("relaxations", []))
    else:
        c.bb.set_status("scheduling", st.id, "failed", {"outcome": "failed", "reason": res.get("reason")})
        supervisor.skip_downstream(c, ("schedule", "cost", "verify", "approve", "book", "notify", "remember"), "scheduling failed")
        _outcome(c, "scheduling", status="failed", reason=res.get("reason") or "no slot could be found.")
    return {}


def billing_node(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    _start(c, st)
    if st.kind == "billing_answer":
        pid = c.bb.facts.get("memory_G1", {}).get("patient_id") or c.patient_id
        res = billing.answer_question(c, pid)
        _done(c, st, {"estimates": len(res["estimates"])})
        _outcome(c, "billing", status="billing", answer=res["answer"], estimates=res["estimates"])
        return {}
    p = billing.cost_proposal(c, c.cache["proposal"])
    c.cache["proposal"] = p
    c.bb.write("billing", "proposals", copy.deepcopy(p), msg=f"proposal {p['proposal_id']} costed: patient pays ₹{p['total_patient_pays']}")
    _done(c, st, {"total_patient_pays": p["total_patient_pays"]})
    return {}


def critic_node(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    _start(c, st)
    p = c.cache["proposal"]
    v = critic.review(c, p)
    if v["verdict"] == "APPROVE":
        _done(c, st, {"verdict": "APPROVE"})
        return {}
    loops = c.cache.get("critic_loops", 0) + 1
    c.cache["critic_loops"] = loops
    if loops > MAX_CRITIC_LOOPS:
        c.bb.set_status("critic", st.id, "failed", {"verdict": "REVISE", "loops": loops})
        for it in p["items"]:
            call_tool(c, "scheduling", "release_hold", {"slot_id": it["slot_id"]}, reason="giving up honestly — free the hold")
        supervisor.skip_downstream(c, ("approve", "book", "notify", "remember"), "critic loop limit reached")
        _outcome(c, "critic", status="failed", reason=f"my proposals kept failing verification ({'; '.join(v['reasons'])[:200]}), so I stopped instead of guessing.")
        return {}
    ref = p.get("goal_ref", "G1")
    c.cache.setdefault(f"exclude_{ref}", []).extend(v["reject_slots"])
    c.cache[f"feedback_{ref}"] = v["reasons"]
    c.trace.decision("supervisor", f"Critic said REVISE (loop {loops}/{MAX_CRITIC_LOOPS}) → re-dispatch Scheduling with feedback; excluded {v['reject_slots']}.")
    c.bb.set_status("critic", st.id, "failed", {"verdict": "REVISE", "reasons": v["reasons"]})
    supervisor.reset_for_replan(c, ("schedule", "cost", "verify"), "critic REVISE")
    return {}


def approval(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    p = c.cache["proposal"]
    key = f"approval_asked_{p['proposal_id']}"
    if not c.cache.get(key):
        c.cache[key] = True
        c.bb.set_status("supervisor", st.id, "running", msg=f"{st.id} waiting for the patient's decision")
        c.trace("supervisor", "approval_request", "Human approval required before any booking write (interrupt).",
                {"kind": "approval", "proposal": p})
    c.pause()
    decision = interrupt({"kind": "approval", "run_id": c.run_id, "proposal": p,
                          "question": "Shall I book this?" if p["kind"] != "reschedule" else "Shall I move your appointment?"})
    c.unpause()
    ok = bool(decision.get("approved")) if isinstance(decision, dict) else str(decision).lower().startswith("y")
    c.trace("human", "decision", f"Patient {'APPROVED' if ok else 'REJECTED'} proposal {p['proposal_id']}", {"approved": ok})
    if ok:
        tok = c.issue_approval(p["proposal_id"])
        c.cache["approval_token"] = tok
        c.bb.write("supervisor", "decisions", {"type": "approval", "proposal_id": p["proposal_id"], "approved": True},
                   msg=f"approval granted for {p['proposal_id']} (token minted by human step)")
        c.bb.set_status("supervisor", st.id, "done", {"approved": True})
    else:
        for it in p["items"]:
            call_tool(c, "scheduling", "release_hold", {"slot_id": it["slot_id"]}, reason="patient rejected — free the slot for others")
        c.bb.write("supervisor", "decisions", {"type": "approval", "proposal_id": p["proposal_id"], "approved": False})
        c.bb.set_status("supervisor", st.id, "done", {"approved": False})
        supervisor.skip_downstream(c, ("book", "notify", "remember"), "patient rejected the proposal")
        _outcome(c, "supervisor", status="rejected", proposal_id=p["proposal_id"])
    return {}


def book(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    _start(c, st)
    p = c.cache["proposal"]
    tok = c.cache.get("approval_token")
    items = p["items"]
    if p["kind"] == "reschedule":
        r = call_tool(c, "scheduling", "reschedule_appointment", {
            "appointment_id": p["reschedule_of"]["appointment_id"], "new_slot_id": items[0]["slot_id"],
            "proposal_id": p["proposal_id"], "approval_token": tok}, reason="patient approved — execute the gated reschedule")
        appts = [r["appointment"]] if r.get("ok") else []
    elif len(items) > 1:
        r = call_tool(c, "scheduling", "book_joint", {
            "bookings": [{"slot_id": i["slot_id"], "patient_id": i["patient_id"], "reason": i["specialty"]} for i in items],
            "proposal_id": p["proposal_id"], "approval_token": tok}, reason="patient approved — book both atomically")
        appts = r.get("appointments", []) if r.get("ok") else []
    else:
        i = items[0]
        r = call_tool(c, "scheduling", "book_slot", {"slot_id": i["slot_id"], "patient_id": i["patient_id"],
                                                     "proposal_id": p["proposal_id"], "approval_token": tok, "reason": i["specialty"]},
                      reason="patient approved — execute the gated booking")
        appts = [r["appointment"]] if r.get("ok") else []
    if not r.get("ok"):
        if r.get("race"):
            n = c.cache.get("race_retries", 0) + 1
            c.cache["race_retries"] = n
            c.bb.write("scheduling", "events", {"type": "booking_race", "detail": r.get("error")})
            if n > MAX_RACE_RETRIES:
                c.bb.set_status("scheduling", st.id, "failed", {"race": True})
                supervisor.skip_downstream(c, ("notify", "remember"), "repeated booking races")
                _outcome(c, "scheduling", status="failed", reason="the slots kept being taken by others while booking.")
                return {}
            ref = p.get("goal_ref", "G1")
            c.cache.setdefault(f"exclude_{ref}", []).extend(i["slot_id"] for i in items)
            c.trace.decision("supervisor", f"Booking race ({r.get('error')}) → treated as a re-plan, not an error. Finding the next best slot; the patient will approve again.")
            c.bb.set_status("scheduling", st.id, "failed", {"race": True})
            supervisor.reset_for_replan(c, ("schedule", "cost", "verify", "approve", "book"), "booking race")
            return {}
        c.bb.set_status("scheduling", st.id, "failed", {"error": r.get("error")})
        supervisor.skip_downstream(c, ("notify", "remember"), "booking failed")
        _outcome(c, "scheduling", status="failed", reason=r.get("error"))
        return {}
    by_slot = {i["slot_id"]: i for i in items}
    for a in appts:
        it = by_slot.get(a["slot_id"], {})
        a["patient_name"] = it.get("patient_name", a.get("patient_id"))
        a["patient_pays"] = (it.get("cost") or {}).get("patient_pays")
    _done(c, st, {"appointments": [a["appointment_id"] for a in appts]})
    _outcome(c, "scheduling", status="booked", appointments=appts, disclosures=p.get("disclosures", []),
             relaxations=p.get("relaxations", []), proposal_id=p["proposal_id"], rescheduled=p["kind"] == "reschedule")
    return {}


def notification_node(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    _start(c, st)
    o = c.bb.facts.get("outcome", {})
    sent = 0
    if o.get("status") == "booked":
        for a in o["appointments"]:
            kind = "rescheduled" if o.get("rescheduled") else "booked"
            notification.notify(c, kind, a, a["patient_id"])
            sent += 1
    elif o.get("status") == "waitlisted":
        window = f"between {date_label(o['date_from'])} and {date_label(o['date_to'])}" if o.get("date_from") else ""
        notification.notify(c, "waitlisted", {**o, "window": window}, o.get("patient_id") or c.patient_id)
        sent += 1
    _done(c, st, {"sent": sent})
    return {}


def remember_node(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    st = _st(c, state)
    _start(c, st)
    saved = memory.remember(c)
    _done(c, st, {"saved": len(saved)})
    return {}


def finish(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    resp = supervisor.compose_response(c)
    c.trace("supervisor", "message", resp["text"], {"role": "assistant", "kind": resp["kind"]})
    return {"response": resp}


def _route(state: GraphState) -> str:
    return state.get("next") or "supervisor"


def _after_agent(state: GraphState) -> str:
    n = state.get("next")
    return n if n in ("escalate", "clarify", "finish", "guard") else "supervisor"


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("guard", guard)
    g.add_node("escalate", escalate)
    g.add_node("supervisor", supervisor_node)
    g.add_node("memory", memory_node)
    g.add_node("triage", triage_node)
    g.add_node("gap_check", gap_check_node)
    g.add_node("clarify", clarify)
    g.add_node("scheduling", scheduling_node)
    g.add_node("billing", billing_node)
    g.add_node("critic", critic_node)
    g.add_node("approval", approval)
    g.add_node("book", book)
    g.add_node("notification", notification_node)
    g.add_node("remember", remember_node)
    g.add_node("finish", finish)
    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", _route, {"escalate": "escalate", "supervisor": "supervisor"})
    g.add_edge("escalate", END)
    g.add_conditional_edges("supervisor", _route, {k: k for k in (
        "memory", "triage", "gap_check", "scheduling", "billing", "critic", "approval", "book", "notification",
        "remember", "finish")})
    for n in ("memory", "triage", "gap_check", "scheduling", "billing", "critic", "approval", "book", "notification", "remember"):
        g.add_conditional_edges(n, _after_agent, {"supervisor": "supervisor", "escalate": "escalate", "clarify": "clarify",
                                                  "finish": "finish", "guard": "guard"})
    g.add_conditional_edges("clarify", _route, {"guard": "guard", "finish": "finish"})
    g.add_edge("finish", END)
    return g.compile(checkpointer=InMemorySaver())


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
