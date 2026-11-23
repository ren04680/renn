"""Booking-side tools: soft holds, GATED booking/rescheduling, waitlist.

GATED = the tool refuses to write unless it receives an approval token that only the human-approval
node (LangGraph `interrupt()`) can mint. An LLM can call it, but it can never succeed on its own.
Race condition: booking is one conditional UPDATE inside a transaction; if the slot was taken in the
meantime the tool reports `race=True` and the Supervisor re-plans (never double-books, never invents).
"""
from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, update

from backend.config import HOLD_TTL_SECONDS
from backend.core.context import RunContext
from backend.db.models import Appointment, Doctor, Patient, Slot, WaitlistEntry
from backend.db.session import get_session
from backend.tools.common import slot_view
from backend.tools.policy import get_policy
from backend.tools.registry import tool


def _new_appt_id() -> str:
    return "A" + uuid.uuid4().hex[:6].upper()


class HoldArgs(BaseModel):
    slot_id: str
    patient_id: str
    ttl_seconds: int = Field(HOLD_TTL_SECONDS, description="Soft-hold time-to-live (default 5 minutes)")


@tool("hold_slot", HoldArgs, "Place a soft hold (TTL, default 5 min) on a free slot while the patient decides. Not a booking.")
def hold_slot(c: RunContext, slot_id: str, patient_id: str, ttl_seconds: int = HOLD_TTL_SECONDS) -> dict:
    now = time.time()
    with get_session() as s:
        res = s.execute(
            update(Slot)
            .where(Slot.id == slot_id,
                   or_(Slot.status == "free",
                       and_(Slot.status == "held", or_(Slot.held_by == c.run_id, Slot.hold_expires < now))))
            .values(status="held", held_by=c.run_id, hold_expires=now + ttl_seconds)
        )
        if res.rowcount != 1:
            sl = s.get(Slot, slot_id)
            return {"ok": False, "race": True, "error": f"Slot {slot_id} is no longer free (status={sl.status if sl else 'missing'})."}
        view = slot_view(s, s.get(Slot, slot_id))
    return {"ok": True, "slot": view, "expires_in": ttl_seconds,
            "summary": f"held {slot_id} ({view['doctor_name']}, {view['date']} {view['start']}) for {ttl_seconds // 60} min"}


class ReleaseArgs(BaseModel):
    slot_id: str


@tool("release_hold", ReleaseArgs, "Release a soft hold this run placed.")
def release_hold(c: RunContext, slot_id: str) -> dict:
    with get_session() as s:
        res = s.execute(update(Slot).where(Slot.id == slot_id, Slot.status == "held", Slot.held_by == c.run_id)
                        .values(status="free", held_by=None, hold_expires=None))
    return {"ok": True, "released": res.rowcount == 1, "summary": f"released hold on {slot_id}" if res.rowcount else "no hold to release"}


def _book_in_session(s, c: RunContext, slot_id: str, patient_id: str, reason: str) -> tuple[bool, str | dict]:
    now = time.time()
    res = s.execute(
        update(Slot)
        .where(Slot.id == slot_id,
               or_(Slot.status == "free",
                   and_(Slot.status == "held", or_(Slot.held_by == c.run_id, Slot.hold_expires < now))))
        .values(status="booked", held_by=None, hold_expires=None, version=Slot.version + 1)
    )
    if res.rowcount != 1:
        sl = s.get(Slot, slot_id)
        return False, f"Slot {slot_id} was taken by someone else (status={sl.status if sl else 'missing'})."
    sl = s.get(Slot, slot_id)
    p = s.get(Patient, patient_id)
    appt = Appointment(id=_new_appt_id(), patient_id=patient_id, patient_name=p.name if p else patient_id,
                       slot_id=slot_id, doctor_id=sl.doctor_id, status="booked", created_at=now, run_id=c.run_id,
                       reason=reason)
    s.add(appt)
    s.flush()
    return True, {"appointment_id": appt.id, **slot_view(s, sl), "patient_id": patient_id}


class BookArgs(BaseModel):
    slot_id: str
    patient_id: str
    proposal_id: str = ""
    approval_token: str | None = Field(None, description="Issued only by the human-approval step. Agents cannot create it.")
    reason: str = ""


@tool("book_slot", BookArgs, "GATED. Book a slot for a patient. Requires a human approval token; without it the call is blocked.", gated=True)
def book_slot(c: RunContext, slot_id: str, patient_id: str, proposal_id: str = "", approval_token=None, reason: str = "") -> dict:
    if not c.check_approval(proposal_id, approval_token):
        c.trace("guardrail", "error", "BLOCKED book_slot: no valid human approval token", {"slot_id": slot_id})
        return {"ok": False, "blocked": True,
                "error": "BLOCKED: book_slot requires explicit human approval. Propose the slot; the patient must approve it first."}
    with get_session() as s:
        ok, out = _book_in_session(s, c, slot_id, patient_id, reason)
        if not ok:
            s.rollback()
            return {"ok": False, "race": True, "error": out}
    return {"ok": True, "appointment": out,
            "summary": f"BOOKED {out['appointment_id']}: {out['doctor_name']} {out['date']} {out['start']} for {patient_id}"}


class JointBookArgs(BaseModel):
    bookings: list[dict] = Field(description="[{slot_id, patient_id, reason}] booked atomically (all or nothing)")
    proposal_id: str = ""
    approval_token: str | None = None


@tool("book_joint", JointBookArgs, "GATED. Atomically book several linked slots (all-or-nothing). Requires a human approval token.", gated=True)
def book_joint(c: RunContext, bookings: list[dict], proposal_id: str = "", approval_token=None) -> dict:
    if not c.check_approval(proposal_id, approval_token):
        c.trace("guardrail", "error", "BLOCKED book_joint: no valid human approval token", {})
        return {"ok": False, "blocked": True, "error": "BLOCKED: requires explicit human approval."}
    out = []
    with get_session() as s:
        for b in bookings:
            ok, res = _book_in_session(s, c, b["slot_id"], b["patient_id"], b.get("reason", ""))
            if not ok:
                s.rollback()
                return {"ok": False, "race": True, "error": res + " — nothing was booked (all-or-nothing)."}
            out.append(res)
    return {"ok": True, "appointments": out,
            "summary": "BOOKED " + "; ".join(f"{a['appointment_id']} {a['doctor_name']} {a['start']} for {a['patient_id']}" for a in out)}


class RescheduleArgs(BaseModel):
    appointment_id: str
    new_slot_id: str
    proposal_id: str = ""
    approval_token: str | None = None


@tool("reschedule_appointment", RescheduleArgs, "GATED. Move an existing appointment to a new slot (atomic). Requires the patient's approval token.", gated=True)
def reschedule_appointment(c: RunContext, appointment_id: str, new_slot_id: str, proposal_id: str = "", approval_token=None) -> dict:
    if not c.check_approval(proposal_id, approval_token):
        c.trace("guardrail", "error", "BLOCKED reschedule_appointment: no valid approval token", {})
        return {"ok": False, "blocked": True, "error": "BLOCKED: rescheduling requires the patient's explicit confirmation."}
    with get_session() as s:
        old = s.get(Appointment, appointment_id)
        if old is None or old.status != "booked":
            return {"ok": False, "error": f"Appointment {appointment_id} is not active."}
        ok, res = _book_in_session(s, c, new_slot_id, old.patient_id, f"rescheduled from {appointment_id}")
        if not ok:
            s.rollback()
            return {"ok": False, "race": True, "error": res}
        old.status = "rescheduled"
        old.notes = f"moved to {res['appointment_id']}"
        old_slot = s.get(Slot, old.slot_id)
        if old_slot and old_slot.status == "booked":
            old_slot.status = "free"
    return {"ok": True, "appointment": res, "old_appointment_id": appointment_id,
            "summary": f"RESCHEDULED {appointment_id} → {res['appointment_id']} ({res['doctor_name']} {res['date']} {res['start']})"}


class WaitlistArgs(BaseModel):
    patient_id: str
    specialty: str
    doctor_id: str | None = None
    date_from: str
    date_to: str
    time_pref: str | None = None
    locality: str | None = None
    mode: str = "any"
    goal_ref: str = "G1"


@tool("add_to_waitlist", WaitlistArgs, "Add the patient to the waitlist. Only allowed once the relaxation ladder is exhausted.")
def add_to_waitlist(c: RunContext, patient_id: str, specialty: str, date_from: str, date_to: str, doctor_id=None,
                    time_pref=None, locality=None, mode="any", goal_ref="G1") -> dict:
    pol = get_policy(c, goal_ref)
    if pol is not None:
        nxt = pol.next_allowed(c)
        if nxt is not None:
            return {"ok": False, "error": f"Not yet: the relaxation ladder is not exhausted (next allowed step: '{nxt}'). Keep trying before waitlisting."}
    wid = "W" + uuid.uuid4().hex[:5].upper()
    with get_session() as s:
        s.add(WaitlistEntry(id=wid, patient_id=patient_id, specialty=specialty, doctor_id=doctor_id, date_from=date_from,
                            date_to=date_to, time_pref=time_pref, locality=locality, mode=mode, status="waiting",
                            created_at=time.time(), run_id=c.run_id))
        pos = s.query(WaitlistEntry).filter(WaitlistEntry.specialty == specialty, WaitlistEntry.status == "waiting").count()
    return {"ok": True, "waitlist_id": wid, "position": pos,
            "summary": f"waitlisted {patient_id} for {specialty} ({date_from}..{date_to}), position #{pos}"}


class PatientApptArgs(BaseModel):
    patient_id: str


@tool("get_patient_appointments", PatientApptArgs, "Upcoming booked appointments for a patient.")
def get_patient_appointments(c: RunContext, patient_id: str) -> dict:
    from backend.tools.common import now_hm

    today, _ = now_hm()
    with get_session() as s:
        rows = (s.query(Appointment, Slot).join(Slot, Slot.id == Appointment.slot_id)
                .filter(Appointment.patient_id == patient_id, Appointment.status == "booked", Slot.date >= today)
                .order_by(Slot.date, Slot.start).all())
        out = [{"appointment_id": a.id, **slot_view(s, sl)} for a, sl in rows]
    return {"ok": True, "appointments": out,
            "summary": f"{len(out)} upcoming appointment(s)" + (": " + "; ".join(f"{a['doctor_name']} {a['date']} {a['start']}" for a in out[:3]) if out else "")}


def doctor_of(slot_id: str) -> Doctor | None:
    with get_session() as s:
        sl = s.get(Slot, slot_id)
        return s.get(Doctor, sl.doctor_id) if sl else None
