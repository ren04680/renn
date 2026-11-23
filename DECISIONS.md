# DECISIONS.md — Hospital Agent OS

Every non-obvious choice made while building, with the alternative considered.
Principle used throughout: **"Free to think, gated to act. The agent is permitted to fail — never to invent."**

---

## Phase 0 findings

| Check | Result |
|---|---|
| Repository contents | **Empty.** `ren04680/renn` had no commits, no branches and no files: the original 13-node CLI, its 5 tools and its 7 scenarios were **not in the repo**. |
| Exam 2 modules (Unit 3 memory / Unit 4 blackboard) | **Not present** (nothing in the repo). Built from scratch here. |
| Python | 3.13 (project targets 3.11+). |
| Node | v22, npm 10 (React + Vite UI is possible, so no Streamlit fallback is needed). |
| `DEEPSEEK_API_KEY` | **Not set** (there is no `.env`). |
| Network (build container) | PyPI + npm reachable. **api.deepseek.com and huggingface.co are blocked** in the build container. |

**Consequences / decisions**

1. **D-01: Original code missing → reconstruct its *behaviour*, not its files.** The 13-node design (intake → gap_check → ask_user loop, emergency escalation, search → availability → decide → relax retry loop, confirm (human y/n), book with race handling, waitlist, notify) is reproduced *inside* the new multi-agent system. The 7 original scenarios are re-specified (see `scripts/run_scenarios.py`, S01–S07) and pass. `legacy/README.md` explains this; if you have the original code locally, drop it into `legacy/` and nothing else changes. *Alternative:* re-write a separate copy of the old CLI from the description. Rejected because it would be a guess at code I have never seen, and it would cost time without improving the demo.
2. **D-02: Offline mode is the primary tested path here.** With no key and no access to DeepSeek, every scenario is verified in `DEMO_OFFLINE` mode (deterministic planner, same agent structure, same trace events). The online (DeepSeek) ReAct path is implemented and **tested against a scripted fake tool-calling LLM** (`tests/test_react_loop.py`). It still needs one live check on your machine with a key; see the README.
3. **D-03: Embeddings fallback.** `sentence-transformers/all-MiniLM-L6-v2` cannot be downloaded here (HF is blocked, and torch is ~GBs). Vector memory therefore uses a pluggable embedder: MiniLM when `sentence-transformers` is installed and the model is cached, otherwise a **deterministic hashing embedder** (word n-grams with domain synonym expansion plus char 3–5-grams, L2-normalised, 6,144 dimensions). The active embedder is shown in the UI badge and in the trace. The store is **ChromaDB** (persistent, cosine), with a numpy fallback if chromadb is not importable.
4. **D-04: Folder layout.** The repo root *is* the project (no extra `hospital-agent/` folder), because the repo exists only for this project.

---

## M1 — Data + model

- **D-05: 5 hospitals + 1 clinic across 6 localities.** The spec says "5 hospitals across 6 localities". Loni Kalbhor gets a *community clinic* (pediatrics + general medicine only), so all 6 localities exist as places a patient can be sent. It also keeps a realistic "small locality → widen area" case.
- **D-06: Demo fixtures on top of seeded randomness.** `scripts/seed.py` uses `random.Random(42)`, so every run produces the same data, and all dates are offsets from `date.today()`. Specific slots are then forced so each jury scenario behaves identically on any day (e.g. every neurology slot is full tomorrow and the day after, which forces the waitlist; every in-person gastro slot is full tomorrow, which forces teleconsult). Each fixture is commented in the seed. *Alternative:* pick the scenario inputs dynamically from the random data. Rejected because the demo script must use exact, rehearsable sentences.
- **D-07: Walk-in appointments.** About 85% of booked slots belong to "Walk-in OPD" patients with no registered profile. The other ~15% belong to the 100 registered patients, which gives realistic numbers without every patient having 8 upcoming visits. On a doctor's cancellation, walk-ins are reported as "front desk to call" and only registered patients are re-homed by the agent.
- **D-08: Slots.** 30-minute slots in a morning session (09:30–12:00) and an evening session (16:00–18:30). Each doctor works 8 of the 14 days. For tele-enabled doctors, the last slot of each session is a teleconsult. The seed produces **2,035 slots**, about 40% booked.
- **D-09: Triage dataset.** 2,800 sentences from 8 specialties × 3 urgencies, English + Hinglish. They are built from templates with synonym substitution, typos, fillers and relations. Some deliberately **ambiguous** phrases appear under two specialties (e.g. "dizziness and ringing in ears" is labelled both ENT and neurology) to mimic real label disagreement.
- **D-10: Two metrics, honestly reported.** (a) A standard stratified 80/20 split. (b) An **unseen-phrase group split**, where the test sentences use base phrases never seen in training. The large drop from (a) to (b) is reported on purpose: template-generated data inflates in-distribution scores. This is why the Triage agent may *override* a low-confidence prediction, and why `emergency_screen` is a hard rule, not ML.
- **D-11: Two heads.** Separate LR heads for specialty and urgency (urgency uses `class_weight=balanced`), with shared TF-IDF features (word 1–2 + char_wb 2–5). This is fast, offline and explainable: the top contributing n-grams are shown as "evidence" in the trace.
- **D-12: Embeddings comparison is optional.** `train_triage.py` attempts MiniLM+LR and records "skipped" in `metrics.json` when the model is unavailable, which is the case here.

---

## M2 — Multi-agent core

- **D-13: Hub-and-spoke LangGraph.** One `StateGraph`: `guard → supervisor ⇄ {memory, triage, gap_check, scheduling, billing, critic, approval, book, notification, remember} → finish`. Every specialist returns to the Supervisor, and the Supervisor dispatches the next *ready* subtask from the blackboard (dependency-aware). *Alternative:* nested subgraphs per agent. Rejected because nesting makes interrupts/resume and the live trace harder to follow, and adds nothing for a demo.
- **D-14: What the LLM decides vs. what code decides.** The **LLM (online)** parses and decomposes goals (Supervisor), picks the Scheduling agent's tool sequence (ReAct with bound tools), reviews low-confidence triage, drafts notifications and chooses memories. **Code** builds the subtask DAG from the decomposition, enforces the policy, verifies (Critic) and gates writes. Reason: "free to think, gated to act". Rules the LLM must not break live in the tools, where it cannot talk its way past them.
- **D-15: Critic is deterministic.** Verification (ids exist, slot free, matches request, relaxations disclosed, coupling satisfied) is rule-based, because a verifier that can hallucinate cannot catch hallucinations. *Alternative:* an LLM critic. Rejected; an LLM may only *draft*, never *verify*.
- **D-16: Approval tokens.** `book_slot` / `book_joint` / `reschedule_appointment` require a per-proposal token minted only by the `approval` node after `interrupt()` returns "approved". An LLM that calls these tools gets `BLOCKED` (tested in `test_llm_cannot_book_without_approval`).
- **D-17: Policy in the tools.** `relax_constraint` enforces ladder order, monotonicity, skipping ineffective steps and the max of 4. `get_availability` rejects searches outside the current envelope (dates, time window, locality, modes, pinned doctor). `add_to_waitlist` is refused until the ladder is exhausted, so the agent cannot give up early.
- **D-18: Ineffective-step semantics.** `widen_time` is ineffective with no time window; `widen_area` with no locality or a pinned doctor; `allow_tele` when tele is already allowed or the patient said "in-person only"; `next_day` beyond the 14-day horizon. Skipped steps are traced but not counted.
- **D-19: Multi-goal = two subtasks + one joint search.** The Supervisor writes two `schedule` subtasks (G1, G2) carrying the coupling. The Scheduling agent solves them together with `find_joint_slots` (same day, back-to-back ≤ 30 min, same hospital as a *soft* preference) and marks G2 "solved jointly". One proposal → one approval → `book_joint` (atomic, all-or-nothing). The joint search uses the deterministic planner in both modes; the LLM's job there is decomposition.
- **D-20: Clarification = interrupt + re-plan.** When the gap check finds no specialty, the `clarify` node interrupts with a question. The answer is screened by the emergency guard again, appended to the request, and the Supervisor re-plans (round 2 subtasks are prefixed `R2.`; old ones are marked skipped). Max 2 rounds, then an honest failure.
- **D-21: Booking race = re-plan.** The conditional `UPDATE … WHERE status='free' OR held-by-me` must affect exactly 1 row. Otherwise the slot is excluded, schedule/cost/verify/approve/book are re-opened, and the patient approves the new slot. Max 2 races, then an honest failure. Test: 8 threads booking one slot → exactly one wins.
- **D-22: Holds.** Soft hold TTL is 5 min for chat proposals and 15 min for proactive offers (the patient may not be looking at the app). Expired holds count as free; there is no background sweeper.
- **D-23: Patient conflicts.** Availability excludes slots where the patient already has an appointment at the same date/time; the Critic re-checks this.
- **D-24: Guest users** can book but are never remembered and cannot be waitlisted (no profile to notify). The honest outcome for a guest whose ladder is exhausted is "couldn't find".
- **D-25: Run context.** Limits, approval tokens and policies live in an in-process `RunContext`; the blackboard and audit trail are persisted. LangGraph uses `InMemorySaver`. *Alternative:* `SqliteSaver`. Not needed for a single-process demo, and it is listed as a known limitation.
- **D-26: Original 7 scenarios re-specified** (the code was absent): S01 direct, S02 clarification, S03 widen time, S04 widen area, S05 teleconsult, S06 emergency, S07 waitlist after the full ladder.

## M3 — API + UI

- **D-27: SSE via an in-memory trace bus.** Every event gets a global sequence number; `/api/stream` tails it with a cursor (Last-Event-ID aware) and the UI backfills from `/api/events/recent` on (re)connect. Chat calls are synchronous HTTP calls running in a worker thread, while the trace streams live over SSE. The client generates the `run_id` so it can follow its own run immediately.
- **D-28: The UI is served by FastAPI** from `frontend/dist`, which is **committed**. On jury day only Python is needed (`./run.sh`); `./run.sh dev` gives hot reload with Vite.
- **D-29: React + Tailwind v3, no component library.** shadcn/ui setup time wasn't worth it. Hand-built cards, chips and timeline, with lucide-react icons. Each agent has a fixed colour and icon and lights up for about 2 s after each event.
- **D-30: Browser quirk fixed.** In current Chromium `scrollIntoView()` returns a Promise; returning it from a `useEffect` broke React's cleanup. Effects now always use block bodies.
- **D-31: `availability.py` and `sse.py` are thin re-exports.** The code lives in `tools/doctors.py` (shared slot query) and `api/main.py`, so the layout still matches the design document.

## M4 — Proactive + multi-goal

- **D-32: Event bus.** An `asyncio.Queue` in the API process; its consumer runs `handle_event_sync` in a worker thread. Scripts and tests call `handle_event_sync` directly, so it is the same code path. HIS side effects (cancel block, free slot) are applied by the watcher at the start of handling, and the event is logged on the blackboard.
- **D-33: One proactive run per offer.** Each displaced patient gets a small LangGraph thread (`px-…`) that holds, verifies (the Critic's `verify_slot_free`), notifies, then `interrupt()`s for the patient's confirmation. Confirming resumes that thread, which mints the token and calls the gated `reschedule_appointment` / `book_slot`. Fully autonomous up to hold + notify, as specified.
- **D-34: Memory-driven alternatives.** Ranking weights: same doctor +3, usual doctor +2, preferred session +2, preferred tele +2.5 (otherwise tele −1.5), near home +1.5, −0.5 per day of delay. This is why P001 gets an evening slot, P014 a Kothrud morning and P023 a teleconsult from the *same* event.
- **D-35: Walk-ins** affected by a cancellation are logged as "front desk will phone" (no app profile). A patient who declines keeps no slot and the old appointment is marked cancelled; this is never silently rebooked.
- **D-36: Slot freed → waitlist.** Best match is chosen FIFO within matches (specialty, date window, doctor if specified), with bonuses for time and locality preferences. If the offered patient declines, the entry returns to "waiting"; up to 3 candidates are tried.

## M5 — Evidence + polish

- **D-37: Online path tested with a scripted fake tool-calling LLM** (`tests/test_react_loop.py`): the happy path, skipping the ladder (policy rejects it), a fabricated slot id (rejected), a direct `book_slot` (BLOCKED), and a crash (automatic offline fallback). The real DeepSeek endpoint could not be reached from the build container.
- **D-38: Scenario runner resets the DB before each scenario**, so scenarios are independent and deterministic. 18 scenarios (spec asked for ≥14).
- **D-39: Screenshots** use Python Playwright (`scripts/capture_screenshots.py`, 35 numbered steps at deviceScaleFactor 2). On machines without Playwright's bundled browser, set `PW_CHROMIUM` to an existing Chromium.
- **D-40: Auto-reseed on server start when the calendar day changed** (fixtures are relative to "today"), so a rehearsal yesterday cannot break today's demo. Manual reset: the UI button or `./run.sh reset`.
