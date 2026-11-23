"""Billing tools — fees and insurance come only from the database (never estimated by an LLM)."""
from __future__ import annotations

from pydantic import BaseModel

from backend.core.context import RunContext
from backend.db.models import Doctor, Hospital, InsurancePlan, Patient
from backend.db.session import get_session
from backend.tools.registry import tool


class FeeArgs(BaseModel):
    doctor_id: str
    mode: str = "in_person"


@tool("get_fee", FeeArgs, "Consultation fee for a doctor (in-person or tele).")
def get_fee(c: RunContext, doctor_id: str, mode: str = "in_person") -> dict:
    with get_session() as s:
        d = s.get(Doctor, doctor_id)
        if not d:
            return {"ok": False, "error": f"No doctor {doctor_id}"}
        fee = d.tele_fee if mode == "tele" else d.fee
    return {"ok": True, "doctor_id": doctor_id, "mode": mode, "fee": fee, "summary": f"{d.name} {mode} fee ₹{fee}"}


class InsArgs(BaseModel):
    patient_id: str
    hospital_id: str
    mode: str = "in_person"


def _coverage(s, patient_id: str, hospital_id: str, mode: str) -> dict:
    p = s.get(Patient, patient_id)
    plan = s.get(InsurancePlan, p.insurance_plan_id if p else "INS0")
    h = s.get(Hospital, hospital_id)
    in_network = plan.id in (h.network_plans or "").split(",")
    if plan.id == "INS0":
        pct, why = 0, "self-pay"
    elif mode == "tele" and not plan.tele_covered:
        pct, why = 0, "teleconsultation not covered by this plan"
    else:
        pct = plan.coverage_pct if in_network else plan.out_of_network_pct
        why = "in-network" if in_network else "out-of-network"
    return {"plan_id": plan.id, "plan_name": plan.name, "in_network": in_network, "coverage_pct": pct,
            "copay": plan.copay if pct > 0 else 0, "basis": why, "hospital": h.name, "notes": plan.notes}


@tool("check_insurance", InsArgs, "Patient's insurance plan and coverage at a hospital (network status, %, copay).")
def check_insurance(c: RunContext, patient_id: str, hospital_id: str, mode: str = "in_person") -> dict:
    with get_session() as s:
        cov = _coverage(s, patient_id, hospital_id, mode)
    return {"ok": True, **cov, "summary": f"{cov['plan_name']}: {cov['coverage_pct']}% ({cov['basis']}) at {cov['hospital']}"}


class EstArgs(BaseModel):
    patient_id: str
    doctor_id: str
    mode: str = "in_person"


@tool("estimate_cost", EstArgs, "Out-of-pocket estimate = fee − insurer share + copay (from the patient's plan).")
def estimate_cost(c: RunContext, patient_id: str, doctor_id: str, mode: str = "in_person") -> dict:
    with get_session() as s:
        d = s.get(Doctor, doctor_id)
        if not d:
            return {"ok": False, "error": f"No doctor {doctor_id}"}
        fee = d.tele_fee if mode == "tele" else d.fee
        cov = _coverage(s, patient_id, d.hospital_id, mode)
    insurer = round(fee * cov["coverage_pct"] / 100)
    patient_pays = min(fee, fee - insurer + cov["copay"])
    est = {"fee": fee, "insurer_pays": insurer, "patient_pays": patient_pays, **cov, "mode": mode,
           "doctor_id": doctor_id, "doctor_name": d.name}
    return {"ok": True, "estimate": est,
            "summary": f"fee ₹{fee}, insurer ₹{insurer} ({cov['coverage_pct']}% {cov['basis']}), you pay ₹{patient_pays}"}
