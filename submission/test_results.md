# Scenario test results

Generated 2026-11-23 05:36 · mode: offline (DEMO_OFFLINE=1, deterministic planner) · **20/20 passed**

| # | Scenario | Outcome | Pass | Agents involved | Tool calls | Retries | Critic loops | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| S01 | Original: direct booking | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 9 | 0 | 0 | 0.23 |
| S02 | Original: clarification loop | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor, triage | 12 | 0 | 0 | 0.14 |
| S03 | Original: retry — widen time window | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 11 | 1 | 0 | 0.06 |
| S04 | Original: retry — widen area (time step skipped) | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 12 | 1 | 0 | 0.11 |
| S05 | Original: retry — allow teleconsultation | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 11 | 1 | 0 | 0.07 |
| S06 | Original: emergency escalated | emergency | ✅ | guardrail | 0 | 0 | 0 | 0.01 |
| S07 | Original: waitlisted after full ladder | waitlisted | ✅ | guardrail, memory, notification, scheduling, supervisor | 17 | 4 | 0 | 0.08 |
| S08 | Memory: 'my usual doctor next week' | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 13 | 0 | 0 | 0.09 |
| S09 | Reflection: critic catches injected fault | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 20 | 0 | 1 | 0.1 |
| S10 | Multi-goal: family back-to-back booking | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 27 | 0 | 0 | 0.14 |
| S11 | Proactive: doctor cancels block | proactive | ✅ | critic, event_watcher, memory, notification | 24 | 0 | 0 | 0.09 |
| S12 | Proactive: slot freed → waitlist fill | proactive | ✅ | critic, event_watcher, memory, notification | 9 | 0 | 0 | 0.05 |
| S13 | Billing: cost with my insurance | billing | ✅ | billing, guardrail, memory, supervisor | 4 | 0 | 0 | 0.04 |
| S14 | Hinglish symptom input | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor, triage | 12 | 0 | 0 | 0.11 |
| S15 | Offline mode (no LLM) | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor, triage | 15 | 0 | 0 | 0.1 |
| S16 | Booking race → re-plan | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 24 | 0 | 0 | 0.15 |
| S17 | Patient rejects proposal | rejected | ✅ | billing, critic, guardrail, memory, scheduling, supervisor | 14 | 1 | 0 | 0.07 |
| S18 | Hinglish emergency | emergency | ✅ | guardrail | 0 | 0 | 0 | 0.01 |
| S19 | Intake: vague request → asks day, time, area | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 9 | 0 | 0 | 0.08 |
| S20 | Intake: memory-aware — asks only the day | booked | ✅ | billing, critic, guardrail, memory, notification, scheduling, supervisor | 16 | 0 | 0 | 0.12 |

## Checks per scenario

**S01 — Original: direct booking** → `booked`
- ✅ booked
- ✅ dermatology in Baner
- ✅ tomorrow morning
- ✅ no relaxation needed

> Booked! ✅ **Dr. Neha Joshi** (Dermatology) — Tue 24 Nov (tomorrow), 10:00–10:30, at Baner Lifeline Hospital, Baner — you pay ₹650. Ref **AD020FB**. A confirmation SMS has been sent.

**S02 — Original: clarification loop** → `booked`
- ✅ asked a clarification first
- ✅ booked orthopedics
- ✅ day after tomorrow evening

> Booked! ✅ **Dr. Arjun Mehra** (Orthopedics) — Wed 25 Nov (day after tomorrow), 16:00–16:30, at Kothrud Care Hospital, Kothrud — you pay ₹900. Ref **ABB5C36**. A confirmation SMS has been sent.

**S03 — Original: retry — widen time window** → `booked`
- ✅ booked
- ✅ relaxed time window only
- ✅ closest slot to 10–11 (11:00, Kothrud)
- ✅ relaxation disclosed

> Booked! ✅ **Dr. Shreya Apte** (Pediatrics) — Tue 24 Nov (tomorrow), 11:00–11:30, at Kothrud Care Hospital, Kothrud — you pay ₹650. Ref **A623782**.  What I changed from your request: No free slot in your requested time (10:00–11:00), so I widened the search to the whole day. A confirmation SMS has b

**S04 — Original: retry — widen area (time step skipped)** → `booked`
- ✅ booked
- ✅ relaxed area only
- ✅ widen_time skipped (ineffective, not counted)
- ✅ ENT outside Hadapsar, tomorrow

> Booked! ✅ **Dr. Ritu Malhotra** (ENT) — Tue 24 Nov (tomorrow), 10:00–10:30, at Kothrud Care Hospital, Kothrud — you pay ₹600. Ref **A1CDFA1**.  What I changed from your request: Nothing suitable in Hadapsar, so I searched hospitals across all of Pune. A confirmation SMS has been sent.

**S05 — Original: retry — allow teleconsultation** → `booked`
- ✅ booked
- ✅ relaxed to teleconsultation
- ✅ tele slot tomorrow

> Booked! ✅ **Dr. Ramesh Agarwal** (Gastroenterology) — Tue 24 Nov (tomorrow), 11:30–12:00, 🎥 video consultation — you pay ₹840. Ref **A5A3BA5**.  What I changed from your request: No in-person slot was free, so I included teleconsultation (video) slots. A confirmation SMS has been sent.

**S06 — Original: emergency escalated** → `emergency`
- ✅ escalated
- ✅ 108 in message
- ✅ scheduling never ran

> ⚠️ This sounds like a medical emergency. I will not book a routine appointment for this. • Call **108** (ambulance) or **112** now, or go to the nearest Emergency Room immediately. • Nearest 24×7 ERs: Kothrud Care Hospital (Paud Road), Shivajinagar General Hospital (JM Road). • If someone is with yo

**S07 — Original: waitlisted after full ladder** → `waitlisted`
- ✅ waitlisted
- ✅ full ladder tried in order
- ✅ no approval asked (nothing to book)
- ✅ never invented a slot

> I couldn't find any Neurology slot even after relaxing your request step by step (widen time, widen area, allow tele, next day). I won't invent one — you're on the **waitlist** (position #2). The moment a matching slot frees up I'll hold it for you and ask you to confirm.

**S08 — Memory: 'my usual doctor next week'** → `booked`
- ✅ booked
- ✅ memory recalled
- ✅ usual doctor Dr. Arjun Mehra (D11)
- ✅ next week
- ✅ evening slot (remembered preference)

> Booked! ✅ **Dr. Arjun Mehra** (Orthopedics) — Mon 30 Nov, 16:30–17:00, at Kothrud Care Hospital, Kothrud — you pay ₹180. Ref **A50494C**. A confirmation SMS has been sent.

**S09 — Reflection: critic catches injected fault** → `booked`
- ✅ critic said REVISE first
- ✅ then APPROVE
- ✅ booked correct specialty

> Booked! ✅ **Dr. Neha Joshi** (Dermatology) — Tue 24 Nov (tomorrow), 10:00–10:30, at Baner Lifeline Hospital, Baner — you pay ₹130. Ref **A889C2D**. A confirmation SMS has been sent.

**S10 — Multi-goal: family back-to-back booking** → `booked`
- ✅ one approval for both
- ✅ two appointments booked
- ✅ mother resolved to P014 (dermatology)
- ✅ same day + back-to-back
- ✅ same hospital

> Booked! ✅ **Dr. Sunita Rao** (Cardiology) — Tue 24 Nov (tomorrow), 16:00–16:30, at Baner Lifeline Hospital, Baner — you pay ₹200. Ref **A687088**. ✅ **Dr. Neha Joshi** (Dermatology) for Sunita Sharma — Tue 24 Nov (tomorrow), 16:30–17:00, at Baner Lifeline Hospital, Baner — you pay ₹395. Ref **A7C0B8

**S11 — Proactive: doctor cancels block** → `proactive`
- ✅ watcher woke with no user prompt
- ✅ offers for P001, P014, P023
- ✅ P001 offer is an evening slot (memory)
- ✅ P023 offered teleconsult (memory)
- ✅ P001 confirmation → rescheduled

> 3 offers; P001 accepted → accepted

**S12 — Proactive: slot freed → waitlist fill** → `proactive`
- ✅ offered to best-matching waitlisted patient P031
- ✅ patient confirmed → booked

> slot S00776 freed → offered to P031 → accepted

**S13 — Billing: cost with my insurance** → `billing`
- ✅ billing answer
- ✅ uses plan on file (CarePlus Gold)
- ✅ exact amounts from data (₹1000 fee, ₹200 payable)

> Here is what your appointments will cost, using your insurance on file: • **Dr. Anil Kulkarni** (Cardiology, Kothrud Care Hospital) on Wed 25 Nov (day after tomorrow) 10:00: fee ₹1000. Your plan **CarePlus Gold** covers 80% here (in-network) → insurer ₹800, **you pay ₹200**.

**S14 — Hinglish symptom input** → `booked`
- ✅ Hinglish → orthopedics by the ML model
- ✅ booked in Kothrud

> Booked! ✅ **Dr. Arjun Mehra** (Orthopedics) — Tue 24 Nov (tomorrow), 09:30–10:00, at Kothrud Care Hospital, Kothrud — you pay ₹900. Ref **A87D2CF**. A confirmation SMS has been sent.

**S15 — Offline mode (no LLM)** → `booked`
- ✅ booked in forced offline mode
- ✅ zero LLM calls
- ✅ same agent structure (triage+memory+scheduling+critic)

> Booked! ✅ **Dr. Amit Deshmukh** (Dermatology) — Tue 24 Nov (tomorrow), 16:00–16:30, at Kothrud Care Hospital, Kothrud — you pay ₹470. Ref **AC44FC0**. A confirmation SMS has been sent.

**S16 — Booking race → re-plan** → `booked`
- ✅ race detected
- ✅ re-planned and asked approval again
- ✅ booked a different slot (no double booking)

> Booked! ✅ **Dr. Vivek Sathe** (General Medicine) — Tue 24 Nov (tomorrow), 17:30–18:00, at Kothrud Care Hospital, Kothrud — you pay ₹350. Ref **AFE674E**. A confirmation SMS has been sent.

**S17 — Patient rejects proposal** → `rejected`
- ✅ rejected → nothing booked
- ✅ hold released

> Okay — nothing was booked and the held slot has been released. Tell me what you'd like to change (time, area, doctor, mode).

**S18 — Hinglish emergency** → `emergency`
- ✅ Hinglish emergency escalated
- ✅ no scheduling

> ⚠️ This sounds like a medical emergency. I will not book a routine appointment for this. • Call **108** (ambulance) or **112** now, or go to the nearest Emergency Room immediately. • Nearest 24×7 ERs: Kothrud Care Hospital (Paud Road), Shivajinagar General Hospital (JM Road). • If someone is with yo

**S19 — Intake: vague request → asks day, time, area** → `booked`
- ✅ asked day, time and area in one message
- ✅ offered quick replies
- ✅ booked orthopedics tomorrow morning in Kothrud

> Booked! ✅ **Dr. Arjun Mehra** (Orthopedics) — Tue 24 Nov (tomorrow), 09:30–10:00, at Kothrud Care Hospital, Kothrud — you pay ₹900. Ref **AF422A9**. A confirmation SMS has been sent.

**S20 — Intake: memory-aware — asks only the day** → `booked`
- ✅ asked only the day (memory knows time, area, usual doctor)
- ✅ told the patient what it remembered
- ✅ booked usual doctor, evening, day after tomorrow

> Booked! ✅ **Dr. Arjun Mehra** (Orthopedics) — Wed 25 Nov (day after tomorrow), 16:00–16:30, at Kothrud Care Hospital, Kothrud — you pay ₹180. Ref **AB3FFC5**. A confirmation SMS has been sent.
