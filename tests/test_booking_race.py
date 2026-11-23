"""Booking race condition: atomic conditional UPDATE → exactly one winner; loser re-plans."""
import threading
from datetime import date, timedelta

from backend import tools  # noqa: F401
from backend.db.models import Appointment, Doctor, Slot
from backend.db.session import get_session
from backend.tools.registry import call_tool

D1 = (date.today() + timedelta(days=1)).isoformat()


def test_concurrent_booking_one_winner(fresh, ctx_factory):
    with get_session() as s:
        sid = (s.query(Slot).join(Doctor, Doctor.id == Slot.doctor_id)
               .filter(Slot.status == "free", Slot.date == D1).first().id)
    ctxs = [ctx_factory(f"P{i + 40:03d}") for i in range(8)]
    toks = [c.issue_approval("PX") for c in ctxs]
    results = []

    def go(c, tok):
        results.append(call_tool(c, "scheduling", "book_slot", {"slot_id": sid, "patient_id": c.patient_id,
                                                                "proposal_id": "PX", "approval_token": tok}))

    th = [threading.Thread(target=go, args=(c, t)) for c, t in zip(ctxs, toks)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    wins = [r for r in results if r["ok"]]
    races = [r for r in results if r.get("race")]
    assert len(wins) == 1 and len(races) == 7
    with get_session() as s:
        assert s.query(Appointment).filter(Appointment.slot_id == sid, Appointment.status == "booked").count() == 1


def test_race_triggers_replan_end_to_end(fresh):
    from scripts.run_scenarios import s16

    r, ids, checks = s16()
    assert all(ok for _, ok in checks), checks


def test_joint_booking_all_or_nothing(fresh, ctx_factory):
    c = ctx_factory()
    with get_session() as s:
        a, b = [x.id for x in s.query(Slot).filter(Slot.status == "free", Slot.date == D1).limit(2).all()]
        s.get(Slot, b).status = "booked"  # second half already gone
    tok = c.issue_approval("PJ")
    r = call_tool(c, "scheduling", "book_joint", {"bookings": [{"slot_id": a, "patient_id": "P001"}, {"slot_id": b, "patient_id": "P014"}],
                                                  "proposal_id": "PJ", "approval_token": tok})
    assert not r["ok"] and r["race"]
    with get_session() as s:
        assert s.get(Slot, a).status == "free"  # rolled back
