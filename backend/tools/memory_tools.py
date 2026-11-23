"""Memory / Records tools (Unit 3): vector recall over episodic memories + structured records."""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from backend.core import vector_memory
from backend.core.context import RunContext
from backend.db.models import Appointment, Doctor, FamilyLink, Hospital, Patient, Slot, Visit
from backend.db.session import get_session
from backend.tools.common import now_hm, slot_view
from backend.tools.registry import tool


class RecallArgs(BaseModel):
    patient_id: str
    query: str
    k: int = 4


@tool("recall_memory", RecallArgs, "Semantic search over the patient's long-term memories (preferences, past visits, family).")
def recall_memory(c: RunContext, patient_id: str, query: str, k: int = 4) -> dict:
    hits = vector_memory.search(patient_id, query, k)
    for h in hits:
        c.trace("memory", "memory_hit", f"[{h['score']:.2f}] {h['text']}", {"patient_id": patient_id, "query": query, **h})
    return {"ok": True, "hits": hits, "embedder": vector_memory.embedder_name(),
            "summary": f"{len(hits)} memory hit(s) for '{query}'" + (f"; top: {hits[0]['text'][:70]}" if hits else "")}


class HistArgs(BaseModel):
    patient_id: str
    limit: int = 10


@tool("get_visit_history", HistArgs, "Past visits (structured records) and the most frequently seen doctor per specialty.")
def get_visit_history(c: RunContext, patient_id: str, limit: int = 10) -> dict:
    with get_session() as s:
        rows = s.query(Visit).filter(Visit.patient_id == patient_id).order_by(Visit.date.desc()).all()
        docs = {d.id: d for d in s.query(Doctor).all()}
        visits = [{"date": v.date, "doctor_id": v.doctor_id, "doctor_name": docs[v.doctor_id].name, "specialty": v.specialty,
                   "reason": v.reason, "time": v.slot_time, "mode": v.mode} for v in rows]
    freq = Counter(v["doctor_id"] for v in visits)
    top = [{"doctor_id": d, "doctor_name": docs[d].name, "specialty": docs[d].specialty, "visits": n}
           for d, n in freq.most_common(3)]
    times = Counter("evening" if v["time"] >= "16:00" else "morning" for v in visits if v["time"])
    return {"ok": True, "visits": visits[:limit], "count": len(visits), "frequent_doctors": top,
            "time_pattern": dict(times),
            "summary": f"{len(visits)} past visit(s)" + (f"; most seen: {top[0]['doctor_name']} ×{top[0]['visits']}" if top else "")}


class ProfileArgs(BaseModel):
    patient_id: str


@tool("get_patient_profile", ProfileArgs, "Patient profile: stored preferences, insurance, family links, upcoming appointments.")
def get_patient_profile(c: RunContext, patient_id: str) -> dict:
    today, _ = now_hm()
    with get_session() as s:
        p = s.get(Patient, patient_id)
        if not p:
            return {"ok": False, "error": f"Unknown patient {patient_id}"}
        fam = [{"relation": f.relation, "patient_id": f.relative_id, "name": s.get(Patient, f.relative_id).name}
               for f in s.query(FamilyLink).filter(FamilyLink.patient_id == patient_id).all()]
        upcoming = [{"appointment_id": a.id, **slot_view(s, sl)} for a, sl in
                    s.query(Appointment, Slot).join(Slot, Slot.id == Appointment.slot_id)
                    .filter(Appointment.patient_id == patient_id, Appointment.status == "booked", Slot.date >= today)
                    .order_by(Slot.date, Slot.start).all()]
        usual = None
        if p.usual_doctor_id:
            d = s.get(Doctor, p.usual_doctor_id)
            h = s.get(Hospital, d.hospital_id)
            usual = {"doctor_id": d.id, "name": d.name, "specialty": d.specialty, "hospital": h.name, "locality": h.locality}
        prof = {"patient_id": p.id, "name": p.name, "age": p.age, "locality": p.locality, "insurance_plan_id": p.insurance_plan_id,
                "preferred_time": p.preferred_time, "preferred_mode": p.preferred_mode, "usual_doctor": usual,
                "language": p.language, "phone": p.phone, "email": p.email}
    return {"ok": True, "profile": prof, "family": fam, "upcoming": upcoming,
            "summary": f"{p.name} ({p.id}), {p.locality or 'no locality'}, prefers {p.preferred_time or '—'}/{p.preferred_mode or '—'}"
            + (f", usual doctor {usual['name']}" if usual else "") + (f", family: {', '.join(f['relation'] + '=' + f['patient_id'] for f in fam)}" if fam else "")}


class SaveArgs(BaseModel):
    patient_id: str
    text: str = Field(max_length=300)
    kind: str = "episode"


@tool("save_memory", SaveArgs, "Persist a new long-term memory (episode / preference / fact) for the patient.")
def save_memory(c: RunContext, patient_id: str, text: str, kind: str = "episode") -> dict:
    if patient_id == "GUEST":
        return {"ok": False, "error": "Guest sessions are not remembered."}
    mid = vector_memory.add_memory(patient_id, text, kind, source=f"run:{c.run_id}")
    return {"ok": True, "memory_id": mid, "summary": f"saved {kind} memory {mid}: {text[:70]}"}
