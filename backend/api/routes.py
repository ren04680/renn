"""REST routes for the UI."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import MODELS_DIR, PRINCIPLE, SUBMISSION_DIR, settings
from backend.core import vector_memory
from backend.core.blackboard import get_blackboard
from backend.core.events import event_bus
from backend.core.trace import bus
from backend.db.models import (Appointment, Doctor, FamilyLink, Hospital, InsurancePlan, Notification, Patient, RunRecord,
                               Slot, WaitlistEntry)
from backend.db.session import get_session
from backend.tools.registry import AGENT_TOOLS, TOOLS

router = APIRouter()


# ----------------------------------------------------------------------------- meta / settings
@router.get("/health")
def health():
    return {"ok": True}


@router.get("/meta")
def meta():
    today = date.today()
    agents = {a: [{"name": n, "gated": TOOLS[n].gated, "description": TOOLS[n].description} for n in ts if n in TOOLS]
              for a, ts in AGENT_TOOLS.items()}
    return {"principle": PRINCIPLE, "today": today.isoformat(),
            "days": [(today + timedelta(days=i)).isoformat() for i in range(14)],
            "embedder": vector_memory.embedder_name(), "vector_store": vector_memory.store_backend(),
            "agents": agents, "settings": settings.as_dict()}


@router.get("/settings")
def get_settings():
    return settings.as_dict()


class SettingsIn(BaseModel):
    inject_fault: bool | None = None
    offline: bool | None = None


@router.post("/settings")
def set_settings(s: SettingsIn):
    settings.update(inject_fault=s.inject_fault, offline=s.offline)
    bus.emit("system", "system", "run_status", f"settings changed: {settings.as_dict()}", {"settings": settings.as_dict()})
    return settings.as_dict()


@router.post("/reset")
async def reset():
    from scripts.seed import reset_demo

    summary = await asyncio.to_thread(reset_demo, None, False)
    settings.update(inject_fault=False)
    bus.clear()
    bus.emit("system", "system", "run_status", "demo data reset to the known state", {"reset": summary})
    return summary


@router.get("/patients")
def patients():
    with get_session() as s:
        plans = {p.id: p.name for p in s.query(InsurancePlan).all()}
        fam = {}
        for f in s.query(FamilyLink).all():
            fam.setdefault(f.patient_id, []).append({"relation": f.relation, "patient_id": f.relative_id})
        rows = s.query(Patient).order_by(Patient.id).all()
        out = [{"id": p.id, "name": p.name, "age": p.age, "locality": p.locality, "plan": plans.get(p.insurance_plan_id),
                "preferred_time": p.preferred_time, "preferred_mode": p.preferred_mode, "family": fam.get(p.id, [])} for p in rows]
    featured = ["P001", "P014", "P023", "P031", "GUEST"]
    out.sort(key=lambda p: (featured.index(p["id"]) if p["id"] in featured else 99, p["id"]))
    return out


@router.get("/patients/{pid}/memories")
def memories(pid: str):
    from backend.db.models import Memory

    with get_session() as s:
        rows = s.query(Memory).filter(Memory.patient_id == pid).order_by(Memory.created_at.desc()).limit(30).all()
        return [{"id": m.id, "text": m.text, "kind": m.kind, "source": m.source, "created_at": m.created_at} for m in rows]


# ----------------------------------------------------------------------------- chat
class ChatIn(BaseModel):
    patient_id: str = "GUEST"
    message: str
    run_id: str | None = None


class ResumeIn(BaseModel):
    run_id: str
    value: dict


@router.post("/chat")
async def chat(body: ChatIn):
    from backend.core.runner import start_run

    rid = body.run_id or uuid.uuid4().hex[:12]
    return await asyncio.to_thread(start_run, body.message, body.patient_id, rid)


@router.post("/resume")
async def resume(body: ResumeIn):
    from backend.core.runner import resume_run

    return await asyncio.to_thread(resume_run, body.run_id, body.value)


@router.get("/runs")
def runs(patient_id: str | None = None, limit: int = 40):
    with get_session() as s:
        q = s.query(RunRecord)
        if patient_id:
            q = q.filter(RunRecord.patient_id == patient_id)
        rows = q.order_by(RunRecord.created_at.desc()).limit(limit).all()
        return [{"run_id": r.run_id, "patient_id": r.patient_id, "kind": r.kind, "text": r.user_text[:140], "status": r.status,
                 "outcome": r.outcome, "created_at": r.created_at} for r in rows]


@router.get("/runs/{run_id}/events")
def run_events(run_id: str):
    return bus.for_run(run_id)


@router.get("/runs/{run_id}/blackboard")
def run_blackboard(run_id: str):
    bb = get_blackboard(run_id)
    return json.loads(json.dumps(bb.view(), default=str))


@router.get("/events/recent")
def recent_events(since: int = 0, limit: int = 1500):
    return bus.since(since, limit=limit)


# ----------------------------------------------------------------------------- hospital ops
@router.get("/ops/doctors")
def doctors():
    with get_session() as s:
        rows = s.query(Doctor, Hospital).join(Hospital, Hospital.id == Doctor.hospital_id).order_by(Doctor.specialty, Doctor.id).all()
        return [{"id": d.id, "name": d.name, "specialty": d.specialty, "hospital": h.name, "hospital_id": h.id,
                 "locality": h.locality, "fee": d.fee, "rating": d.rating, "tele": d.tele_available} for d, h in rows]


@router.get("/ops/schedule")
def schedule(day: str, specialty: str | None = None):
    now = time.time()
    with get_session() as s:
        q = s.query(Slot, Doctor, Hospital).join(Doctor, Doctor.id == Slot.doctor_id).join(Hospital, Hospital.id == Doctor.hospital_id) \
            .filter(Slot.date == day)
        if specialty:
            q = q.filter(Doctor.specialty == specialty)
        appts = {a.slot_id: a for a in s.query(Appointment).filter(Appointment.status == "booked").all()}
        rows: dict[str, dict] = {}
        for sl, d, h in q.order_by(Doctor.specialty, Doctor.id, Slot.start).all():
            r = rows.setdefault(d.id, {"doctor_id": d.id, "name": d.name, "specialty": d.specialty, "hospital": h.name,
                                       "locality": h.locality, "slots": {}})
            st = sl.status
            if st == "held" and (sl.hold_expires or 0) < now:
                st = "free"
            a = appts.get(sl.id)
            r["slots"][sl.start] = {"slot_id": sl.id, "status": st, "mode": sl.mode,
                                    "patient": (a.patient_id or "walk-in") if a and st in ("booked", "cancelled") else None,
                                    "held_by": sl.held_by if st == "held" else None}
    return {"day": day, "times": ["09:30", "10:00", "10:30", "11:00", "11:30", "16:00", "16:30", "17:00", "17:30", "18:00"],
            "doctors": list(rows.values())}


@router.get("/ops/appointments")
def appointments(limit: int = 60, registered_only: bool = True):
    today = date.today().isoformat()
    with get_session() as s:
        q = s.query(Appointment, Slot, Doctor, Hospital).join(Slot, Slot.id == Appointment.slot_id) \
            .join(Doctor, Doctor.id == Slot.doctor_id).join(Hospital, Hospital.id == Doctor.hospital_id) \
            .filter(Slot.date >= today)
        if registered_only:
            q = q.filter(Appointment.patient_id.isnot(None))
        rows = q.order_by(Appointment.created_at.desc()).limit(limit).all()
        return [{"appointment_id": a.id, "patient_id": a.patient_id, "patient_name": a.patient_name, "status": a.status,
                 "slot_status": sl.status, "doctor": d.name, "specialty": d.specialty, "hospital": h.name, "date": sl.date,
                 "start": sl.start, "mode": sl.mode, "created_at": a.created_at, "notes": a.notes, "run_id": a.run_id}
                for a, sl, d, h in rows]


@router.get("/ops/waitlist")
def waitlist():
    with get_session() as s:
        rows = s.query(WaitlistEntry).order_by(WaitlistEntry.created_at.desc()).all()
        names = {p.id: p.name for p in s.query(Patient).all()}
        return [{"id": w.id, "patient_id": w.patient_id, "patient_name": names.get(w.patient_id), "specialty": w.specialty,
                 "date_from": w.date_from, "date_to": w.date_to, "time_pref": w.time_pref, "locality": w.locality,
                 "status": w.status, "created_at": w.created_at} for w in rows]


@router.get("/ops/notifications")
def notifications(patient_id: str | None = None, limit: int = 50):
    with get_session() as s:
        q = s.query(Notification)
        if patient_id:
            q = q.filter(Notification.patient_id == patient_id)
        rows = q.order_by(Notification.created_at.desc()).limit(limit).all()
        return [{"id": n.id, "patient_id": n.patient_id, "channel": n.channel, "to": n.to, "subject": n.subject, "body": n.body,
                 "kind": n.kind, "created_at": n.created_at, "run_id": n.run_id} for n in rows]


@router.get("/ops/freeable_slots")
def freeable_slots():
    """Booked slots in specialties that have waiting waitlist entries (for the 'Slot freed' simulator)."""
    with get_session() as s:
        wl = s.query(WaitlistEntry).filter(WaitlistEntry.status == "waiting").all()
        out = []
        for w in wl:
            q = s.query(Slot, Doctor, Hospital).join(Doctor, Doctor.id == Slot.doctor_id).join(Hospital, Hospital.id == Doctor.hospital_id) \
                .filter(Doctor.specialty == w.specialty, Slot.status == "booked", Slot.date >= w.date_from, Slot.date <= w.date_to) \
                .order_by(Slot.date, Slot.start).limit(6).all()
            for sl, d, h in q:
                if not any(o["slot_id"] == sl.id for o in out):
                    out.append({"slot_id": sl.id, "label": f"{d.name} ({d.specialty}) · {h.locality} · {sl.date} {sl.start}",
                                "specialty": d.specialty, "for_waitlist": w.patient_id})
        return out[:20]


# ----------------------------------------------------------------------------- events + offers
class CancelIn(BaseModel):
    doctor_id: str
    date: str
    start: str = "09:30"
    end: str = "12:00"


class FreedIn(BaseModel):
    slot_id: str


@router.post("/events/doctor_cancel")
async def doctor_cancel(body: CancelIn):
    eid = await event_bus.publish({"type": "doctor_cancel", **body.model_dump()})
    return {"event_id": eid, "queued": True}


@router.post("/events/slot_freed")
async def slot_freed(body: FreedIn):
    eid = await event_bus.publish({"type": "slot_freed", "slot_id": body.slot_id})
    return {"event_id": eid, "queued": True}


@router.get("/events/{event_id}")
def event_result(event_id: str):
    return event_bus.results.get(event_id) or {"pending": True}


@router.get("/offers")
def offers(patient_id: str | None = None, status: str | None = None):
    from backend.agents.event_watcher import list_offers

    return list_offers(patient_id, status)


class OfferIn(BaseModel):
    accept: bool


@router.post("/offers/{offer_id}/respond")
async def respond(offer_id: str, body: OfferIn):
    from backend.agents.event_watcher import respond_offer

    res = await asyncio.to_thread(respond_offer, offer_id, body.accept)
    if res.get("status") == "error":
        raise HTTPException(404, res.get("error"))
    return res


# ----------------------------------------------------------------------------- metrics
@router.get("/metrics")
def metrics():
    out = {"scenarios": None, "classifier": None}
    p = SUBMISSION_DIR / "test_results.json"
    if p.exists():
        out["scenarios"] = json.loads(p.read_text(encoding="utf-8"))
    m = MODELS_DIR / "metrics.json"
    if m.exists():
        out["classifier"] = json.loads(m.read_text(encoding="utf-8"))
    out["system"] = {"embedder": vector_memory.embedder_name(), "vector_store": vector_memory.store_backend(),
                     "settings": settings.as_dict()}
    return out
