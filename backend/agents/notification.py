"""Notification agent: the LLM drafts the message (offline: template), the tool delivers it."""
from __future__ import annotations

from backend.core.context import RunContext
from backend.core.fallback_parser import SPECIALTY_LABEL
from backend.core.llm import LLMUnavailable, llm_json, note_fallback
from backend.tools.common import date_label
from backend.tools.registry import call_tool

AGENT = "notification"

SYSTEM = """You draft short, warm, factual SMS messages for a Pune hospital. Use ONLY the facts given
(doctor, hospital, date, time, mode, amount). Never add facts. Max 320 characters. English.
Return JSON: {"subject": "...", "body": "..."}"""


def _template(kind: str, f: dict) -> tuple[str, str]:
    if kind == "booked":
        mode = "Video consultation (link sent 15 min before)" if f["mode"] == "tele" else f"at {f['hospital_name']}, {f['locality']}"
        return ("Appointment confirmed",
                f"Hi {f['patient_name'].split()[0]}, your {SPECIALTY_LABEL.get(f['specialty'], f['specialty'])} appointment with "
                f"{f['doctor_name']} is confirmed for {date_label(f['date'])} at {f['start']} — {mode}. "
                f"Estimated amount payable: ₹{f.get('patient_pays', f['fee'])}. Ref {f['appointment_id']}. Reply C to cancel.")
    if kind == "waitlisted":
        return ("Added to waitlist",
                f"Hi {f['patient_name'].split()[0]}, no {SPECIALTY_LABEL.get(f['specialty'], f['specialty'])} slot was free "
                f"{f['window']}. You are on the waitlist (#{f.get('position') or '-'}); we will hold the first matching slot "
                f"for you and message you to confirm.")
    if kind == "rescheduled":
        return ("Appointment moved",
                f"Hi {f['patient_name'].split()[0]}, your appointment is now with {f['doctor_name']} on {date_label(f['date'])} "
                f"at {f['start']} ({'video' if f['mode'] == 'tele' else f['hospital_name']}). Ref {f['appointment_id']}.")
    return ("Hospital update", f.get("text", ""))


def notify(c: RunContext, kind: str, facts: dict, patient_id: str) -> dict:
    subject, body = _template(kind, facts)
    if not c.offline:
        try:
            out = llm_json(c, AGENT, "draft_notification", SYSTEM, f"Message type: {kind}\nFacts: {facts}\nTemplate (for reference): {body}")
            if out.get("body") and len(out["body"]) <= 400:
                # zero-fabrication guard: the drafted text must still contain the key facts
                must = [facts.get("start", ""), str(facts.get("doctor_name", "")).split()[-1] if facts.get("doctor_name") else ""]
                if all(m in out["body"] for m in must if m):
                    subject, body = out.get("subject") or subject, out["body"]
                else:
                    c.trace.decision(AGENT, "LLM draft dropped a key fact (time/doctor) — using the verified template instead.")
        except LLMUnavailable as e:
            note_fallback(c, AGENT, "draft_notification", e)
    return call_tool(c, AGENT, "send_notification", {"patient_id": patient_id, "subject": subject, "body": body,
                                                     "channel": "sms", "kind": kind},
                     reason="deliver the drafted message to the patient's outbox")
