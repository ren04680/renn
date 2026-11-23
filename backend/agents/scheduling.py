"""Scheduling agent — ReAct: the LLM picks its own tool sequence (online); a deterministic planner
with the same tools, the same policy checks and the same trace events runs offline / on LLM failure.

Bounded autonomy:
  * tools are policy-checked (relaxation ladder order + monotonicity, search envelope)
  * book_slot / reschedule are GATED (approval token only the human step can mint)
  * only slot ids that came back from a tool result can be proposed (zero fabrication)
  * max 15 tool calls; when limits hit → honest fallback (waitlist / "couldn't find"), never a guess
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

from backend.core.context import RunContext
from backend.core.fallback_parser import SPECIALTY_LABEL
from backend.core.llm import LLMUnavailable, get_model, note_fallback, parse_json
from backend.db.models import Doctor, Slot
from backend.db.session import get_session
from backend.tools.common import hm_to_min, slot_view
from backend.tools.policy import LADDER, RelaxationPolicy, get_policy
from backend.tools.registry import call_tool, openai_tool_schemas

AGENT = "scheduling"
MAX_REACT_STEPS = 12


# --------------------------------------------------------------------------- constraints
def initial_constraints(c: RunContext, g: dict | None) -> dict:
    parsed = c.cache.get("parsed", {})
    pc = parsed.get("constraints", {})
    tomorrow = date.today() + timedelta(days=1)
    df = pc.get("date_from") or tomorrow.isoformat()
    dt = pc.get("date_to") or ((tomorrow + timedelta(days=2)).isoformat() if not pc.get("date_from") else df)
    if df < date.today().isoformat():
        df = date.today().isoformat()
    locality = pc.get("locality")
    from_home = False
    if not locality and pc.get("near_me") and g:
        locality = (g.get("prefs") or {}).get("home_locality") or None
        from_home = bool(locality)
        if not locality:
            c.cache["near_me_unresolved"] = True
    modes = ["tele"] if pc.get("mode") == "tele" else ["in_person"]
    cons = {
        "date_from": df, "date_to": dt, "date_text": pc.get("date_text") or "earliest (next 3 days)",
        "time_from": pc.get("time_from"), "time_to": pc.get("time_to"), "time_text": pc.get("time_text"),
        "locality": locality, "modes": modes, "in_person_only": bool(pc.get("in_person_only")),
        "locality_from_home": from_home,
    }
    if g:
        cons.update({"patient_id": g.get("patient_id"), "specialty": g.get("specialty"), "doctor_id": g.get("doctor_id")})
    return cons


def ensure_policy(c: RunContext, goal_ref: str, g: dict | None) -> RelaxationPolicy:
    pol = get_policy(c, goal_ref)
    if pol is None:
        pol = RelaxationPolicy(goal_ref, initial_constraints(c, g))
        c.policies[goal_ref] = pol
        c.bb.write(AGENT, "facts", {f"constraints_{goal_ref}": pol.current},
                   msg=f"constraints_{goal_ref}: {pol.current.get('specialty') or 'joint'} {pol.current['date_from']}..{pol.current['date_to']}"
                   + (f" {pol.current['time_from']}–{pol.current['time_to']}" if pol.current.get("time_from") else "")
                   + (f" in {pol.current['locality']}" if pol.current.get("locality") else ""))
    return pol


# --------------------------------------------------------------------------- ranking
def rank(slots: list[dict], g: dict, pol: RelaxationPolicy) -> list[tuple[float, dict, list[str]]]:
    prefs = g.get("prefs") or {}
    orig = pol.original
    cur = pol.current
    out = []
    for s in slots:
        sc, why = 0.0, []
        if prefs.get("usual_doctor_id") == s["doctor_id"]:
            sc += 3
            why.append(f"{s['doctor_name']} is the patient's usual doctor")
        sess = "morning" if s["start"] < "12:00" else "afternoon" if s["start"] < "16:00" else "evening"
        if orig.get("time_from"):
            st = hm_to_min(s["start"])
            a, b = hm_to_min(orig["time_from"]), hm_to_min(orig["time_to"])
            dist = 0 if a <= st < b else min(abs(st - a), abs(st - b))
            sc -= dist / 60
            if dist:
                why.append(f"closest to the requested {orig.get('time_text') or 'time'} ({dist} min away)")
        elif prefs.get("time") == sess:
            sc += 2
            why.append(f"{sess} slot — patient usually prefers {sess}s")
        if s["mode"] == "tele":
            if prefs.get("mode") == "tele":
                sc += 1.5
                why.append("teleconsult — patient prefers tele")
            else:
                sc -= 1
        elif prefs.get("mode") == "in_person":
            sc += 0.3
        loc = orig.get("locality") or prefs.get("locality") or prefs.get("home_locality")
        if loc and s["locality"] == loc and s["mode"] == "in_person":
            sc += 1.5
            why.append(f"in {loc}" + (" — near your home, as you asked" if orig.get("locality_from_home")
                                      else " as requested" if orig.get("locality") == loc else " (near home)"))
        days = (date.fromisoformat(s["date"]) - date.fromisoformat(cur["date_from"])).days
        sc -= 0.6 * days
        sc += s["rating"] - 4.0
        sc -= hm_to_min(s["start"]) / 6000
        if not why:
            why.append("earliest good match")
        why.append(f"rated {s['rating']}")
        out.append((round(sc, 3), s, why))
    out.sort(key=lambda x: -x[0])
    return out


# --------------------------------------------------------------------------- proposal
def _item(g: dict, goal_ref: str, s: dict) -> dict:
    keep = ("slot_id", "doctor_id", "doctor_name", "specialty", "hospital_id", "hospital_name", "locality",
            "date", "start", "end", "mode", "fee", "rating")
    return {"goal_ref": goal_ref, "patient_id": g.get("patient_id"), "patient_name": g.get("patient_name", g.get("patient_id")),
            **{k: s[k] for k in keep}}


def make_proposal(c: RunContext, goal_ref: str, items: list[dict], pol: RelaxationPolicy, rationale: str,
                  notes: list[str], coupling: dict | None = None, kind: str = "single", extra: dict | None = None) -> dict:
    n = c.cache.get("proposal_n", 0) + 1
    c.cache["proposal_n"] = n
    extra_disc = []
    if c.cache.get("near_me_unresolved"):
        extra_disc.append("You said 'nearby', but I don't know your area (no profile), so I searched all of Pune — "
                          "tell me your locality to narrow it down.")
    for it in items:
        g = c.cache.get("goals", {}).get(it.get("goal_ref"), {})
        if g.get("on_behalf_of"):
            extra_disc.append(f"Booked under your account for your {g['on_behalf_of']} (not registered yet — the front desk "
                              "will register them at the visit).")
    p = {"proposal_id": f"PR-{c.run_id[:6]}-{n}", "goal_ref": goal_ref, "kind": kind, "items": items,
         "coupling": coupling, "relaxations": list(pol.applied), "disclosures": [r["disclosure"] for r in pol.applied] + extra_disc,
         "skipped_steps": list(pol.skipped), "rationale": rationale, "preference_notes": notes, "stage": "proposed",
         **(extra or {})}
    return p


def inject_fault(c: RunContext, p: dict) -> dict:
    """DEBUG: swap the proposal to a real-but-wrong slot (booked, different specialty) to show the Critic."""
    it = p["items"][0]
    with get_session() as s:
        q = (s.query(Slot, Doctor).join(Doctor, Doctor.id == Slot.doctor_id)
             .filter(Slot.date == it["date"], Slot.status == "booked", Doctor.specialty != it["specialty"])
             .order_by(Slot.start).first())
        if q is None:
            q = (s.query(Slot, Doctor).join(Doctor, Doctor.id == Slot.doctor_id)
                 .filter(Slot.status == "booked", Doctor.specialty != it["specialty"]).first())
        bad = slot_view(s, q[0], q[1])
    p = json.loads(json.dumps(p))
    p["items"][0] = {**it, **{k: bad[k] for k in ("slot_id", "doctor_id", "doctor_name", "specialty", "hospital_id",
                                                     "hospital_name", "locality", "date", "start", "end", "mode", "fee", "rating")}}
    c.fault_used = True
    c.trace.decision(AGENT, f"[DEBUG inject-fault] proposal swapped to {bad['slot_id']} ({bad['doctor_name']}, {bad['specialty']}, status=booked) — the Critic should catch this.",
                     {"fault": True, "bad_slot": bad["slot_id"]})
    return p


def _finish_with_slot(c: RunContext, goal_ref: str, g: dict, pol: RelaxationPolicy, slot: dict, why: list[str],
                      rationale_prefix: str = "") -> dict:
    notes = [w for w in why if not w.startswith("rated")]
    rationale = rationale_prefix + f"{slot['doctor_name']} at {slot['hospital_name']} on {slot['date']} {slot['start']}: " + "; ".join(why)
    kind = "reschedule" if g.get("reschedule_of") else "single"
    extra = {"reschedule_of": g["reschedule_of"]} if g.get("reschedule_of") else None
    p = make_proposal(c, goal_ref, [_item(g, goal_ref, slot)], pol, rationale, notes, kind=kind, extra=extra)
    c.trace.thought(AGENT, f"Chose {slot['slot_id']} because: " + "; ".join(why) + ".")
    return {"outcome": "proposed", "proposal": p}


# --------------------------------------------------------------------------- offline planner
def offline_plan(c: RunContext, goal_ref: str, g: dict, pol: RelaxationPolicy) -> dict:
    t = c.trace
    last_key = None
    while True:
        cur = pol.current
        key = (cur.get("specialty"), cur.get("locality"), cur.get("doctor_id"))
        if key != last_key:
            what = f"{SPECIALTY_LABEL.get(cur['specialty'], cur['specialty'])} doctors" + (f" in {cur['locality']}" if cur.get("locality") else " across Pune")
            r = call_tool(c, AGENT, "search_doctors",
                          {"specialty": cur["specialty"], "locality": cur.get("locality"), "doctor_id": cur.get("doctor_id")},
                          reason=f"need candidate {what} before checking their calendars")
            if not r.get("ok"):
                return {"outcome": "failed", "reason": r.get("error")}
            last_key = key
        av = call_tool(c, AGENT, "get_availability", {"goal_ref": goal_ref, "patient_id": g.get("patient_id")},
                       reason="check real free slots within the current (policy-approved) constraints")
        if not av.get("ok"):
            return {"outcome": "failed", "reason": av.get("error")}
        if av["count"] > 0:
            ranked = rank(av["slots"], g, pol)
            for _, s, why in ranked[:3]:
                h = call_tool(c, AGENT, "hold_slot", {"slot_id": s["slot_id"], "patient_id": g.get("patient_id") or "GUEST"},
                              reason="soft-hold the best match so nobody takes it while the patient decides")
                if h.get("ok"):
                    return _finish_with_slot(c, goal_ref, g, pol, s, why)
                if not h.get("race"):
                    return {"outcome": "failed", "reason": h.get("error")}
                t.thought(AGENT, f"{s['slot_id']} was taken a moment ago (race) — re-planning with the next option.")
                c.cache.setdefault(f"exclude_{goal_ref}", []).append(s["slot_id"])
            continue
        nxt = pol.next_allowed(c, AGENT)
        if nxt is None:
            t.thought(AGENT, "Relaxation ladder exhausted. I will not invent a slot — adding the patient to the waitlist.")
            if not g.get("patient_id") or g.get("patient_id") == "GUEST":
                return {"outcome": "failed", "reason": "no slot after the full relaxation ladder (guest cannot be waitlisted)"}
            w = call_tool(c, AGENT, "add_to_waitlist", {
                "patient_id": g["patient_id"], "specialty": cur["specialty"], "doctor_id": cur.get("doctor_id"),
                "date_from": pol.original["date_from"], "date_to": cur["date_to"],
                "time_pref": (g.get("prefs") or {}).get("time"), "locality": pol.original.get("locality"),
                "mode": "any", "goal_ref": goal_ref}, reason="ladder exhausted — waitlist is the honest outcome")
            if not w.get("ok"):
                return {"outcome": "failed", "reason": w.get("error")}
            return {"outcome": "waitlisted", "waitlist_id": w["waitlist_id"], "position": w["position"],
                    "relaxations": pol.applied, "constraints": cur}
        t.thought(AGENT, f"No free slot under current constraints → next ladder step allowed by policy: '{nxt}'.")
        r = call_tool(c, AGENT, "relax_constraint", {"step": nxt, "goal_ref": goal_ref},
                      reason="no slots found; relax exactly one constraint in ladder order")
        if not r.get("ok"):
            return {"outcome": "failed", "reason": r.get("error")}


# --------------------------------------------------------------------------- online ReAct
SYSTEM = """You are the Scheduling agent of a Pune hospital network. You choose which tools to call and in
what order to find the best appointment slot for the goal below.

Hard rules (enforced by the tools — breaking them only returns errors):
1. Only propose a slot_id that a tool returned to you. Never invent ids, times, doctors or fees.
2. If there are no free slots, call relax_constraint with the next ladder step:
   widen_time → widen_area → allow_tele → next_day (ineffective steps are skipped by the policy).
   Never skip ahead; the tool will tell you the allowed step.
3. Only when the ladder is exhausted, call add_to_waitlist.
4. hold_slot the slot you choose before proposing it.
5. You cannot book: book_slot needs the patient's approval token, which you do not have.
6. Prefer the patient's remembered preferences (usual doctor, time of day, mode, area) when choosing.
Every tool call must include a short `reason`.
Finish with ONLY a JSON object, no tool call:
  {"action":"propose","slot_id":"S…","rationale":"why this slot (mention preferences used)"}
or {"action":"waitlist","waitlist_id":"W…"}"""


def react(c: RunContext, goal_ref: str, g: dict, pol: RelaxationPolicy) -> dict:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    model = get_model(c)
    schemas = openai_tool_schemas(AGENT, exclude=("find_joint_slots", "book_joint", "reschedule_appointment", "release_hold"))
    bound = model.bind_tools(schemas)
    feedback = c.cache.get(f"feedback_{goal_ref}")
    goal = {"goal_ref": goal_ref, "patient_id": g.get("patient_id"), "patient_name": g.get("patient_name"),
            "specialty": pol.current["specialty"], "pinned_doctor_id": pol.current.get("doctor_id"),
            "constraints_now": {k: v for k, v in pol.current.items() if k not in ("patient_id",)},
            "next_allowed_relaxation": pol.peek_next(), "preferences_from_memory": g.get("prefs"),
            "excluded_slot_ids": c.cache.get(f"exclude_{goal_ref}", []),
            "critic_feedback": feedback}
    msgs = [SystemMessage(SYSTEM), HumanMessage("Goal:\n" + json.dumps(goal, default=str))]
    seen_slots: dict[str, dict] = {}
    waitlist_ids: set[str] = set()
    for step in range(MAX_REACT_STEPS):
        if not c.budget_ok(AGENT):
            break
        try:
            c.llm_calls += 1
            ai: AIMessage = bound.invoke(msgs)
        except Exception as e:  # noqa: BLE001
            from backend.core.llm import trip_breaker

            trip_breaker()
            raise LLMUnavailable(f"{type(e).__name__}: {e}") from e
        msgs.append(ai)
        text = ai.content if isinstance(ai.content, str) else ""
        if ai.tool_calls:
            if text.strip():
                c.trace.thought(AGENT, text.strip()[:300], {"llm": True})
            for tc in ai.tool_calls:
                args = dict(tc.get("args") or {})
                reason = args.pop("reason", "") or text.strip()[:140]
                if tc["name"] in ("get_availability",):
                    args.setdefault("goal_ref", goal_ref)
                if tc["name"] == "relax_constraint":
                    args.setdefault("goal_ref", goal_ref)
                res = call_tool(c, AGENT, tc["name"], args, reason=reason)
                for s in res.get("slots", []) or []:
                    seen_slots[s["slot_id"]] = s
                if res.get("slot"):
                    seen_slots[res["slot"]["slot_id"]] = res["slot"]
                if res.get("waitlist_id"):
                    waitlist_ids.add(res["waitlist_id"])
                msgs.append(ToolMessage(json.dumps(res, default=str)[:3500], tool_call_id=tc["id"]))
            continue
        try:
            final = parse_json(text)
        except Exception:  # noqa: BLE001
            msgs.append(HumanMessage("Reply with the final JSON object only (or call a tool)."))
            continue
        if final.get("action") == "waitlist" and final.get("waitlist_id") in waitlist_ids:
            return {"outcome": "waitlisted", "waitlist_id": final["waitlist_id"], "relaxations": pol.applied,
                    "constraints": pol.current, "position": None}
        sid = final.get("slot_id")
        if final.get("action") == "propose" and sid in seen_slots:
            s = seen_slots[sid]
            with get_session() as sess:
                sl = sess.get(Slot, sid)
                held_by_me = sl is not None and sl.status == "held" and sl.held_by == c.run_id
            if not held_by_me:
                h = call_tool(c, AGENT, "hold_slot", {"slot_id": sid, "patient_id": g.get("patient_id") or "GUEST"},
                              reason="system: chosen slot must be held before it is proposed")
                if not h.get("ok"):
                    msgs.append(HumanMessage(f"hold failed: {h.get('error')}. Choose another slot from tool results."))
                    continue
                s = h["slot"]
            rationale = str(final.get("rationale", ""))[:400]
            ranked = rank([s], g, pol)
            why = ranked[0][2] if ranked else []
            out = _finish_with_slot(c, goal_ref, g, pol, s, why, rationale_prefix=(rationale + " — ") if rationale else "")
            return out
        msgs.append(HumanMessage(
            f"Rejected: slot_id {sid!r} did not come from a tool result in this conversation (zero-fabrication rule). "
            "Use get_availability and pick one of the returned slot_ids."))
        c.trace("scheduling", "error", f"LLM proposed {sid!r} which no tool returned — rejected (zero fabrication)")
    raise LLMUnavailable("ReAct loop ended without a valid proposal")


# --------------------------------------------------------------------------- entry points
def run(c: RunContext, goal_ref: str) -> dict:
    g = c.cache["goals"][goal_ref]
    pol = ensure_policy(c, goal_ref, g)
    t = c.trace
    fb = c.cache.get(f"feedback_{goal_ref}")
    if fb:
        t.thought(AGENT, f"Re-planning after Critic feedback: {'; '.join(fb)[:220]}")
    t.thought(AGENT, f"Goal {goal_ref}: {SPECIALTY_LABEL.get(pol.current['specialty'], pol.current['specialty'])} for "
                     f"{g.get('patient_name') or g.get('patient_id')} — {pol.current['date_text'] if not pol.applied else pol.current['date_from']}"
                     + (f", {pol.current['time_text']}" if pol.current.get('time_text') and not pol.applied else "")
                     + (f", {pol.current['locality']}" if pol.current.get("locality") else "")
                     + (f", pinned to {g.get('doctor_id')}" if g.get("doctor_id") else "")
                     + f". Mode: {'online ReAct (LLM chooses tools)' if not c.offline else 'offline planner (same tools & policy)'}.")
    res = None
    if not c.offline:
        try:
            res = react(c, goal_ref, g, pol)
        except LLMUnavailable as e:
            note_fallback(c, AGENT, "react_scheduling", e)
    if res is None:
        res = offline_plan(c, goal_ref, g, pol)
    if res.get("outcome") == "proposed" and c.inject_fault and not c.fault_used:
        res["proposal"] = inject_fault(c, res["proposal"])
    return res


def run_joint(c: RunContext, goal_refs: list[str], coupling: dict) -> dict:
    """Multi-goal: one joint search over two linked goals with a coupling constraint."""
    goals = c.cache["goals"]
    ga, gb = goals[goal_refs[0]], goals[goal_refs[1]]
    pol = ensure_policy(c, "J", None)
    t = c.trace
    t.thought(AGENT, f"Joint goal: {SPECIALTY_LABEL[ga['specialty']]} for {ga.get('patient_name')} + "
                     f"{SPECIALTY_LABEL[gb['specialty']]} for {gb.get('patient_name')}; coupling: "
                     + ", ".join(k.replace("_", " ") for k, v in coupling.items() if v) + ". Using find_joint_slots instead of two independent searches.")
    while True:
        r = call_tool(c, AGENT, "find_joint_slots", {
            "goal_a": {"patient_id": ga["patient_id"], "specialty": ga["specialty"], "label": goal_refs[0]},
            "goal_b": {"patient_id": gb["patient_id"], "specialty": gb["specialty"], "label": goal_refs[1]},
            "same_day": bool(coupling.get("same_day") or coupling.get("back_to_back")),
            "back_to_back": bool(coupling.get("back_to_back")),
            "prefer_same_hospital": bool(coupling.get("same_hospital")), "goal_ref": "J"},
            reason="two linked appointments must be solved together, not one after the other")
        if not r.get("ok"):
            return {"outcome": "failed", "reason": r.get("error")}
        if r["count"]:
            for pair in r["pairs"][:3]:
                h1 = call_tool(c, AGENT, "hold_slot", {"slot_id": pair["a"]["slot_id"], "patient_id": ga["patient_id"]},
                               reason=f"hold {goal_refs[0]} half of the best pair")
                if not h1.get("ok"):
                    c.cache.setdefault("exclude_J", []).append(pair["a"]["slot_id"])
                    continue
                h2 = call_tool(c, AGENT, "hold_slot", {"slot_id": pair["b"]["slot_id"], "patient_id": gb["patient_id"]},
                               reason=f"hold {goal_refs[1]} half of the pair")
                if not h2.get("ok"):
                    call_tool(c, AGENT, "release_hold", {"slot_id": pair["a"]["slot_id"]}, reason="partner slot lost — release")
                    c.cache.setdefault("exclude_J", []).append(pair["b"]["slot_id"])
                    continue
                a, b = pair["a"], pair["b"]
                notes = []
                if pair["same_hospital"]:
                    notes.append(f"both at {a['hospital_name']} (same hospital, as preferred)")
                else:
                    notes.append("no same-hospital pair was free, so the two hospitals differ (soft preference not met)")
                first, second = (a, b) if a["start"] <= b["start"] else (b, a)
                notes.append(f"back-to-back: {first['start']}–{first['end']} then {second['start']}–{second['end']}")
                rationale = (f"Joint plan on {a['date']}: {a['doctor_name']} ({SPECIALTY_LABEL[a['specialty']]}) for {ga['patient_name']} "
                             f"and {b['doctor_name']} ({SPECIALTY_LABEL[b['specialty']]}) for {gb['patient_name']}; " + "; ".join(notes))
                t.thought(AGENT, f"Chose pair {a['slot_id']}+{b['slot_id']}: " + "; ".join(notes) + ".")
                p = make_proposal(c, "J", [_item(ga, goal_refs[0], a), _item(gb, goal_refs[1], b)], pol, rationale, notes,
                                  coupling=coupling, kind="joint")
                if c.inject_fault and not c.fault_used:
                    p = inject_fault(c, p)
                return {"outcome": "proposed", "proposal": p}
            continue
        nxt = pol.next_allowed(c, AGENT)
        if nxt is None:
            return {"outcome": "failed", "reason": "No pair of slots satisfies the coupling (same day, back-to-back) even after relaxing; "
                    "I won't invent one. I can book the two appointments separately instead."}
        r2 = call_tool(c, AGENT, "relax_constraint", {"step": nxt, "goal_ref": "J"}, reason="no valid pair; relax one shared constraint")
        if not r2.get("ok"):
            return {"outcome": "failed", "reason": r2.get("error")}


def new_id() -> str:
    return uuid.uuid4().hex[:8]


__all__ = ["run", "run_joint", "rank", "LADDER"]
