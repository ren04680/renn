"""Relaxation policy checker: order, monotonicity, skip logic, limits."""
from datetime import date, timedelta

from backend import tools  # noqa: F401
from backend.tools.policy import LADDER, RelaxationPolicy
from backend.tools.registry import call_tool

D1 = (date.today() + timedelta(days=1)).isoformat()


def cons(**kw):
    base = {"specialty": "neurology", "patient_id": "P001", "doctor_id": None, "date_from": D1, "date_to": D1,
            "time_from": "09:00", "time_to": "12:00", "time_text": "morning", "locality": "Baner", "modes": ["in_person"],
            "in_person_only": False}
    base.update(kw)
    return base


def test_ladder_order_and_monotonic(ctx_factory):
    c = ctx_factory()
    c.policies["G1"] = RelaxationPolicy("G1", cons())
    applied = []
    for step in LADDER:
        r = call_tool(c, "scheduling", "relax_constraint", {"step": step})
        assert r["ok"], r
        applied.append(step)
    cur = c.policies["G1"].current
    assert cur["time_from"] is None and cur["locality"] is None and "tele" in cur["modes"]
    assert cur["date_from"] > D1  # moved forward, never backwards
    assert c.policies["G1"].exhausted
    r = call_tool(c, "scheduling", "relax_constraint", {"step": "next_day"})
    assert not r["ok"] and r.get("exhausted")


def test_skip_ahead_is_rejected_with_allowed_step(ctx_factory):
    c = ctx_factory()
    c.policies["G1"] = RelaxationPolicy("G1", cons())
    r = call_tool(c, "scheduling", "relax_constraint", {"step": "allow_tele"})
    assert not r["ok"]
    assert "widen_time" in r["error"]
    assert c.policies["G1"].applied == []


def test_ineffective_steps_skipped_not_counted(ctx_factory):
    c = ctx_factory()
    c.policies["G1"] = RelaxationPolicy("G1", cons(time_from=None, time_to=None, locality=None))
    pol = c.policies["G1"]
    assert pol.next_allowed(c) == "allow_tele"
    assert pol.skipped == ["widen_time", "widen_area"]
    r = call_tool(c, "scheduling", "relax_constraint", {"step": "allow_tele"})
    assert r["ok"] and r["relaxation"]["n"] == 1  # skipped steps did not count


def test_in_person_only_blocks_tele(ctx_factory):
    c = ctx_factory()
    c.policies["G1"] = RelaxationPolicy("G1", cons(time_from=None, time_to=None, locality=None, in_person_only=True))
    assert c.policies["G1"].next_allowed(c) == "next_day"


def test_pinned_doctor_skips_area(ctx_factory):
    c = ctx_factory()
    c.policies["G1"] = RelaxationPolicy("G1", cons(doctor_id="D11", time_from=None, time_to=None))
    assert c.policies["G1"].next_allowed(c) == "allow_tele"


def test_availability_envelope_enforced(fresh, ctx_factory):
    c = ctx_factory()
    c.policies["G1"] = RelaxationPolicy("G1", cons(specialty="dermatology"))
    r = call_tool(c, "scheduling", "get_availability", {"modes": ["tele"]})
    assert not r["ok"] and "not permitted" in r["error"]
    r = call_tool(c, "scheduling", "get_availability", {"locality": "Kothrud"})
    assert not r["ok"] and "locality" in r["error"]
    r = call_tool(c, "scheduling", "get_availability", {})
    assert r["ok"]
