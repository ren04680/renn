"""DeepSeek Chat via langchain-openai (OpenAI-compatible endpoint), with automatic offline fallback.

Rules:
- If the run is offline (DEMO_OFFLINE=1 or no key) -> `LLMUnavailable` immediately, callers use offline logic.
- Any error/timeout -> `LLMUnavailable`; the caller falls back and a `fallback` trace event is emitted.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Any

from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TIMEOUT
from backend.core.context import RunContext


class LLMUnavailable(Exception):
    pass


_model = None
_lock = threading.Lock()


def chat_model():
    global _model
    with _lock:
        if _model is None:
            from langchain_openai import ChatOpenAI

            _model = ChatOpenAI(
                model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY or "missing", base_url=DEEPSEEK_BASE_URL,
                timeout=LLM_TIMEOUT, max_retries=1, temperature=0,
            )
        return _model


# test hook: tests can inject a fake chat model (e.g. scripted tool-calling LLM)
_override = None


def set_model_override(m) -> None:
    global _override
    _override = m


def get_model(c: RunContext):
    if _override is not None:
        return _override
    if c.offline:
        raise LLMUnavailable("offline mode")
    return chat_model()


def note_fallback(c: RunContext, agent: str, step: str, err: Exception | str) -> None:
    c.fallbacks += 1
    c.trace(agent, "fallback", f"LLM unavailable for '{step}' → using offline logic ({str(err)[:90]})",
            {"step": step, "error": str(err)[:300], "offline_mode": c.offline})


def parse_json(text: str) -> Any:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", t, re.S)
        if m:
            return json.loads(m.group(1))
        raise


def llm_json(c: RunContext, agent: str, step: str, system: str, user: str) -> Any:
    """One JSON-returning LLM call. Raises LLMUnavailable on offline/any failure."""
    from langchain_core.messages import HumanMessage, SystemMessage

    model = get_model(c)
    try:
        c.llm_calls += 1
        resp = model.invoke([SystemMessage(system), HumanMessage(user)])
        return parse_json(resp.content if isinstance(resp.content, str) else str(resp.content))
    except LLMUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        raise LLMUnavailable(f"{type(e).__name__}: {e}") from e
