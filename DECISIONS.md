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
