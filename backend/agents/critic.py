"""Critic / Verifier agent (reflection). Checks every proposal BEFORE the patient sees it.

Deterministic on purpose: verification must not hallucinate. Returns APPROVE or REVISE(reasons).
"""
from __future__ import annotations

from backend.core.context import RunContext
from backend.tools.registry import call_tool

AGENT = "critic"


def review(c: RunContext, proposal: dict) -> dict:
    reasons: list[str] = []
    checks = []
    r1 = call_tool(c, AGENT, "verify_ids_exist", {"proposal": proposal}, reason="zero-fabrication: every id/value must exist in the DB")
    checks.append({"check": "verify_ids_exist", "pass": r1.get("pass"), "detail": r1.get("summary")})
    reasons += r1.get("problems", [])
    bad_slots = []
    for it in proposal["items"]:
        r2 = call_tool(c, AGENT, "verify_slot_free", {"slot_id": it["slot_id"]}, reason="the slot must still be free / held by us")
        checks.append({"check": f"verify_slot_free({it['slot_id']})", "pass": r2.get("pass"), "detail": r2.get("summary")})
        if not r2.get("pass"):
            reasons.append(r2.get("summary"))
            bad_slots.append(it["slot_id"])
    r3 = call_tool(c, AGENT, "compare_to_original_request", {"proposal": proposal},
                   reason="does this answer what the patient actually asked (after disclosed relaxations)?")
    checks.append({"check": "compare_to_original_request", "pass": r3.get("pass"), "detail": r3.get("summary")})
    reasons += r3.get("problems", [])
    if reasons:
        for it in proposal["items"]:
            if any(it["slot_id"] in r or it["doctor_id"] in r or it["doctor_name"] in r for r in reasons):
                bad_slots.append(it["slot_id"])
    verdict = "APPROVE" if not reasons else "REVISE"
    out = {"proposal_id": proposal["proposal_id"], "verdict": verdict, "reasons": reasons, "checks": checks,
           "reject_slots": sorted(set(bad_slots))}
    c.trace(AGENT, "critic_verdict",
            f"{verdict}" + (f" — {'; '.join(reasons)[:260]}" if reasons else " — ids exist, slot free, matches request, relaxations disclosed"),
            out)
    c.bb.write(AGENT, "critic_verdicts", out, msg=f"verdict {verdict} for {proposal['proposal_id']}")
    return out
