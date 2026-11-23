# DEMO_SCRIPT.md — 6–7 minute live jury demo

**Before the jury (2 min):**
1. `.\run.bat` (Windows) or `./run.sh` → open **http://localhost:8000** in Chrome (zoom 90% on a laptop screen).
2. Click **Reset demo** (top right). It reseeds every fixture relative to today; patients you registered are kept.
3. The screen is deliberately clean: **Patient** and **Hospital Ops** only. Press **Ctrl + Shift + A** (or open `http://localhost:8000/?advanced=1`) to reveal the advanced controls: **Inject fault**, **Online/Offline**, and the **Blackboard** and **Metrics** tabs. Press it again to hide them. You need them for steps 3, 4 and 7.
4. Offline mode is the default (no key, or `DEMO_OFFLINE=1`). With a DeepSeek key in `.env` it runs online. If it's slow, press Ctrl+Shift+A and click the Online badge to switch to Offline.

Opening line (15 s):
> "This started as a workflow: fixed tool order, and an LLM that only parsed text. Now it's a multi-agent system. A Supervisor decomposes goals onto a blackboard. Specialists pick their own tools, remember patients, critique their own proposals, and react to hospital events with nobody typing. Our rule is: *free to think, gated to act — permitted to fail, never to invent.*"

---

## 1 · Normal request: the agent chooses its tools (60 s)
Patient: **Guest (walk-in)**. Type or click the chip:
```
ENT specialist in Hadapsar tomorrow
```
- The agent asks **one** question: "What time?". It only asks for what it can't work out itself. Click the quick reply **"Earliest, any time"**.
- Point at **Agent Activity**: "Each agent lights up when it acts. The Supervisor decomposed the request into subtasks; you'll see them later on the Blackboard tab."
- "Scheduling is a ReAct agent. Every tool call carries its own *why*: `search_doctors`, then `get_availability`. It found nothing in Hadapsar."
- "It wants to relax, but relaxation goes through a **policy checker**. `widen_time` is **skipped, not counted**, because the time is open. The next allowed step is `widen_area`."
- Approval card: "Fee and insurance come from the Billing agent, and the **'What I changed'** box discloses the relaxation. The Critic has already verified it. Nothing is written until I click." → **Approve & book**.

## 2 · Memory: it asks only what it doesn't know (60 s)
Switch patient to **P001 · Aarav Sharma**:
```
looking for a bone doctor
```
- "A guest would get three questions (day, time, area). Aarav gets **one**: *which day*. The agent says: *'From what I remember, I'll use your usual evening slots, hospitals near Kothrud, and your usual doctor Dr. Arjun Mehra if free.'* That's **vector memory plus visit history**. It never asks again for what it already knows."
- Click **"Day after tomorrow"**. Card: **Dr. Arjun Mehra, evening, Kothrud**, with *"Why this slot: usual doctor · evening · near home."* → **Approve**.
- (Optional, 15 s) `Book with my usual doctor next week` → no questions at all, straight to Dr. Mehra next week, evening.

## 2b · Register a juror as a new patient (optional, 45 s)
Click **New patient** in the top bar. Ask a juror for their name, age and area, pick an insurance plan and a preferred time, then click **Register & switch to patient**.
- "They're now saved as **P101** in the hospital database, and their preferences became long-term memories."
- Type `I need a skin doctor` → the agent asks only the day and says it will use their preferred time and area. Click a quick reply → card → Approve.
- Patients you register are kept when you press Reset demo. The 100 seeded patients stay in the dataset, but only the demo cast is listed.

## 3 · Multi-goal family booking (60 s)
Still P001:
```
Book a cardiologist for me and a dermatologist for my mother on the same day, back to back, same hospital if possible
```
- It asks **"Which day?"**. Both people's time and area preferences are already in memory. Click **"Tomorrow"**.
- "The Supervisor splits this into **two linked goals with a coupling constraint**: same day, back to back, same hospital as a soft preference. Memory resolves 'my mother' to **P014 Sunita** through family links."
- "Scheduling does **one joint search** (`find_joint_slots`) instead of two independent ones, and the result is **one combined proposal with one approval**. Each person's own insurance is applied."
- → **Approve**. Then press **Ctrl + Shift + A** and open the **Blackboard** tab for 10 s: "goal, subtasks with owners and dependencies, facts, critic verdicts, and the write log that is our audit trail in SQLite."

## 4 · Reflection: the Critic catches an injected fault (45 s)
Back on the **Patient** tab, switch to **Guest**, then turn **Inject fault ON** (top bar, visible in advanced mode; it turns yellow):
```
Pediatrician in Kothrud tomorrow between 10 and 11 am
```
- In Activity, scroll to the red **REVISE**: "In debug mode the Scheduling agent's first proposal is deliberately wrong: a booked cardiology slot in Hadapsar. The Critic checks it against the database and catches **3 problems**: the slot is taken, it's the wrong specialty, and it's the wrong area."
- "The Supervisor re-dispatches Scheduling with that feedback, and the corrected proposal passes. That's a maximum of 2 loops, then it fails honestly."
- Corrected card: "10–11 was full, so it **widened the time and disclosed it**." → **Approve**, then turn **Inject fault OFF**.

## 5 · Proactive and event-driven: the WOW moment (75 s)
Open **Hospital Ops**. The defaults are already set: **D01 · Dr. Anil Kulkarni**, the day after tomorrow, **09:30–12:00**.
- "Nobody is typing anything now. The hospital tells us a doctor cancelled a morning block." → **Fire "doctor cancels block"**.
- The grid turns red and striped, and **Proactive offers** fills in. "The Event Watcher woke up on the event bus, found 4 affected appointments, and re-homed the 3 registered patients **using each one's memory**."
- Switch patient to **P001**. The fuchsia **offer card** appears: "Same doctor, **evening**, because Aarav prefers evenings. The slot is held for 15 minutes and he was notified. The agent did everything **except** the final write." → **Confirm new slot**.
- Optional: switch to **P023**. "Vikram prefers teleconsults, so the agent offered him a **video** slot with his usual cardiologist. Different patients get different choices from the same event."
- Optional (15 s): **Fire "slot freed"** → switch to **P031** → "a freed neurology slot goes to the waitlisted patient first."

## 6 · Emergency (20 s)
Switch to **Guest**:
```
severe chest pain and sweating
```
- "A hard rule runs before every agent, in English and Hinglish. Scheduling never runs, and it tells the patient to call 108. No model can override this."

## 7 · Metrics (30 s)
Open the **Metrics** tab (advanced mode, Ctrl + Shift + A):
- "20 scenarios pass, including the original 7, the intake questions, a booking race, a rejection, Hinglish input and offline mode. 63 pytest tests cover tools, the policy checker, the critic, guardrails, races, unscripted inputs, and the online ReAct loop with a deliberately misbehaving LLM."
- "Triage model: TF-IDF + logistic regression, 97% specialty accuracy on held-out data. We also report **63% on unseen phrasings** on purpose. That honest number is why triage asks the patient when it isn't confident, and why emergencies use a hard rule instead of ML."

Close (10 s):
> "So the agents are free to think: they choose tools, recall, plan and critique. But every action is gated: a policy, a critic, and a human."

---

## Likely viva questions (short answers)

**1. Why isn't this just a workflow?**
In a workflow the developer fixes the tool order. Here the Scheduling agent decides which tool to call next from the observations (ReAct), and the Supervisor decomposes each request into a different subtask graph (a single booking has 9 subtasks, a family request has coupled goals, a billing question has 2). Re-planning happens at run time: critic REVISE, booking race, clarification. And the Event Watcher acts with no prompt at all. What *is* fixed is the safety envelope.

**2. How do you prevent hallucinated slots?**
Three layers. (a) The ReAct loop only accepts a `slot_id` that a tool returned in that conversation. (b) The proposal shown to the patient is assembled from DB rows, not LLM text. (c) The Critic re-verifies every id, date, time, mode and fee against the DB before the patient sees it. There is a test where the LLM proposes `S99999` and gets rejected.

**3. What stops the LLM from booking on its own?**
`book_slot` is gated: it needs an approval token minted only by the human step (`interrupt()` → Approve). There is a test where the LLM calls `book_slot` directly and gets `BLOCKED`.

**4. Why a blackboard over direct agent-to-agent messaging?**
Decoupling and auditability. Agents don't need to know each other; they read facts and write results. The Supervisor sees the whole state to decide what's next (dependencies, re-plans). Every write is logged with agent and timestamp and persisted, so the run is fully replayable. That is the audit trail a hospital needs. With direct messaging, the shared state is scattered across conversations.

**5. Why TF-IDF + LR for triage instead of an LLM?**
It's fast (ms), works offline, is deterministic, and is explainable: we show the n-grams that drove the decision. It is also measurable, with a confusion matrix and macro-F1. The LLM can still *review* low-confidence cases and override the specialty with a stated reason, but it can never lower urgency. Emergencies use a hard rule, not ML.

**6. How does the relaxation policy work, and why enforce it in a tool?**
The ladder is widen_time → widen_area → allow_tele → next_day, then waitlist. It is monotonic, ineffective steps are skipped without counting, and there are at most 4 steps. It's enforced *inside* `relax_constraint` and `get_availability`, so even an LLM that wants to jump ahead receives an error naming the allowed step (tested). Putting rules in tools means the LLM can't talk its way around them.

**7. What happens if DeepSeek is down during the demo?**
Every LLM step has a timeout. On failure, that step falls back to the offline logic and a `fallback` event is shown in the trace. `DEMO_OFFLINE=1`, or the badge, switches the whole system to the deterministic planner, which uses the same agents, tools and trace. It is tested in `test_llm_failure_falls_back_to_offline`.

**8. How does memory work?**
It's hybrid. There are episodic and preference memories in a vector store (ChromaDB; MiniLM embeddings, or a local hashing embedder offline) plus structured records (visit history, profile, family links). After each run the Memory agent decides what's worth saving, such as the booking episode, a stated preference, or an accepted teleconsult. Those memories drive ranking and proactive alternatives.

**9. How do you handle two people booking the same slot?**
Soft holds with a TTL while the patient decides. The final booking is one atomic conditional UPDATE in a transaction. If someone else won, the tool reports a race, and the Supervisor treats it as a re-plan rather than an error: it finds the next best slot and asks again. A test runs 8 threads booking the same slot, and exactly one wins. Joint family bookings are all-or-nothing.

**10. Why does it ask some questions and not others?**
It's a gap check, not a fixed form. The Supervisor asks only for what is missing *and* can't be inferred: the specialist (if the symptoms are unclear), then the day, time and area in **one** message. Memory fills the rest (usual time, home area, usual doctor), and it tells the patient what it assumed so they can correct it. It asks at most once and never nags: an unhelpful answer means it proceeds with sensible defaults and discloses them.

**11. What are the limitations?**
The online path is only validated with a scripted fake LLM in our build environment (one live check is needed with a key). The offline embedder is lexical. State that is mid-approval lives in memory, so a restart drops pending conversations. The HIS is mock data.
