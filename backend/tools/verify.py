"""Critic / Verifier tools. Deterministic by design: verification must not hallucinate."""
from __future__ import annotations

from pydantic import BaseModel

from backend.core.context import RunContext
from backend.db.models import Doctor, Hospital, Slot
from backend.db.session import get_session
from backend.tools.common import hm_to_min, patient_busy, slot_available_for
from backend.tools.policy import get_policy
from backend.tools.registry import tool


class ProposalArgs(BaseModel):
    proposal: dict


@tool("verify_ids_exist", ProposalArgs, "Check every id/value shown to the patient (slot, doctor, hospital, date, time, mode, fee) against the database.")
def verify_ids_exist(c: RunContext, proposal: dict) -> dict:
    problems = []
    with get_session() as s:
        for it in proposal.get("items", []):
            sl = s.get(Slot, it.get("slot_id"))
            if sl is None:
                problems.append(f"slot {it.get('slot_id')} does not exist (fabricated id)")
                continue
            d = s.get(Doctor, it.get("doctor_id"))
            if d is None:
                problems.append(f"doctor {it.get('doctor_id')} does not exist")
                continue
            if sl.doctor_id != d.id:
                problems.append(f"slot {sl.id} belongs to {sl.doctor_id}, not {d.id}")
            h = s.get(Hospital, d.hospital_id)
            if it.get("hospital_id") != h.id:
                problems.append(f"hospital mismatch for {d.id}: {it.get('hospital_id')} vs {h.id}")
            if (it.get("date"), it.get("start"), it.get("mode")) != (sl.date, sl.start, sl.mode):
                problems.append(f"slot {sl.id} details differ from DB ({sl.date} {sl.start} {sl.mode})")
            fee = d.tele_fee if sl.mode == "tele" else d.fee
            if it.get("fee") != fee:
                problems.append(f"fee shown ₹{it.get('fee')} ≠ DB fee ₹{fee}")
    ok = not problems
    return {"ok": True, "pass": ok, "problems": problems,
            "summary": "all ids/values match the database" if ok else f"{len(problems)} problem(s): " + "; ".join(problems)}


class SlotFreeArgs(BaseModel):
    slot_id: str


@tool("verify_slot_free", SlotFreeArgs, "Check the slot is still free (or held by this run).")
def verify_slot_free(c: RunContext, slot_id: str) -> dict:
    with get_session() as s:
        sl = s.get(Slot, slot_id)
        if sl is None:
            return {"ok": True, "pass": False, "summary": f"{slot_id} does not exist"}
        ok = slot_available_for(sl, c.run_id)
        st = sl.status + (" (held by this run)" if sl.status == "held" and sl.held_by == c.run_id else "")
    return {"ok": True, "pass": ok, "status": st, "summary": f"{slot_id} is {st}" + ("" if ok else " — NOT available")}


@tool("compare_to_original_request", ProposalArgs,
      "Compare the proposal with what the patient asked for (specialty, patient, doctor, date/time window, area, mode, "
      "coupling) given only the relaxations actually applied, and check every relaxation is disclosed.")
def compare_to_original_request(c: RunContext, proposal: dict) -> dict:
    problems: list[str] = []
    goals = c.cache.get("goals", {})
    pol = get_policy(c, proposal.get("goal_ref", "G1"))
    cur = pol.current if pol else {}
    with get_session() as s:
        for it in proposal.get("items", []):
            g = goals.get(it.get("goal_ref"), {})
            if g.get("specialty") and it.get("specialty") != g["specialty"]:
                problems.append(f"{it.get('doctor_name')} is {it.get('specialty')} but the request was {g['specialty']}")
            if g.get("patient_id") and it.get("patient_id") != g["patient_id"]:
                problems.append(f"booked for {it.get('patient_id')} but the request was for {g['patient_id']}")
            if g.get("doctor_id") and it.get("doctor_id") != g["doctor_id"]:
                problems.append(f"patient asked for {g['doctor_id']} but proposal is {it.get('doctor_id')}")
            if cur:
                if not (cur["date_from"] <= it.get("date", "") <= cur["date_to"]):
                    problems.append(f"date {it.get('date')} outside allowed window {cur['date_from']}..{cur['date_to']}")
                if cur.get("time_from") and not (cur["time_from"] <= it.get("start", "") < cur["time_to"]):
                    problems.append(f"time {it.get('start')} outside requested window {cur['time_from']}–{cur['time_to']}")
                if cur.get("locality") and it.get("mode") == "in_person" and it.get("locality") != cur["locality"]:
                    problems.append(f"{it.get('hospital_name')} is in {it.get('locality')}, not {cur['locality']} (area was not widened)")
                if it.get("mode") not in cur.get("modes", ["in_person"]):
                    problems.append(f"mode {it.get('mode')} not allowed (teleconsultation was not unlocked)")
            if (it.get("date"), it.get("start")) in patient_busy(s, it.get("patient_id")):
                problems.append(f"{it.get('patient_id')} already has an appointment at {it.get('date')} {it.get('start')}")
    disclosed = " ".join(proposal.get("disclosures", []))
    for r in (pol.applied if pol else []):
        if r["disclosure"] not in disclosed:
            problems.append(f"relaxation '{r['step']}' was applied but not disclosed to the patient")
    cp = proposal.get("coupling")
    items = proposal.get("items", [])
    if cp and len(items) == 2:
        a, b = items
        if cp.get("same_day") and a["date"] != b["date"]:
            problems.append("coupling violated: not on the same day")
        if cp.get("back_to_back"):
            g1 = hm_to_min(b["start"]) - hm_to_min(a["end"])
            g2 = hm_to_min(a["start"]) - hm_to_min(b["end"])
            if not (0 <= g1 <= 30 or 0 <= g2 <= 30):
                problems.append("coupling violated: appointments are not back-to-back")
    ok = not problems
    return {"ok": True, "pass": ok, "problems": problems,
            "summary": "matches the request (after disclosed relaxations)" if ok else f"{len(problems)} mismatch(es): " + "; ".join(problems)}
