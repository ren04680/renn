"""Each tool behaves and enforces its contract."""
from datetime import date, timedelta

from backend import tools  # noqa: F401
from backend.db.models import Slot
from backend.db.session import get_session
from backend.tools.registry import call_tool

D1 = (date.today() + timedelta(days=1)).isoformat()


def a_free_slot(spec="dermatology"):
    from backend.db.models import Doctor

    with get_session() as s:
        sl = (s.query(Slot).join(Doctor, Doctor.id == Slot.doctor_id)
              .filter(Doctor.specialty == spec, Slot.status == "free", Slot.date == D1).first())
        return sl.id


def test_search_doctors(fresh, ctx_factory):
    c = ctx_factory()
    r = call_tool(c, "scheduling", "search_doctors", {"specialty": "cardiology"})
    assert r["ok"] and r["count"] == 5
    r = call_tool(c, "scheduling", "search_doctors", {"specialty": "ent", "locality": "Hadapsar"})
    assert [d["doctor_id"] for d in r["doctors"]] == ["D21"]


def test_permissions(fresh, ctx_factory):
    c = ctx_factory()
    r = call_tool(c, "billing", "book_slot", {"slot_id": "S00001", "patient_id": "P001"})
    assert not r["ok"] and "Permission denied" in r["error"]


def test_tool_budget(fresh, ctx_factory):
    c = ctx_factory()
    for _ in range(15):
        assert call_tool(c, "scheduling", "search_doctors", {"specialty": "ent"})["ok"]
    r = call_tool(c, "scheduling", "search_doctors", {"specialty": "ent"})
    assert not r["ok"] and "budget" in r["error"]


def test_hold_and_gated_booking(fresh, ctx_factory):
    c = ctx_factory()
    sid = a_free_slot()
    assert call_tool(c, "scheduling", "hold_slot", {"slot_id": sid, "patient_id": "P001"})["ok"]
    other = ctx_factory()
    assert not call_tool(other, "scheduling", "hold_slot", {"slot_id": sid, "patient_id": "P002"})["ok"]
    r = call_tool(c, "scheduling", "book_slot", {"slot_id": sid, "patient_id": "P001", "proposal_id": "PX"})
    assert r.get("blocked") and not r["ok"]  # no human approval token → blocked
    r = call_tool(c, "scheduling", "book_slot", {"slot_id": sid, "patient_id": "P001", "proposal_id": "PX", "approval_token": "forged"})
    assert r.get("blocked")
    tok = c.issue_approval("PX")
    r = call_tool(c, "scheduling", "book_slot", {"slot_id": sid, "patient_id": "P001", "proposal_id": "PX", "approval_token": tok})
    assert r["ok"] and r["appointment"]["slot_id"] == sid


def test_estimate_cost(fresh, ctx_factory):
    c = ctx_factory()
    r = call_tool(c, "billing", "estimate_cost", {"patient_id": "P001", "doctor_id": "D01"})
    e = r["estimate"]
    assert e["fee"] == 1000 and e["coverage_pct"] == 80 and e["patient_pays"] == 200
    r = call_tool(c, "billing", "estimate_cost", {"patient_id": "GUEST", "doctor_id": "D01"})
    assert r["estimate"]["patient_pays"] == 1000


def test_memory_recall_and_save(fresh, ctx_factory):
    c = ctx_factory()
    r = call_tool(c, "memory", "recall_memory", {"patient_id": "P001", "query": "usual doctor"})
    assert r["ok"] and any("Mehra" in h["text"] for h in r["hits"])
    r = call_tool(c, "memory", "save_memory", {"patient_id": "P001", "text": "Prefers Dr. Test for testing.", "kind": "preference"})
    assert r["ok"]
    r = call_tool(c, "memory", "recall_memory", {"patient_id": "P001", "query": "Dr. Test testing", "k": 1})
    assert "Dr. Test" in r["hits"][0]["text"]
    assert not call_tool(c, "memory", "save_memory", {"patient_id": "GUEST", "text": "x"})["ok"]


def test_waitlist_refused_before_ladder_exhausted(fresh, ctx_factory):
    from backend.tools.policy import RelaxationPolicy

    c = ctx_factory()
    c.policies["G1"] = RelaxationPolicy("G1", {"specialty": "neurology", "date_from": D1, "date_to": D1, "time_from": "09:00",
                                               "time_to": "12:00", "locality": None, "modes": ["in_person"]})
    r = call_tool(c, "scheduling", "add_to_waitlist", {"patient_id": "P001", "specialty": "neurology", "date_from": D1, "date_to": D1})
    assert not r["ok"] and "widen_time" in r["error"]


def test_patient_profile_family(fresh, ctx_factory):
    c = ctx_factory()
    r = call_tool(c, "memory", "get_patient_profile", {"patient_id": "P001"})
    assert {"relation": "mother", "patient_id": "P014", "name": "Sunita Sharma"} in r["family"]
