"""Critic verification + hard-rule guardrails."""
import copy
from datetime import date, timedelta

import pytest

from backend import tools  # noqa: F401
from backend.agents import critic
from backend.core.guardrails import emergency_screen
from backend.db.models import Doctor, Slot
from backend.db.session import get_session
from backend.tools.common import slot_view
from backend.tools.policy import RelaxationPolicy

D1 = (date.today() + timedelta(days=1)).isoformat()


def _proposal(c, spec="dermatology", relax=False):
    with get_session() as s:
        sl, d = (s.query(Slot, Doctor).join(Doctor, Doctor.id == Slot.doctor_id)
                 .filter(Doctor.specialty == spec, Slot.status == "free", Slot.date == D1, Slot.mode == "in_person").first())
        v = slot_view(s, sl, d)
    c.cache["goals"] = {"G1": {"patient_id": "P001", "specialty": spec}}
    pol = RelaxationPolicy("G1", {"specialty": spec, "patient_id": "P001", "date_from": D1, "date_to": D1, "time_from": None,
                                  "time_to": None, "locality": None, "modes": ["in_person"]})
    if relax:
        pol.apply("allow_tele")
    c.policies["G1"] = pol
    item = {"goal_ref": "G1", "patient_id": "P001", "patient_name": "A", **{k: v[k] for k in (
        "slot_id", "doctor_id", "doctor_name", "specialty", "hospital_id", "hospital_name", "locality", "date", "start", "end", "mode", "fee", "rating")}}
    return {"proposal_id": "PR-T", "goal_ref": "G1", "kind": "single", "items": [item], "disclosures": [], "relaxations": pol.applied}


def test_critic_approves_valid(fresh, ctx_factory):
    c = ctx_factory()
    assert critic.review(c, _proposal(c))["verdict"] == "APPROVE"


def test_critic_catches_fabricated_id(fresh, ctx_factory):
    c = ctx_factory()
    p = _proposal(c)
    p["items"][0]["slot_id"] = "S99999"
    v = critic.review(c, p)
    assert v["verdict"] == "REVISE" and any("does not exist" in r for r in v["reasons"])


def test_critic_catches_wrong_fee_and_specialty(fresh, ctx_factory):
    c = ctx_factory()
    p = _proposal(c)
    p["items"][0]["fee"] = 1
    c.cache["goals"]["G1"]["specialty"] = "cardiology"
    v = critic.review(c, p)
    assert v["verdict"] == "REVISE"
    assert any("fee" in r for r in v["reasons"]) and any("cardiology" in r for r in v["reasons"])


def test_critic_catches_taken_slot(fresh, ctx_factory):
    c = ctx_factory()
    p = _proposal(c)
    with get_session() as s:
        s.get(Slot, p["items"][0]["slot_id"]).status = "booked"
    v = critic.review(c, p)
    assert v["verdict"] == "REVISE" and v["reject_slots"] == [p["items"][0]["slot_id"]]


def test_critic_requires_disclosure(fresh, ctx_factory):
    c = ctx_factory()
    p = _proposal(c, relax=True)
    v = critic.review(c, p)
    assert v["verdict"] == "REVISE" and any("not disclosed" in r for r in v["reasons"])
    p2 = copy.deepcopy(p)
    p2["disclosures"] = [r["disclosure"] for r in c.policies["G1"].applied]
    assert critic.review(c, p2)["verdict"] == "APPROVE"


@pytest.mark.parametrize("text", [
    "severe chest pain and sweating", "chest pain spreading to my left arm", "I think it's a heart attack",
    "my father can't breathe", "face drooping and slurred speech", "my baby is having a seizure",
    "heavy bleeding that won't stop", "I want to kill myself", "seene mein bahut tez dard aur pasina",
    "saans nahi aa rahi", "dadi behosh ho gayi", "vomiting blood since morning",
])
def test_emergency_detected(text):
    assert emergency_screen(text)["emergency"]


@pytest.mark.parametrize("text", [
    "I need a dermatologist in Baner tomorrow", "mild chest discomfort when climbing stairs for months",
    "Tuesday evening fits my schedule", "no chest pain, just a skin rash", "seene mein halka dard", "knee pain",
])
def test_no_false_emergency(text):
    assert not emergency_screen(text)["emergency"]


def test_emergency_stops_scheduling(fresh):
    from backend.core.runner import start_run
    from backend.core.trace import bus

    r = start_run("severe chest pain and sweating", "P001")
    assert r["response"]["kind"] == "emergency"
    assert not [e for e in bus.for_run(r["run_id"]) if e["agent"] == "scheduling"]
