"""Event Watcher / Proactive agent.

Wakes up on hospital events with NO user prompt:
  * doctor_cancel(doctor, date, start–end)  → find affected appointments → per patient: recall memory
    preferences → find alternatives → verify → soft-hold → notify → wait for the patient's confirmation
  * slot_freed(slot)                         → offer it to the best-matching waitlisted patient
Fully autonomous up to hold + notify. The final write (reschedule / book) still needs the patient's
explicit confirmation (LangGraph interrupt → approval token) — same gate as everywhere else.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import date, timedelta
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel
from sqlalchemy import and_

from backend.config import PROACTIVE_HOLD_TTL_SECONDS
from backend.core.context import ctx, new_context
from backend.core.fallback_parser import SPECIALTY_LABEL
from backend.core.trace import bus
from backend.db.models import Appointment, Doctor, Offer, Patient, RunRecord, Slot, WaitlistEntry
from backend.db.session import get_session
from backend.tools.common import date_label, hm_to_min, slot_view
from backend.tools.registry import call_tool, tool

AGENT = "event_watcher"


# ============================================================================ HIS side effects
def apply_doctor_cancel(doctor_id: str, d: str, start: str, end: str) -> dict:
    with get_session() as s:
        rows = s.query(Slot).filter(Slot.doctor_id == doctor_id, Slot.date == d, Slot.start >= start, Slot.start < end).all()
        for sl in rows:
            sl.status, sl.held_by, sl.hold_expires = "cancelled", None, None
        return {"slots_cancelled": len(rows), "slot_ids": [r.id for r in rows]}


def apply_slot_freed(slot_id: str) -> dict:
    with get_session() as s:
        sl = s.get(Slot, slot_id)
        if sl is None:
            return {"error": "no such slot"}
        appt = s.query(Appointment).filter(Appointment.slot_id == slot_id, Appointment.status == "booked").first()
        if appt:
            appt.status, appt.notes = "cancelled", "cancelled by patient (slot freed)"
        sl.status, sl.held_by, sl.hold_expires = "free", None, None
        return {"freed": slot_id, "cancelled_appointment": appt.id if appt else None}


# ============================================================================ tools
class AffectedArgs(BaseModel):
    doctor_id: str
    date: str
    start: str
    end: str


@tool("get_affected_appointments", AffectedArgs, "Appointments inside a cancelled doctor block (registered + walk-in).")
def get_affected_appointments(c, doctor_id: str, date: str, start: str, end: str) -> dict:
    with get_session() as s:
        rows = (s.query(Appointment, Slot).join(Slot, Slot.id == Appointment.slot_id)
                .filter(Slot.doctor_id == doctor_id, Slot.date == date, Slot.start >= start, Slot.start < end,
                        Appointment.status == "booked").order_by(Slot.start).all())
        out = [{"appointment_id": a.id, "patient_id": a.patient_id, "patient_name": a.patient_name, **slot_view(s, sl)} for a, sl in rows]
    reg = [a for a in out if a["patient_id"]]
    return {"ok": True, "appointments": out, "registered": len(reg), "walk_in": len(out) - len(reg),
            "summary": f"{len(out)} affected appointment(s): {len(reg)} registered, {len(out) - len(reg)} walk-in"}


class AltArgs(BaseModel):
    patient_id: str
    specialty: str
    original_doctor_id: str
    original_date: str
    preferred_time: str | None = None
    preferred_mode: str | None = None
    usual_doctor_id: str | None = None
    home_locality: str | None = None
    days: int = 4
    exclude_slot_ids: list[str] = []


@tool("find_alternatives", AltArgs, "Rank free alternative slots for a displaced patient using their remembered preferences.")
def find_alternatives(c, patient_id, specialty, original_doctor_id, original_date, preferred_time=None, preferred_mode=None,
                      usual_doctor_id=None, home_locality=None, days=4, exclude_slot_ids=None) -> dict:
    from backend.tools.doctors import _query_slots

    start = max(date.fromisoformat(original_date), date.today())
    end = start + timedelta(days=days)
    modes = ["in_person", "tele"]
    slots = _query_slots(c, specialty, None, start.isoformat(), end.isoformat(), None, None, None, modes, patient_id,
                         set(exclude_slot_ids or []))
    ranked = []
    for s in slots:
        sc, why = 0.0, []
        if s["doctor_id"] == original_doctor_id:
            sc += 3
            why.append("same doctor as the cancelled appointment")
        if usual_doctor_id and s["doctor_id"] == usual_doctor_id and s["doctor_id"] != original_doctor_id:
            sc += 2
            why.append("patient's usual doctor")
        sess = "morning" if s["start"] < "12:00" else "evening"
        if preferred_time and preferred_time == sess:
            sc += 2
            why.append(f"{sess} — remembered preference")
        if s["mode"] == "tele":
            if preferred_mode == "tele":
                sc += 2.5
                why.append("teleconsult — remembered preference")
            else:
                sc -= 1.5
        if home_locality and s["locality"] == home_locality and s["mode"] == "in_person":
            sc += 1.5
            why.append(f"near home ({home_locality})")
        dd = (date.fromisoformat(s["date"]) - start).days
        sc -= 0.5 * dd
        sc -= hm_to_min(s["start"]) / 6000
        ranked.append({"score": round(sc, 3), "slot": s, "why": why or ["earliest available"]})
    ranked.sort(key=lambda x: -x["score"])
    top = ranked[:3]
    return {"ok": True, "candidates": top, "count": len(ranked),
            "summary": f"{len(ranked)} alternative(s); best: " + (f"{top[0]['slot']['doctor_name']} {top[0]['slot']['date']} {top[0]['slot']['start']} ({', '.join(top[0]['why'])})" if top else "none")}


class OfferWLArgs(BaseModel):
    slot_id: str
    exclude_patient_ids: list[str] = []


@tool("offer_to_waitlist", OfferWLArgs, "Find the best-matching waitlisted patient for a freed slot (FIFO within matches).")
def offer_to_waitlist(c, slot_id: str, exclude_patient_ids: list[str] | None = None) -> dict:
    with get_session() as s:
        sl = s.get(Slot, slot_id)
        d = s.get(Doctor, sl.doctor_id)
        view = slot_view(s, sl, d)
        rows = s.query(WaitlistEntry).filter(and_(WaitlistEntry.specialty == d.specialty, WaitlistEntry.status == "waiting")) \
            .order_by(WaitlistEntry.created_at).all()
        cands = []
        for w in rows:
            if w.patient_id in (exclude_patient_ids or []):
                continue
            if not (w.date_from <= sl.date <= w.date_to):
                continue
            if w.doctor_id and w.doctor_id != d.id:
                continue
            sc, why = 10.0, [f"waiting since {time.strftime('%H:%M', time.localtime(w.created_at))} (FIFO)"]
            sess = "morning" if sl.start < "12:00" else "evening"
            if w.time_pref == sess:
                sc += 2
                why.append(f"wanted {sess}")
            if w.locality and w.locality == view["locality"]:
                sc += 1
                why.append(f"wanted {w.locality}")
            sc -= rows.index(w) * 0.5
            cands.append({"waitlist_id": w.id, "patient_id": w.patient_id, "score": sc, "why": why})
    cands.sort(key=lambda x: -x["score"])
    best = cands[0] if cands else None
    return {"ok": True, "match": best, "candidates": cands[:5], "slot": view,
            "summary": (f"best match {best['patient_id']} ({', '.join(best['why'])})" if best else "no waitlisted patient matches this slot")}


# ============================================================================ proactive offer graph
class PState(TypedDict, total=False):
    run_id: str
    offer_id: str
    result: dict


def _confirm(state: PState) -> dict:
    c = ctx(state["run_id"])
    with get_session() as s:
        o = s.get(Offer, state["offer_id"])
        payload = json.loads(o.payload)
        kind, pid, slot_id, old, wl = o.kind, o.patient_id, o.slot_id, o.old_appointment_id, o.waitlist_id
    if not c.cache.get("asked"):
        c.cache["asked"] = True
        c.trace("event_watcher", "approval_request", f"Waiting for {pid} to confirm the proactive offer (interrupt).",
                {"kind": "offer", "offer_id": state["offer_id"], "offer": payload})
    decision = interrupt({"kind": "offer", "offer_id": state["offer_id"], "run_id": c.run_id, "offer": payload})
    ok = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    c.trace("human", "decision", f"{pid} {'ACCEPTED' if ok else 'DECLINED'} offer {state['offer_id']}", {"approved": ok})
    if ok:
        tok = c.issue_approval(state["offer_id"])
        if kind == "reschedule":
            r = call_tool(c, AGENT, "reschedule_appointment", {"appointment_id": old, "new_slot_id": slot_id,
                                                              "proposal_id": state["offer_id"], "approval_token": tok},
                          reason="patient confirmed — execute the gated reschedule")
        else:
            r = call_tool(c, AGENT, "book_slot", {"slot_id": slot_id, "patient_id": pid, "proposal_id": state["offer_id"],
                                                  "approval_token": tok, "reason": "waitlist fill"},
                          reason="patient confirmed — execute the gated booking")
        status = "accepted" if r.get("ok") else "failed"
        appt = r.get("appointment")
        with get_session() as s:
            o = s.get(Offer, state["offer_id"])
            o.status = status
            if wl and r.get("ok"):
                w = s.get(WaitlistEntry, wl)
                w.status = "fulfilled"
            p = s.get(Patient, pid)
            name = p.name
        if r.get("ok"):
            from backend.agents.notification import notify

            notify(c, "rescheduled", {**appt, "patient_name": name}, pid)
        result = {"status": status, "appointment": appt, "error": r.get("error")}
    else:
        call_tool(c, AGENT, "release_hold", {"slot_id": slot_id}, reason="patient declined — free the slot")
        with get_session() as s:
            o = s.get(Offer, state["offer_id"])
            o.status = "declined"
            if wl:
                s.get(WaitlistEntry, wl).status = "waiting"
            if kind == "reschedule" and old:
                a = s.get(Appointment, old)
                sl = s.get(Slot, a.slot_id)
                if sl.status == "cancelled":
                    a.status, a.notes = "cancelled", "doctor cancelled; patient declined the alternative"
        result = {"status": "declined"}
    with get_session() as s:
        rr = s.get(RunRecord, c.run_id)
        if rr:
            rr.status, rr.outcome, rr.updated_at = "done", result["status"], time.time()
    bus.emit(c.run_id, "system", "run_status", f"offer {state['offer_id']} {result['status']}", {"status": "done", "offer": result})
    return {"result": result}


_pgraph = None


def proactive_graph():
    global _pgraph
    if _pgraph is None:
        g = StateGraph(PState)
        g.add_node("confirm", _confirm)
        g.add_edge(START, "confirm")
        g.add_edge("confirm", END)
        _pgraph = g.compile(checkpointer=InMemorySaver())
    return _pgraph


def _cfg(run_id):
    return {"configurable": {"thread_id": run_id}}


# ============================================================================ planning an offer
def _prefs_for(c, pid: str) -> dict:
    prof = call_tool(c, "memory", "get_patient_profile", {"patient_id": pid}, reason="displaced patient — load stored preferences")
    rec = call_tool(c, "memory", "recall_memory", {"patient_id": pid, "query": "prefers time of day teleconsultation usual doctor area", "k": 4},
                    reason="use long-term memory to pick an alternative the patient will actually accept")
    from backend.agents.memory import _prefs_from_hits

    prefs = _prefs_from_hits(rec.get("hits", []))
    p = prof.get("profile", {})
    prefs.setdefault("time", p.get("preferred_time"))
    prefs.setdefault("mode", p.get("preferred_mode"))
    prefs["home_locality"] = p.get("locality")
    prefs["usual_doctor_id"] = (p.get("usual_doctor") or {}).get("doctor_id")
    prefs["name"] = p.get("name", pid)
    return prefs


def _create_offer(parent, event_id: str, kind: str, pid: str, slot: dict, why: list[str], old_appt: dict | None,
                  waitlist_id: str | None, prefs: dict) -> dict:
    rid = "px-" + uuid.uuid4().hex[:8]
    c = new_context(rid, pid, kind="proactive")
    c.offline = parent.offline
    bus.emit(rid, "system", "run_status", f"proactive offer run for {pid} (parent event {event_id})",
             {"status": "started", "patient_id": pid, "parent": parent.run_id, "proactive": True})
    h = call_tool(c, AGENT, "hold_slot", {"slot_id": slot["slot_id"], "patient_id": pid, "ttl_seconds": PROACTIVE_HOLD_TTL_SECONDS},
                  reason="hold the alternative while the patient is asked (proactive, no prompt)")
    if not h.get("ok"):
        return {"ok": False, "error": h.get("error")}
    v = call_tool(c, "critic", "verify_slot_free", {"slot_id": slot["slot_id"]}, reason="critic re-checks before the patient is told")
    est = call_tool(c, AGENT, "estimate_cost", {"patient_id": pid, "doctor_id": slot["doctor_id"], "mode": slot["mode"]},
                    reason="offer must show the real cost")
    oid = "OF-" + uuid.uuid4().hex[:6].upper()
    payload = {"offer_id": oid, "kind": kind, "patient_id": pid, "patient_name": prefs.get("name", pid), "slot": slot,
               "why": why, "old_appointment": old_appt, "waitlist_id": waitlist_id, "cost": est.get("estimate"),
               "critic": "APPROVE" if v.get("pass") else "REVISE", "event_id": event_id,
               "expires_in_min": PROACTIVE_HOLD_TTL_SECONDS // 60}
    with get_session() as s:
        s.add(Offer(id=oid, run_id=rid, event_id=event_id, patient_id=pid, kind=kind,
                    old_appointment_id=old_appt["appointment_id"] if old_appt else None, waitlist_id=waitlist_id,
                    slot_id=slot["slot_id"], status="pending", payload=json.dumps(payload, default=str), created_at=time.time()))
        s.add(RunRecord(run_id=rid, patient_id=pid, kind="proactive", user_text=f"[event {event_id}]", status="waiting",
                        outcome="offer", created_at=time.time(), updated_at=time.time(), summary="{}"))
        if waitlist_id:
            s.get(WaitlistEntry, waitlist_id).status = "offered"
    mode = "video consultation" if slot["mode"] == "tele" else slot["hospital_name"]
    if kind == "reschedule":
        body = (f"Hi {prefs.get('name', '').split()[0]}, {old_appt['doctor_name']} is unavailable on {date_label(old_appt['date'])} {old_appt['start']}. "
                f"We are holding {slot['doctor_name']} on {date_label(slot['date'])} at {slot['start']} ({mode}) for you — "
                f"{', '.join(why)}. Open the app to confirm (held {PROACTIVE_HOLD_TTL_SECONDS // 60} min).")
        subj = "Your appointment needs rescheduling"
    else:
        body = (f"Good news {prefs.get('name', '').split()[0]}! A {SPECIALTY_LABEL.get(slot['specialty'], slot['specialty'])} slot opened: "
                f"{slot['doctor_name']} on {date_label(slot['date'])} at {slot['start']} ({mode}). It's held for you for "
                f"{PROACTIVE_HOLD_TTL_SECONDS // 60} min — open the app to confirm.")
        subj = "A slot opened up for you"
    call_tool(c, "notification", "send_notification", {"patient_id": pid, "subject": subj, "body": body, "kind": "offer"},
              reason="tell the patient proactively; booking still needs their confirmation")
    c.trace(AGENT, "offer", f"Offer {oid} to {pid}: {slot['doctor_name']} {slot['date']} {slot['start']} ({slot['mode']}) — {', '.join(why)}",
            payload)
    parent.trace(AGENT, "offer", f"Offer {oid} → {pid}: {slot['doctor_name']} {slot['date']} {slot['start']} ({', '.join(why)})", payload)
    proactive_graph().invoke({"run_id": rid, "offer_id": oid}, _cfg(rid))  # runs until the confirmation interrupt
    return {"ok": True, "offer_id": oid, "run_id": rid}


# ============================================================================ event handling
def handle_event_sync(event: dict) -> dict:
    """Entry point for both the asyncio event bus (via to_thread) and scripts/tests."""
    event_id = event.get("event_id") or "EV-" + uuid.uuid4().hex[:6].upper()
    rid = "ev-" + uuid.uuid4().hex[:8]
    c = new_context(rid, "SYSTEM", kind="event")
    with get_session() as s:
        s.add(RunRecord(run_id=rid, patient_id=None, kind="event", user_text=json.dumps(event), status="running",
                        outcome="", created_at=time.time(), updated_at=time.time(), summary="{}"))
    et = event["type"]
    if not event.get("applied"):
        eff = apply_doctor_cancel(event["doctor_id"], event["date"], event["start"], event["end"]) if et == "doctor_cancel" \
            else apply_slot_freed(event["slot_id"])
    else:
        eff = event.get("effect", {})
    bus.emit(rid, "system", "run_status", f"event {event_id} received", {"status": "started", "event": event, "proactive": True})
    c.trace(AGENT, "event_trigger", f"Woke up on hospital event '{et}' — no user prompt. {json.dumps({k: v for k, v in event.items() if k in ('doctor_id', 'date', 'start', 'end', 'slot_id')})}",
            {"event_id": event_id, "event": event, "effect": eff})
    c.bb.write(AGENT, "goal", f"React to {et} ({event_id})")
    c.bb.write(AGENT, "events", {"event_id": event_id, **event, "effect": eff})
    offers, affected = [], 0
    if et == "doctor_cancel":
        with get_session() as s:
            d = s.get(Doctor, event["doctor_id"])
            dname, spec = d.name, d.specialty
        r = call_tool(c, AGENT, "get_affected_appointments", {k: event[k] for k in ("doctor_id", "date", "start", "end")},
                      reason=f"{dname} cancelled {event['start']}–{event['end']} on {event['date']}: who is affected?")
        appts = r.get("appointments", [])
        affected = len(appts)
        c.bb.write(AGENT, "facts", {"affected": appts, "doctor": dname})
        walk = [a for a in appts if not a["patient_id"]]
        if walk:
            c.trace.decision(AGENT, f"{len(walk)} walk-in appointment(s) have no app profile → front desk will phone them (logged).")
        for a in [a for a in appts if a["patient_id"]]:
            pid = a["patient_id"]
            c.trace.thought(AGENT, f"Re-homing {a['patient_name']} ({pid}) — was {a['start']} with {dname}.")
            prefs = _prefs_for(c, pid)
            alt = call_tool(c, AGENT, "find_alternatives", {
                "patient_id": pid, "specialty": spec, "original_doctor_id": event["doctor_id"], "original_date": event["date"],
                "preferred_time": prefs.get("time"), "preferred_mode": prefs.get("mode"), "usual_doctor_id": prefs.get("usual_doctor_id"),
                "home_locality": prefs.get("home_locality"),
                "exclude_slot_ids": [o["slot_id"] for o in offers]}, reason="memory-aware alternatives for this patient")
            cands = alt.get("candidates", [])
            made = False
            for cand in cands:
                res = _create_offer(c, event_id, "reschedule", pid, cand["slot"], cand["why"], a, None, prefs)
                if res.get("ok"):
                    offers.append({"offer_id": res["offer_id"], "patient_id": pid, "slot_id": cand["slot"]["slot_id"], "run_id": res["run_id"]})
                    made = True
                    break
            if not made:
                c.trace.decision(AGENT, f"No alternative found for {pid} — not inventing one; added to front-desk call list.")
    elif et == "slot_freed":
        sid = event["slot_id"]
        tried: list[str] = []
        for _ in range(3):
            r = call_tool(c, AGENT, "offer_to_waitlist", {"slot_id": sid, "exclude_patient_ids": tried},
                          reason="a slot opened: give it to the best-matching waitlisted patient first")
            m = r.get("match")
            if not m:
                c.trace.thought(AGENT, "No waitlisted patient matches — slot stays open for normal booking.")
                break
            affected = 1
            prefs = _prefs_for(c, m["patient_id"])
            res = _create_offer(c, event_id, "waitlist_fill", m["patient_id"], r["slot"], m["why"], None, m["waitlist_id"], prefs)
            if res.get("ok"):
                offers.append({"offer_id": res["offer_id"], "patient_id": m["patient_id"], "slot_id": sid, "run_id": res["run_id"]})
                break
            tried.append(m["patient_id"])
    summary = {"event_id": event_id, "run_id": rid, "type": et, "affected": affected, "offers": offers}
    c.bb.write(AGENT, "decisions", {"type": "proactive_summary", **summary})
    with get_session() as s:
        rr = s.get(RunRecord, rid)
        rr.status, rr.outcome, rr.updated_at, rr.summary = "done", f"{len(offers)} offer(s)", time.time(), json.dumps(summary)
    bus.emit(rid, "system", "run_status", f"event {event_id} handled: {affected} affected, {len(offers)} offer(s) sent",
             {"status": "done", **summary})
    return summary


def respond_offer(offer_id: str, accept: bool) -> dict:
    with get_session() as s:
        o = s.get(Offer, offer_id)
        if o is None:
            return {"status": "error", "error": "no such offer"}
        if o.status != "pending":
            return {"status": o.status, "error": "offer already resolved"}
        rid = o.run_id
    out = proactive_graph().invoke(Command(resume={"approved": accept}), _cfg(rid))
    return out.get("result", {"status": "error"})


def list_offers(patient_id: str | None = None, status: str | None = None) -> list[dict]:
    with get_session() as s:
        q = s.query(Offer)
        if patient_id:
            q = q.filter(Offer.patient_id == patient_id)
        if status:
            q = q.filter(Offer.status == status)
        rows = q.order_by(Offer.created_at.desc()).all()
        return [{"offer_id": o.id, "run_id": o.run_id, "event_id": o.event_id, "patient_id": o.patient_id, "kind": o.kind,
                 "status": o.status, "created_at": o.created_at, **{k: v for k, v in json.loads(o.payload).items() if k in
                 ("slot", "why", "old_appointment", "cost", "patient_name", "critic", "expires_in_min")}} for o in rows]
