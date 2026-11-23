"""Unscripted 'jury improvisation' inputs: the system must stay honest and sensible, never crash."""
import time

import pytest

from backend.core.runner import resume_run, start_run
from backend.core.trace import bus


def run(text, pid="GUEST", answer=None):
    r = start_run(text, pid)
    n = 0
    while r["status"] == "waiting" and n < 4:
        n += 1
        if r["interrupt"]["kind"] == "clarification":
            r = resume_run(r["run_id"], {"text": answer or "knee pain tomorrow"})
        else:
            r = resume_run(r["run_id"], {"approved": True})
    return r


@pytest.mark.parametrize("text,what", [("I need a dentist", "dentistry"), ("eye problem since 2 days", "eye care"),
                                       ("I feel depressed and anxious", "mental health")])
def test_unsupported_specialty_is_honest(fresh, text, what):
    r = run(text)
    assert r["response"]["kind"] == "text" and what in r["response"]["text"]
    assert not [e for e in bus.for_run(r["run_id"]) if e["type"] == "tool_call" and e["agent"] == "scheduling"]


def test_named_doctor_is_pinned(fresh):
    r = run("book Dr. Mehra tomorrow", "P001")
    a = r["response"]["outcome"]["appointments"][0]
    assert a["doctor_id"] == "D11"


def test_unregistered_child_booked_under_parent_with_disclosure(fresh):
    r = run("my child has fever")
    o = r["response"]["outcome"]
    assert r["response"]["kind"] == "booked" and o["appointments"][0]["specialty"] == "pediatrics"
    assert any("not registered" in d for d in o["disclosures"])


def test_negated_symptom_not_emergency(fresh):
    r = run("no chest pain, just a rash")
    assert r["response"]["kind"] == "booked"
    assert r["response"]["outcome"]["appointments"][0]["specialty"] == "dermatology"


def test_cancel_is_honest(fresh):
    r = run("cancel my appointment", "P001")
    assert r["response"]["kind"] == "text" and "front-desk" in r["response"]["text"]


def test_specialty_price_question(fresh):
    r = run("How much does a cardiologist cost?", "P001")
    assert r["response"]["kind"] == "billing" and "Cardiology" in r["response"]["text"] and "CarePlus Gold" in r["response"]["text"]


def test_same_patient_two_specialties_never_overlap(fresh):
    r = run("Book a cardiologist and a dermatologist for me on the same day", "P001")
    apps = r["response"]["outcome"]["appointments"]
    assert len(apps) == 2
    a, b = sorted(apps, key=lambda x: x["start"])
    assert a["date"] == b["date"] and a["end"] <= b["start"]


def test_llm_outage_trips_breaker_fast(fresh, monkeypatch):
    import backend.config as config
    from backend.config import settings
    from backend.core import llm

    class Down:
        def invoke(self, *_a, **_k):
            raise ConnectionError("DeepSeek unreachable")

        def bind_tools(self, _t):
            return self

    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "k")
    settings.update(offline=False)
    llm.set_model_override(Down())
    try:
        t0 = time.time()
        r = run("I need a dermatologist in Baner tomorrow morning")
        assert r["response"]["kind"] == "booked" and time.time() - t0 < 5
        assert r["stats"]["llm_calls"] == 1  # first failure opens the breaker; later steps skip the LLM instantly
    finally:
        llm.set_model_override(None)
        settings.update(offline=True)
