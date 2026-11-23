"""Constraint-relaxation policy checker (the original ladder, now enforced as a tool contract).

Ladder (monotonic — constraints only ever get wider, never narrower):
  1) widen_time  2) widen_area  3) allow_tele  4) next_day   → exhausted ⇒ waitlist
Ineffective steps (e.g. widen_time when no time window was given) are skipped automatically and
are NOT counted. If an agent (LLM) tries to skip ahead or repeat a step, `relax_constraint`
returns an error naming the only allowed next step.
"""
from __future__ import annotations

import copy
from datetime import date, timedelta

from pydantic import BaseModel, Field

from backend.config import MAX_RELAXATIONS
from backend.core.context import RunContext
from backend.tools.common import date_label
from backend.tools.registry import tool

LADDER = ["widen_time", "widen_area", "allow_tele", "next_day"]
STEP_LABEL = {
    "widen_time": "widen the time window", "widen_area": "widen the area to all of Pune",
    "allow_tele": "allow teleconsultation", "next_day": "shift to the next day",
}
HORIZON_DAYS = 13


class RelaxationPolicy:
    def __init__(self, goal_ref: str, constraints: dict) -> None:
        self.goal_ref = goal_ref
        self.original = copy.deepcopy(constraints)
        self.current = copy.deepcopy(constraints)
        self.applied: list[dict] = []
        self.skipped: list[str] = []
        self.position = 0  # index into LADDER of the next step to consider

    # ---- effectiveness -------------------------------------------------
    def effective(self, step: str) -> tuple[bool, str]:
        c = self.current
        if step == "widen_time":
            ok = bool(c.get("time_from") or c.get("time_to"))
            return ok, "no time window was requested" if not ok else ""
        if step == "widen_area":
            if c.get("doctor_id"):
                return False, "a specific doctor is pinned (location is fixed)"
            ok = bool(c.get("locality"))
            return ok, "no locality restriction to widen" if not ok else ""
        if step == "allow_tele":
            if c.get("in_person_only"):
                return False, "patient explicitly asked for in-person only"
            ok = "tele" not in c.get("modes", ["in_person"])
            return ok, "teleconsultation already allowed" if not ok else ""
        if step == "next_day":
            last = date.fromisoformat(c["date_to"])
            ok = (last - date.today()).days < HORIZON_DAYS
            return ok, "beyond the 14-day booking horizon" if not ok else ""
        return False, "unknown step"

    def next_allowed(self, c: RunContext | None = None, agent: str = "scheduling") -> str | None:
        while self.position < len(LADDER):
            step = LADDER[self.position]
            ok, why = self.effective(step)
            if ok:
                if len(self.applied) >= MAX_RELAXATIONS:
                    return None
                return step
            if step not in self.skipped:
                self.skipped.append(step)
                if c is not None:
                    c.trace(agent, "relaxation", f"skip '{step}' — ineffective ({why}); not counted",
                            {"step": step, "skipped": True, "why": why, "goal_ref": self.goal_ref})
            self.position += 1
        return None

    def peek_next(self) -> str | None:
        """Same as next_allowed but without side effects (no skip bookkeeping / trace)."""
        pos = self.position
        while pos < len(LADDER):
            ok, _ = self.effective(LADDER[pos])
            if ok:
                return None if len(self.applied) >= MAX_RELAXATIONS else LADDER[pos]
            pos += 1
        return None

    @property
    def exhausted(self) -> bool:
        return self.peek_next() is None

    def apply(self, step: str) -> dict:
        c = self.current
        before = {k: c.get(k) for k in ("time_from", "time_to", "locality", "modes", "date_from", "date_to")}
        if step == "widen_time":
            disclosure = (f"No free slot in your requested time ({c.get('time_text') or (c.get('time_from') + '–' + c.get('time_to'))}), "
                          "so I widened the search to the whole day.")
            c["time_from"] = c["time_to"] = None
        elif step == "widen_area":
            disclosure = f"Nothing suitable in {c['locality']}, so I searched hospitals across all of Pune."
            c["locality"] = None
        elif step == "allow_tele":
            disclosure = "No in-person slot was free, so I included teleconsultation (video) slots."
            c["modes"] = sorted(set(c.get("modes", ["in_person"])) | {"tele"})
        else:  # next_day
            f, t = date.fromisoformat(c["date_from"]), date.fromisoformat(c["date_to"])
            span = (t - f).days
            nf = t + timedelta(days=1)
            nt = min(nf + timedelta(days=span), date.today() + timedelta(days=HORIZON_DAYS))
            disclosure = (f"Nothing on {date_label(c['date_from'])}" + (f"–{date_label(c['date_to'])}" if span else "")
                          + f", so I moved the search to {date_label(nf.isoformat())}" + (f"–{date_label(nt.isoformat())}" if nt != nf else "") + ".")
            c["date_from"], c["date_to"] = nf.isoformat(), nt.isoformat()
        after = {k: c.get(k) for k in before}
        rec = {"step": step, "n": len(self.applied) + 1, "before": before, "after": after, "disclosure": disclosure}
        self.applied.append(rec)
        self.position = LADDER.index(step) + 1
        return rec

    def state(self) -> dict:
        return {"goal_ref": self.goal_ref, "original": self.original, "current": self.current,
                "applied": self.applied, "skipped": self.skipped,
                "next_allowed": self.peek_next(), "exhausted": self.peek_next() is None}


def get_policy(c: RunContext, goal_ref: str = "G1") -> RelaxationPolicy | None:
    return c.policies.get(goal_ref)


class RelaxArgs(BaseModel):
    step: str = Field(description="One of widen_time | widen_area | allow_tele | next_day (must be the next allowed step).")
    goal_ref: str = Field("G1", description="Which goal's constraints to relax (G1, or J for a joint multi-goal search).")


@tool("relax_constraint", RelaxArgs,
      "Relax ONE search constraint following the hospital's ladder (widen_time → widen_area → allow_tele → next_day). "
      "Only the next allowed step is accepted; ineffective steps are skipped automatically. Returns the new constraints.")
def relax_constraint(c: RunContext, step: str, goal_ref: str = "G1") -> dict:
    pol = get_policy(c, goal_ref)
    if pol is None:
        return {"ok": False, "error": f"No constraints registered for goal {goal_ref}."}
    expected = pol.next_allowed(c)
    if expected is None:
        return {"ok": False, "exhausted": True,
                "error": "Relaxation ladder exhausted (max 4 relaxations). Do not invent a slot: add the patient to the waitlist."}
    if step != expected:
        c.trace("scheduling", "relaxation", f"POLICY REJECTED '{step}' — next allowed step is '{expected}'",
                {"step": step, "rejected": True, "expected": expected, "goal_ref": goal_ref})
        return {"ok": False, "error": f"Policy violation: '{step}' is not allowed now. Ladder order is "
                f"{' → '.join(LADDER)}; the next allowed step is '{expected}' ({STEP_LABEL[expected]})."}
    rec = pol.apply(step)
    c.trace("scheduling", "relaxation", f"relaxation #{rec['n']}: {STEP_LABEL[step]} — {rec['disclosure']}",
            {**rec, "goal_ref": goal_ref})
    c.bb.write("scheduling", "facts", {f"relaxations_{goal_ref}": pol.applied, f"constraints_{goal_ref}": pol.current},
               msg=f"relaxation #{rec['n']} ({step}) recorded for {goal_ref}")
    return {"ok": True, "summary": f"applied {step} (#{rec['n']}); {rec['disclosure']}", "relaxation": rec,
            "constraints": pol.current, "next_allowed": pol.peek_next()}
