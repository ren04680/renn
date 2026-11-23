"""Billing agent: fees + insurance from data only. Adds cost to proposals; answers billing questions."""
from __future__ import annotations

from backend.core.context import RunContext
from backend.core.fallback_parser import SPECIALTY_LABEL
from backend.tools.common import date_label
from backend.tools.registry import call_tool

AGENT = "billing"


def cost_proposal(c: RunContext, proposal: dict) -> dict:
    total = 0
    for it in proposal["items"]:
        e = call_tool(c, AGENT, "estimate_cost", {"patient_id": it["patient_id"], "doctor_id": it["doctor_id"], "mode": it["mode"]},
                      reason="every proposal must show the real fee and the insurance share before approval")
        if e.get("ok"):
            it["cost"] = e["estimate"]
            total += e["estimate"]["patient_pays"]
    proposal["total_patient_pays"] = total
    proposal["stage"] = "costed"
    c.trace.thought(AGENT, "Cost added: " + "; ".join(
        f"{it['patient_name']}: fee ₹{it['cost']['fee']}, {it['cost']['plan_name']} {it['cost']['coverage_pct']}% ({it['cost']['basis']}) → pays ₹{it['cost']['patient_pays']}"
        for it in proposal["items"] if it.get("cost")))
    return proposal


def answer_question(c: RunContext, patient_id: str) -> dict:
    t = c.trace
    ap = call_tool(c, AGENT, "get_patient_appointments", {"patient_id": patient_id},
                   reason="the question is about cost — find what the patient is actually booked for")
    lines, rows = [], []
    for a in ap.get("appointments", [])[:3]:
        e = call_tool(c, AGENT, "estimate_cost", {"patient_id": patient_id, "doctor_id": a["doctor_id"], "mode": a["mode"]},
                      reason=f"estimate out-of-pocket for appointment {a['appointment_id']}")
        if e.get("ok"):
            est = e["estimate"]
            rows.append({**a, "cost": est})
            lines.append(f"• **{a['doctor_name']}** ({SPECIALTY_LABEL.get(a['specialty'], a['specialty'])}, {a['hospital_name']}) "
                         f"on {date_label(a['date'])} {a['start']}: fee ₹{est['fee']}. Your plan **{est['plan_name']}** covers "
                         f"{est['coverage_pct']}% here ({est['basis']}) → insurer ₹{est['insurer_pays']}"
                         + (f", copay ₹{est['copay']}" if est['copay'] else "") + f", **you pay ₹{est['patient_pays']}**.")
    if not rows:
        spec = (c.cache.get("goals", {}).get("G1") or {}).get("specialty")
        if spec:
            info = call_tool(c, AGENT, "get_fee", {"doctor_id": _any_doctor(spec)}, reason="no booking yet — show a typical fee")
            lines.append(f"You have no upcoming appointment. A typical {SPECIALTY_LABEL[spec]} consultation costs about ₹{info.get('fee')}.")
        else:
            lines.append("You have no upcoming appointments, so there is nothing to estimate yet. Tell me which specialist "
                         "you need and I'll include the exact cost and insurance share in the proposal.")
    text = "Here is what your appointments will cost, using your insurance on file:\n" + "\n".join(lines) if rows else "\n".join(lines)
    t.thought(AGENT, f"Answered billing question from data ({len(rows)} appointment(s) estimated).")
    res = {"answer": text, "estimates": rows}
    c.bb.write(AGENT, "facts", {"billing_answer": res}, msg=f"billing answer: {len(rows)} estimate(s)")
    return res


def _any_doctor(spec: str) -> str:
    from backend.db.models import Doctor
    from backend.db.session import get_session

    with get_session() as s:
        return s.query(Doctor).filter(Doctor.specialty == spec).order_by(Doctor.fee).first().id
