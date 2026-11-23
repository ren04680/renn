"""Notification tool — mock SMS/email outbox stored in the DB (shown in the UI's Hospital Ops tab)."""
from __future__ import annotations

import time

from pydantic import BaseModel, Field

from backend.core.context import RunContext
from backend.db.models import Notification, Patient
from backend.db.session import get_session
from backend.tools.registry import tool


class NotifyArgs(BaseModel):
    patient_id: str
    subject: str
    body: str = Field(max_length=1200)
    channel: str = "sms"
    kind: str = "info"


@tool("send_notification", NotifyArgs, "Deliver a message to the patient's outbox (mock SMS/email).")
def send_notification(c: RunContext, patient_id: str, subject: str, body: str, channel: str = "sms", kind: str = "info") -> dict:
    with get_session() as s:
        p = s.get(Patient, patient_id)
        to = (p.phone if channel == "sms" else p.email) if p else "front-desk"
        n = Notification(patient_id=patient_id, channel=channel, to=to, subject=subject, body=body, kind=kind,
                         created_at=time.time(), run_id=c.run_id)
        s.add(n)
        s.flush()
        nid = n.id
    c.trace("notification", "notification", f"{channel.upper()} → {to}: {subject}",
            {"patient_id": patient_id, "channel": channel, "to": to, "subject": subject, "body": body, "kind": kind, "id": nid})
    return {"ok": True, "notification_id": nid, "summary": f"{channel} sent to {to}"}
