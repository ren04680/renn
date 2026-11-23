"""Triage tools: hard-rule emergency screen + the trained ML classifier."""
from __future__ import annotations

from pydantic import BaseModel

from backend.core import guardrails
from backend.core.context import RunContext
from backend.ml import triage_model
from backend.tools.registry import tool


class TextArgs(BaseModel):
    text: str


@tool("emergency_screen", TextArgs, "HARD RULE: detect emergency language (EN + Hinglish). Always runs first; cannot be overridden.")
def emergency_screen(c: RunContext, text: str) -> dict:
    r = guardrails.emergency_screen(text)
    return {"ok": True, **r, "summary": ("EMERGENCY: " + ", ".join(m["match"] for m in r["matches"])) if r["emergency"] else "no emergency language"}


@tool("classify_symptoms", TextArgs, "Trained TF-IDF + Logistic Regression model: symptoms → specialty + urgency, with confidences and evidence n-grams.")
def classify_symptoms(c: RunContext, text: str) -> dict:
    r = triage_model.classify(text)
    return {"ok": True, **r,
            "summary": f"{r['specialty']} ({r['specialty_conf']:.0%}), urgency {r['urgency']} ({r['urgency_conf']:.0%}); evidence: {', '.join(r['evidence'][:3])}"}
