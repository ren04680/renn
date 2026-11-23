"""Walk through every demo scenario in the real UI and save numbered step-by-step screenshots.

  python -m scripts.capture_screenshots                 # server already running on :8000
  python -m scripts.capture_screenshots --start-server  # starts uvicorn (offline mode) for you
Output: submission/screenshots/NN_name.png
Needs: pip install playwright && python -m playwright install chromium
       (or set PW_CHROMIUM=/path/to/chrome to reuse an existing Chromium)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "submission" / "screenshots"


def _post(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _wait_server(base, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(base + "/api/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _chromium_path():
    if os.getenv("PW_CHROMIUM"):
        return os.getenv("PW_CHROMIUM")
    c = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    return c[-1] if c else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--start-server", action="store_true")
    ap.add_argument("--scale", type=float, default=2.0)
    a = ap.parse_args()
    base = a.base
    proc = None
    if a.start_server:
        env = {**os.environ, "DEMO_OFFLINE": os.getenv("DEMO_OFFLINE", "1")}
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.api.main:app", "--port", base.rsplit(":", 1)[-1]],
                                cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not _wait_server(base):
        sys.exit(f"server not reachable at {base}")
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.png"):
        f.unlink()
    _post(base, "/api/reset")
    _post(base, "/api/settings", {"inject_fault": False})

    from playwright.sync_api import sync_playwright

    n = [0]
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception:
            browser = pw.chromium.launch(executable_path=_chromium_path())
        page = browser.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=a.scale)
        page.goto(base + "/?advanced=1")  # advanced mode shows Inject fault, Blackboard and Metrics for the evidence shots
        page.wait_for_selector("[data-testid=chat-input]")
        page.wait_for_timeout(1200)

        def shot(name):
            n[0] += 1
            page.wait_for_timeout(700)
            page.screenshot(path=str(OUT / f"{n[0]:02d}_{name}.png"))
            print(f"  {n[0]:02d}_{name}.png")

        def patient(pid):
            page.click("[data-testid=tab-patient]")
            page.select_option("[data-testid=patient-select]", pid)
            page.wait_for_timeout(600)

        def counts():
            return (page.locator("[data-testid=approval-card]").count(), page.locator("[data-testid^=assistant-]").count())

        def send(text, expect="approval", answers=(), shot_question=None):
            """Send a message. If the agent asks an intake question, optionally screenshot it, then answer."""
            answers = list(answers)
            bc, bm = counts()
            page.fill("[data-testid=chat-input]", text)
            page.click("[data-testid=send-btn]")
            while True:
                page.wait_for_function(
                    f"document.querySelectorAll('[data-testid=approval-card]').length > {bc} || "
                    f"document.querySelectorAll('[data-testid^=assistant-]').length > {bm}", timeout=30000)
                page.wait_for_timeout(700)
                c, m = counts()
                last = page.locator("[data-testid^=assistant-]").last.get_attribute("data-testid") if m else ""
                if expect == "approval" and c == bc and last == "assistant-clarification":
                    if shot_question:
                        shot(shot_question)
                        shot_question = None
                    bc, bm = counts()
                    page.fill("[data-testid=chat-input]", answers.pop(0) if answers else "earliest, any time, anywhere")
                    page.click("[data-testid=send-btn]")
                    continue
                break

        def approve(yes=True):
            before = page.locator("[data-testid^=assistant-]").count()
            page.locator("[data-testid=approve-btn]" if yes else "[data-testid=reject-btn]").last.click()
            page.wait_for_function(f"document.querySelectorAll('[data-testid^=assistant-]').length > {before}", timeout=30000)
            page.wait_for_timeout(900)

        def reveal(text):
            loc = page.locator("[data-testid=activity-panel]").get_by_text(text, exact=False).last
            loc.scroll_into_view_if_needed()
            page.wait_for_timeout(500)

        print("Screenshots →", OUT)
        patient("P001")
        shot("home_patient_P001")
        # 1) normal booking: agent picks its tools, explains why
        send("I need a dermatologist in Baner tomorrow morning")
        shot("normal_request_tool_choice_and_proposal")
        reveal("search_doctors")
        shot("normal_request_why_each_tool")
        approve()
        shot("normal_request_booked")
        # 2) memory
        send("looking for a bone doctor", answers=["Day after tomorrow"], shot_question="intake_memory_aware_asks_only_the_day")
        shot("intake_answered_usual_doctor_evening_card")
        approve()
        send("Book with my usual doctor next week")
        reveal("memory hit")
        shot("memory_recall_usual_doctor")
        approve()
        shot("memory_booked_usual_doctor_evening")
        # 3) multi-goal family
        send("Book a cardiologist for me and a dermatologist for my mother on the same day, back to back, same hospital if possible",
             answers=["Tomorrow"])
        reveal("Decomposed into")
        shot("multigoal_decomposition")
        page.locator("[data-testid=approval-card]").last.scroll_into_view_if_needed()
        shot("multigoal_combined_proposal_one_approval")
        approve()
        shot("multigoal_booked_both")
        page.click("[data-testid=tab-blackboard]")
        page.wait_for_timeout(1500)
        shot("blackboard_multigoal_subtasks")
        # 4) critic catches injected fault
        patient("GUEST")
        page.click("[data-testid=toggle-fault]")
        page.wait_for_timeout(400)
        send("Pediatrician in Kothrud tomorrow between 10 and 11 am")
        reveal("REVISE")
        shot("critic_catches_injected_fault_REVISE")
        page.locator("[data-testid=approval-card]").last.scroll_into_view_if_needed()
        shot("critic_corrected_proposal_with_disclosure")
        approve()
        page.click("[data-testid=toggle-fault]")
        shot("critic_corrected_booked")
        # 5) proactive: doctor cancels block
        page.click("[data-testid=tab-ops]")
        page.wait_for_timeout(1500)
        shot("ops_before_event")
        page.click("[data-testid=fire-cancel]")
        page.wait_for_timeout(3500)
        shot("ops_after_doctor_cancels_block")
        patient("P001")
        page.wait_for_selector("[data-testid=offer-card]", timeout=15000)
        reveal("Woke up on hospital event")
        shot("proactive_event_watcher_no_prompt")
        page.locator("[data-testid=activity-panel] >> text=Re-homing").last.scroll_into_view_if_needed()
        shot("proactive_memory_based_alternatives")
        page.locator("[data-testid=offer-card]").first.scroll_into_view_if_needed()
        shot("proactive_offer_card_P001")
        before = page.locator("[data-testid^=assistant-]").count()
        page.click("[data-testid=offer-accept]")
        page.wait_for_function(f"document.querySelectorAll('[data-testid^=assistant-]').length > {before}", timeout=30000)
        shot("proactive_offer_confirmed")
        patient("P023")
        page.wait_for_selector("[data-testid=offer-card]", timeout=15000)
        shot("proactive_offer_P023_teleconsult_preference")
        # slot freed → waitlist
        page.click("[data-testid=tab-ops]")
        page.wait_for_timeout(1200)
        page.click("[data-testid=fire-freed]")
        page.wait_for_timeout(3000)
        shot("ops_slot_freed_waitlist")
        patient("P031")
        page.wait_for_selector("[data-testid=offer-card]", timeout=15000)
        shot("waitlist_offer_P031")
        before = page.locator("[data-testid^=assistant-]").count()
        page.click("[data-testid=offer-accept]")
        page.wait_for_function(f"document.querySelectorAll('[data-testid^=assistant-]').length > {before}", timeout=30000)
        shot("waitlist_offer_confirmed")
        # 6) emergency
        patient("GUEST")
        send("severe chest pain and sweating", expect="msg")
        shot("emergency_escalation")
        # clarification loop
        send("looking for a bone doctor", answers=["Tomorrow morning, Kothrud"], shot_question="intake_guest_asks_day_time_area")
        shot("intake_guest_answered_proposal")
        approve()
        send("I want to see a doctor", expect="msg")
        shot("clarification_question")
        send("I have knee pain, day after tomorrow evening", answers=["anywhere"])
        shot("clarification_answered_proposal")
        approve()
        # relaxation disclosure
        send("ENT specialist in Hadapsar tomorrow", answers=["Earliest, any time"])
        page.locator("[data-testid=approval-card]").last.scroll_into_view_if_needed()
        shot("relaxation_widen_area_disclosed")
        approve()
        send("I need a gastroenterologist tomorrow")
        page.locator("[data-testid=approval-card]").last.scroll_into_view_if_needed()
        shot("relaxation_teleconsult_disclosed")
        approve()
        # Hinglish
        send("mere ghutne mein dard hai, Kothrud mein dikhana hai", answers=["kal subah"])
        reveal("classify_symptoms")
        shot("hinglish_triage_classifier")
        approve()
        # waitlist
        page.click("[data-testid=tab-patient]")
        page.click("[data-testid=new-patient]")
        page.wait_for_selector("[data-testid=register-modal]")
        page.fill("[data-testid=reg-name]", "Priya Deshmukh")
        page.fill("[data-testid=reg-age]", "41")
        page.select_option("[data-testid=reg-locality]", "Shivajinagar")
        page.select_option("[data-testid=reg-plan]", "INS1")
        page.select_option("[data-testid=reg-time]", "morning")
        shot("register_new_patient_form")
        page.click("[data-testid=reg-submit]")
        page.wait_for_timeout(1200)
        shot("registered_patient_welcome")
        send("Neurologist in Shivajinagar tomorrow morning", expect="msg")
        shot("waitlisted_after_full_ladder")
        # billing
        patient("P001")
        send("How much will it cost with my insurance?", expect="msg")
        shot("billing_answer_from_data")
        # ops + blackboard + metrics
        page.click("[data-testid=tab-ops]")
        page.wait_for_timeout(1500)
        shot("ops_final_state_outbox")
        page.click("[data-testid=tab-blackboard]")
        page.wait_for_timeout(1500)
        shot("blackboard_audit_trail")
        page.click("[data-testid=tab-metrics]")
        page.wait_for_timeout(1500)
        shot("metrics_scenarios_and_classifier")
        page.evaluate("document.querySelector('[data-testid=metrics]').scrollTo(0, 10000)")
        shot("metrics_confusion_matrix")
        browser.close()
    if proc:
        proc.terminate()
    print(f"saved {n[0]} screenshots")


if __name__ == "__main__":
    main()
