from __future__ import annotations

from typing import TypedDict


class GraphState(TypedDict, total=False):
    run_id: str
    patient_id: str
    text: str            # full request text (original + clarification answers)
    last_message: str    # latest human message — screened by the emergency guard
    next: str            # node chosen by the supervisor
    current: str | None  # subtask id being executed
    replan: bool
    response: dict
