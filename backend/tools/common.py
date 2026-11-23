"""Shared DB helpers for tools."""
from __future__ import annotations

import time
from datetime import date, datetime

from backend.db.models import Appointment, Doctor, Hospital, Patient, Slot
from backend.db.session import get_session


def now_hm() -> tuple[str, str]:
    n = datetime.now()
    return n.date().isoformat(), n.strftime("%H:%M")


def slot_available_for(sl: Slot, run_id: str | None, now: float | None = None) -> bool:
    now = now or time.time()
    if sl.status == "free":
        return True
    if sl.status == "held":
        return (sl.hold_expires or 0) < now or (run_id is not None and sl.held_by == run_id)
    return False


def slot_view(s, sl: Slot, doc: Doctor | None = None, hosp: Hospital | None = None) -> dict:
    doc = doc or s.get(Doctor, sl.doctor_id)
    hosp = hosp or s.get(Hospital, doc.hospital_id)
    return {
        "slot_id": sl.id, "doctor_id": doc.id, "doctor_name": doc.name, "specialty": doc.specialty,
        "hospital_id": hosp.id, "hospital_name": hosp.name, "locality": hosp.locality,
        "date": sl.date, "start": sl.start, "end": sl.end, "mode": sl.mode, "status": sl.status,
        "fee": doc.tele_fee if sl.mode == "tele" else doc.fee, "rating": doc.rating,
    }


def patient_busy(s, patient_id: str | None) -> set[tuple[str, str]]:
    if not patient_id:
        return set()
    rows = (
        s.query(Slot.date, Slot.start)
        .join(Appointment, Appointment.slot_id == Slot.id)
        .filter(Appointment.patient_id == patient_id, Appointment.status == "booked")
        .all()
    )
    return {(d, st) for d, st in rows}


def get_patient(patient_id: str) -> Patient | None:
    with get_session() as s:
        return s.get(Patient, patient_id)


def date_label(iso: str) -> str:
    d = date.fromisoformat(iso)
    today = date.today()
    delta = (d - today).days
    rel = {0: " (today)", 1: " (tomorrow)", 2: " (day after tomorrow)"}.get(delta, "")
    return d.strftime("%a %d %b") + rel


def hm_to_min(hm: str) -> int:
    h, m = map(int, hm.split(":"))
    return h * 60 + m
