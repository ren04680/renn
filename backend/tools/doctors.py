"""Doctor search + availability tools (Scheduling agent)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field

from backend.core.context import RunContext
from backend.db.models import Doctor, Hospital, Slot
from backend.db.session import get_session
from backend.tools.common import hm_to_min, now_hm, patient_busy, slot_available_for, slot_view
from backend.tools.policy import get_policy
from backend.tools.registry import tool

SPECIALTY_INFO = {
    "cardiology": "Heart and blood-vessel conditions: chest pain, palpitations, blood pressure.",
    "dermatology": "Skin, hair and nail conditions: rashes, acne, eczema, hair fall.",
    "orthopedics": "Bones, joints and muscles: knee/back/shoulder pain, sprains, fractures.",
    "neurology": "Brain and nerves: migraine, numbness, seizures, dizziness.",
    "ent": "Ear, nose and throat: ear pain, sinusitis, sore throat, hearing.",
    "pediatrics": "Children's health: fever, cough, vaccinations, growth.",
    "general_medicine": "Common illnesses and check-ups: fever, cold, diabetes, BP review.",
    "gastroenterology": "Digestive system: acidity, stomach pain, indigestion, liver.",
}


class SearchDoctorsArgs(BaseModel):
    specialty: str | None = Field(None, description="Specialty key, e.g. cardiology, dermatology, orthopedics, neurology, ent, pediatrics, general_medicine, gastroenterology")
    locality: str | None = Field(None, description="Pune locality to restrict to (omit for all of Pune)")
    doctor_id: str | None = None
    name: str | None = Field(None, description="Part of the doctor's name, e.g. 'Mehra'")


@tool("search_doctors", SearchDoctorsArgs, "Find doctors by specialty and/or locality, id or name. Returns ids, hospital, fee, rating, tele availability.")
def search_doctors(c: RunContext, specialty=None, locality=None, doctor_id=None, name=None) -> dict:
    with get_session() as s:
        q = s.query(Doctor, Hospital).join(Hospital, Hospital.id == Doctor.hospital_id)
        if specialty:
            q = q.filter(Doctor.specialty == specialty)
        if locality:
            q = q.filter(Hospital.locality == locality)
        if doctor_id:
            q = q.filter(Doctor.id == doctor_id)
        if name:
            q = q.filter(Doctor.name.ilike(f"%{name}%"))
        rows = q.order_by(Doctor.rating.desc()).all()
        docs = [{"doctor_id": d.id, "name": d.name, "specialty": d.specialty, "hospital_id": h.id, "hospital": h.name,
                 "locality": h.locality, "rating": d.rating, "fee": d.fee, "tele_fee": d.tele_fee,
                 "tele_available": d.tele_available, "languages": d.languages} for d, h in rows]
    where = f" in {locality}" if locality else " across Pune"
    return {"ok": True, "doctors": docs, "count": len(docs),
            "summary": f"{len(docs)} {specialty or ''} doctor(s){where}" + (f": {', '.join(d['name'] for d in docs[:4])}" if docs else "")}


class SpecialtyArgs(BaseModel):
    specialty: str


@tool("get_specialty_info", SpecialtyArgs, "Describe a specialty and how many doctors / what fee range the hospital network has.")
def get_specialty_info(c: RunContext, specialty: str) -> dict:
    with get_session() as s:
        docs = s.query(Doctor).filter(Doctor.specialty == specialty).all()
    if not docs:
        return {"ok": False, "error": f"Unknown specialty '{specialty}'."}
    fees = [d.fee for d in docs]
    return {"ok": True, "specialty": specialty, "description": SPECIALTY_INFO.get(specialty, ""), "doctors": len(docs),
            "fee_range": [min(fees), max(fees)],
            "summary": f"{specialty}: {len(docs)} doctors, fees ₹{min(fees)}–₹{max(fees)}"}


class AvailabilityArgs(BaseModel):
    specialty: str | None = None
    doctor_ids: list[str] | None = None
    date_from: str | None = Field(None, description="ISO date; defaults to the goal's current constraint")
    date_to: str | None = None
    time_from: str | None = Field(None, description="HH:MM; defaults to the goal's current constraint")
    time_to: str | None = None
    locality: str | None = None
    modes: list[str] | None = Field(None, description="in_person and/or tele; defaults to what the policy currently allows")
    patient_id: str | None = None
    exclude_slot_ids: list[str] | None = None
    goal_ref: str = "G1"
    limit: int = 20


def _query_slots(c: RunContext, specialty, doctor_ids, date_from, date_to, time_from, time_to, locality, modes,
                 patient_id, exclude) -> list[dict]:
    today_iso, now_t = now_hm()
    out = []
    with get_session() as s:
        q = (s.query(Slot, Doctor, Hospital).join(Doctor, Doctor.id == Slot.doctor_id)
             .join(Hospital, Hospital.id == Doctor.hospital_id)
             .filter(Slot.date >= date_from, Slot.date <= date_to, Slot.status.in_(["free", "held"])))
        if specialty:
            q = q.filter(Doctor.specialty == specialty)
        if doctor_ids:
            q = q.filter(Doctor.id.in_(doctor_ids))
        if locality:
            q = q.filter(Hospital.locality == locality)
        if modes:
            q = q.filter(Slot.mode.in_(modes))
        busy = patient_busy(s, patient_id)
        for sl, d, h in q.order_by(Slot.date, Slot.start).all():
            if not slot_available_for(sl, c.run_id):
                continue
            if sl.date == today_iso and sl.start <= now_t:
                continue
            if time_from and sl.start < time_from:
                continue
            if time_to and sl.start >= time_to:
                continue
            if sl.id in exclude or (sl.date, sl.start) in busy:
                continue
            out.append(slot_view(s, sl, d, h))
    return out


@tool("get_availability", AvailabilityArgs,
      "List FREE slots matching the goal's current (policy-checked) constraints. Omitted arguments default to the "
      "current constraints; asking for anything wider than the policy allows returns an error.")
def get_availability(c: RunContext, specialty=None, doctor_ids=None, date_from=None, date_to=None, time_from=None,
                     time_to=None, locality=None, modes=None, patient_id=None, exclude_slot_ids=None, goal_ref="G1",
                     limit=20) -> dict:
    pol = get_policy(c, goal_ref)
    cur = pol.current if pol else {}
    specialty = specialty or cur.get("specialty")
    date_from = date_from or cur.get("date_from") or (date.today() + timedelta(days=1)).isoformat()
    date_to = date_to or cur.get("date_to") or date_from
    time_from = time_from or cur.get("time_from")
    time_to = time_to or cur.get("time_to")
    locality = locality or cur.get("locality")
    modes = modes or cur.get("modes") or ["in_person"]
    patient_id = patient_id or cur.get("patient_id")
    if pol:
        errs = []
        if specialty != cur.get("specialty"):
            errs.append(f"specialty must be '{cur.get('specialty')}' (the requested specialty)")
        if date_from < cur["date_from"] or date_to > cur["date_to"]:
            errs.append(f"dates must stay within {cur['date_from']}..{cur['date_to']} (relax with next_day when allowed)")
        if cur.get("time_from") and (time_from < cur["time_from"] or (time_to or "24:00") > cur["time_to"]):
            errs.append(f"time must stay within {cur['time_from']}–{cur['time_to']} (relax with widen_time when allowed)")
        if cur.get("locality") and locality != cur["locality"]:
            errs.append(f"locality must be {cur['locality']} (relax with widen_area when allowed)")
        bad_modes = [m for m in modes if m not in cur.get("modes", ["in_person"])]
        if bad_modes:
            errs.append(f"mode(s) {bad_modes} not permitted yet (relax with allow_tele when allowed)")
        if cur.get("doctor_id"):
            if doctor_ids and doctor_ids != [cur["doctor_id"]]:
                errs.append(f"the patient asked for doctor {cur['doctor_id']} only")
            doctor_ids = [cur["doctor_id"]]
        if errs:
            return {"ok": False, "error": "Outside the policy envelope: " + "; ".join(errs)}
    exclude = set(exclude_slot_ids or []) | set(c.cache.get(f"exclude_{goal_ref}", []))
    slots = _query_slots(c, specialty, doctor_ids, date_from, date_to, time_from, time_to, locality, modes, patient_id, exclude)
    win = f"{date_from}" + (f"..{date_to}" if date_to != date_from else "") + (f" {time_from}–{time_to}" if time_from else " (any time)")
    return {"ok": True, "slots": slots[:limit], "count": len(slots),
            "searched": {"specialty": specialty, "date_from": date_from, "date_to": date_to, "time_from": time_from,
                         "time_to": time_to, "locality": locality, "modes": modes, "doctor_ids": doctor_ids},
            "summary": (f"{len(slots)} free slot(s) for {specialty} {win}" + (f" in {locality}" if locality else "")
                        + (f", modes={'+'.join(modes)}" if modes != ['in_person'] else ""))}


class GoalSpec(BaseModel):
    patient_id: str
    specialty: str
    label: str = ""


class JointArgs(BaseModel):
    goal_a: GoalSpec
    goal_b: GoalSpec
    same_day: bool = True
    back_to_back: bool = True
    max_gap_minutes: int = 30
    prefer_same_hospital: bool = True
    goal_ref: str = "J"


@tool("find_joint_slots", JointArgs,
      "Joint search for TWO linked appointments (e.g. patient + family member) satisfying a coupling constraint: "
      "same day, back-to-back (gap ≤ max_gap_minutes), preferably the same hospital. Returns ranked slot pairs.")
def find_joint_slots(c: RunContext, goal_a: dict, goal_b: dict, same_day=True, back_to_back=True, max_gap_minutes=30,
                     prefer_same_hospital=True, goal_ref="J") -> dict:
    pol = get_policy(c, goal_ref)
    cur = pol.current if pol else {}
    df = cur.get("date_from") or (date.today() + timedelta(days=1)).isoformat()
    dt = cur.get("date_to") or df
    modes = cur.get("modes", ["in_person"])
    exclude = set(c.cache.get(f"exclude_{goal_ref}", []))
    A = _query_slots(c, goal_a["specialty"], None, df, dt, cur.get("time_from"), cur.get("time_to"), cur.get("locality"), modes, goal_a["patient_id"], exclude)
    B = _query_slots(c, goal_b["specialty"], None, df, dt, cur.get("time_from"), cur.get("time_to"), cur.get("locality"), modes, goal_b["patient_id"], exclude)
    pairs = []
    for a in A:
        for b in B:
            if same_day and a["date"] != b["date"]:
                continue
            if a["mode"] != b["mode"]:
                continue
            if goal_a["patient_id"] == goal_b["patient_id"] and not (
                    hm_to_min(a["end"]) <= hm_to_min(b["start"]) or hm_to_min(b["end"]) <= hm_to_min(a["start"])):
                continue  # one person cannot be in two consultations at once
            if back_to_back:
                if a["date"] != b["date"]:
                    continue
                gap1 = hm_to_min(b["start"]) - hm_to_min(a["end"])
                gap2 = hm_to_min(a["start"]) - hm_to_min(b["end"])
                if not (0 <= gap1 <= max_gap_minutes or 0 <= gap2 <= max_gap_minutes):
                    continue
            same_h = a["hospital_id"] == b["hospital_id"]
            gap = abs(hm_to_min(a["start"]) - hm_to_min(b["start"])) if a["date"] == b["date"] else 600
            score = (5 if (same_h and prefer_same_hospital) else 0) - (datetime.fromisoformat(a["date"]) - datetime.fromisoformat(df)).days - gap / 240 \
                + (0.3 * (a["rating"] + b["rating"]) - 2.5) - 0.01 * hm_to_min(min(a["start"], b["start"])) / 60
            pairs.append({"a": a, "b": b, "same_hospital": same_h, "score": round(score, 3)})
    pairs.sort(key=lambda p: -p["score"])
    top = pairs[:5]
    sh = sum(1 for p in pairs if p["same_hospital"])
    return {"ok": True, "pairs": top, "count": len(pairs), "same_hospital_pairs": sh,
            "summary": f"{len(pairs)} valid pair(s) ({sh} at the same hospital) between {df} and {dt}"
            + (f"; best: {top[0]['a']['hospital_name']} {top[0]['a']['date']} {top[0]['a']['start']}+{top[0]['b']['start']}" if top else "")}
