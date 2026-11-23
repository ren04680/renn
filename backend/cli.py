"""Command-line interface (same trace style as the original CLI: `[agent] message`).

  python -m backend.cli                       # interactive chat (choose patient with --patient)
  python -m backend.cli --scenario 3          # run one scripted scenario by number (S03)
  python -m backend.cli --event cancel        # fire the demo 'doctor cancels block' event
  python -m backend.cli --reset               # reseed demo data
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from backend.config import PRINCIPLE, settings
from backend.core.trace import bus


def interactive(patient: str) -> None:
    from backend.core.runner import resume_run, start_run

    print(f"\nHospital Agent OS — CLI · patient {patient} · {'OFFLINE' if settings.offline else 'ONLINE'} mode")
    print(f"“{PRINCIPLE}”\nType a request (or 'quit'). Try: 'Book with my usual doctor next week'\n")
    while True:
        try:
            text = input(f"{patient}> ").strip()
        except EOFError:
            break
        if text.lower() in ("quit", "exit", "q"):
            break
        if not text:
            continue
        r = start_run(text, patient)
        while r["status"] == "waiting":
            it = r["interrupt"]
            if it["kind"] == "clarification":
                ans = input(f"\n🤖 {it['question']}\n{patient}> ")
                r = resume_run(r["run_id"], {"text": ans})
            else:
                p = it["proposal"]
                print("\n──────── PROPOSAL (needs your approval) ────────")
                for i in p["items"]:
                    cost = i.get("cost") or {}
                    print(f"  {i['patient_name']}: {i['doctor_name']} ({i['specialty']}) · {i['hospital_name']} · {i['date']} {i['start']} · "
                          f"{i['mode']} · fee ₹{i['fee']} · you pay ₹{cost.get('patient_pays', '?')}")
                for d in p.get("disclosures", []):
                    print(f"  ⚠ {d}")
                yn = input("Approve booking? [y/n] ").strip().lower()
                r = resume_run(r["run_id"], {"approved": yn.startswith("y")})
        print(f"\n🤖 {r['response']['text']}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patient", default="P001")
    ap.add_argument("--scenario", type=int)
    ap.add_argument("--event", choices=["cancel", "freed"])
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="hide blackboard writes")
    a = ap.parse_args()
    bus.echo = True
    if a.quiet:
        bus.echo_types = {"thought", "tool_call", "tool_result", "relaxation", "critic_verdict", "decision", "memory_hit",
                          "approval_request", "notification", "event_trigger", "offer", "error", "fallback"}
    if a.reset:
        from scripts.seed import reset_demo

        reset_demo()
        return
    if a.scenario:
        from scripts.run_scenarios import SCENARIOS, run

        sid = f"S{a.scenario:02d}"
        ok = run({sid}, verbose=True)
        sys.exit(0 if all(r["pass"] for r in ok) else 1)
    if a.event:
        from backend.agents.event_watcher import handle_event_sync, list_offers

        d2 = (date.today() + timedelta(days=2)).isoformat()
        ev = {"type": "doctor_cancel", "doctor_id": "D01", "date": d2, "start": "09:30", "end": "12:00"} if a.event == "cancel" \
            else {"type": "slot_freed", "slot_id": input("slot id to free: ").strip()}
        res = handle_event_sync(ev)
        print("\nOffers:", [(o["offer_id"], o["patient_id"], o["slot"]["start"], o["status"]) for o in list_offers() if o["event_id"] == res["event_id"]])
        return
    interactive(a.patient)


if __name__ == "__main__":
    main()
