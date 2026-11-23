# legacy/

The original single-agent CLI (13-node LangGraph workflow, 5 tools, 7 scenarios) was **not present in this
repository** when the multi-agent upgrade started (the repo was empty — see DECISIONS.md D-01).

Its behaviour is preserved inside the new system:

| Original node(s) | Where it lives now |
|---|---|
| intake, gap_check, ask_user (clarification loop) | `backend/agents/supervisor.py` (parse + gap check) + `clarify` node with `interrupt()` in `backend/core/graph.py` |
| emergency_esc, escalate | `backend/core/guardrails.py::emergency_screen` + `escalate` node (runs first on every message) |
| search_doctors, check_availability, decide | `backend/agents/scheduling.py` (ReAct agent choosing its own tools) |
| relax (retry loop, monotonic ladder) | `backend/tools/policy.py` (policy checker) + `relax_constraint` tool |
| confirm (human y/n) | `approval` node with LangGraph `interrupt()` (Approve/Reject card in UI, y/n in CLI) |
| book (race = re-plan) | `backend/tools/booking.py::book_slot` (atomic conditional UPDATE) |
| waitlist, notify | `add_to_waitlist` tool, Notification agent |

If you have the original code locally, copy it into this folder unchanged; nothing imports from here.
