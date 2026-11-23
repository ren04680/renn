"""Online path: the Scheduling agent's ReAct loop with a scripted fake tool-calling LLM.

Proves the guarantees hold even when the LLM misbehaves:
  * it tries to skip the relaxation ladder   → policy error, it must follow the allowed step
  * it proposes a slot id no tool returned    → rejected (zero fabrication)
  * it tries to book without approval         → BLOCKED by the gate
  * it crashes / times out                    → automatic offline fallback, marked in the trace
"""
import json
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import backend.config as config
from backend.config import settings
from backend.core import llm
from backend.core.fallback_parser import parse_request
from backend.core.runner import resume_run, start_run
from backend.core.trace import bus


class FakeLLM:
    def __init__(self, mode="good"):
        self.mode = mode
        self.calls = 0

    def bind_tools(self, tools):
        self.tool_names = [t["function"]["name"] for t in tools]
        self.s = {"n": 0}
        return self

    def _tc(self, name, args, reason):
        self.s["n"] += 1
        self.s["last_tool"] = name
        return AIMessage(content=f"Thinking: {reason}", tool_calls=[{"name": name, "args": {**args, "reason": reason}, "id": f"c{self.s['n']}"}])

    def invoke(self, msgs):
        self.calls += 1
        if self.mode == "crash":
            raise TimeoutError("simulated DeepSeek timeout")
        sys_txt = msgs[0].content
        if "Supervisor" in sys_txt:
            p = parse_request(msgs[1].content)
            return AIMessage(content=json.dumps({"intent": p["intent"], "goals": p["goals"], "constraints": {},
                                                 "usual_doctor": p["usual_doctor"], "plan_summary": "recall → schedule → cost → verify → approve"}))
        if "Triage agent" in sys_txt:
            return AIMessage(content='{"specialty": null, "urgency": "routine", "override": false, "reasoning": "agree"}')
        if "SMS" in sys_txt:
            tpl = msgs[1].content.split("Template (for reference): ", 1)[1]
            return AIMessage(content=json.dumps({"subject": "Confirmed", "body": tpl[:390]}))
        if "Memory agent" in sys_txt:
            return AIMessage(content='{"memories": []}')
        return self._sched(msgs)

    def _sched(self, msgs):
        s = self.s
        goal = json.loads(msgs[1].content.split("Goal:\n", 1)[1])
        last = msgs[-1]
        if isinstance(last, HumanMessage) and "Rejected" in last.content:
            return AIMessage(content=json.dumps({"action": "propose", "slot_id": s["held"], "rationale": "corrected after rejection"}))
        if not isinstance(last, ToolMessage):
            if self.mode == "book_attempt" and not s.get("tried_book"):
                s["tried_book"] = True
                return self._tc("book_slot", {"slot_id": "S00001", "patient_id": goal["patient_id"] or "GUEST"}, "just book it directly")
            return self._tc("search_doctors", {"specialty": goal["specialty"]}, "find candidate doctors")
        res = json.loads(last.content)
        lt = s["last_tool"]
        if lt == "book_slot":
            return self._tc("search_doctors", {"specialty": goal["specialty"]}, "booking is gated, so search properly")
        if lt == "search_doctors":
            return self._tc("get_availability", {}, "check free slots under current constraints")
        if lt == "relax_constraint":
            if not res.get("ok"):
                m = re.search(r"next allowed step is '(\w+)'", res.get("error", ""))
                return self._tc("relax_constraint", {"step": m.group(1)}, "follow the policy's allowed step")
            return self._tc("get_availability", {}, "re-check after relaxing")
        if lt == "get_availability":
            if res.get("count"):
                return self._tc("hold_slot", {"slot_id": res["slots"][0]["slot_id"], "patient_id": goal["patient_id"] or "GUEST"}, "hold the best slot")
            if self.mode == "skip_ladder" and not s.get("skipped"):
                s["skipped"] = True
                return self._tc("relax_constraint", {"step": "next_day"}, "jump straight to another day")
            return self._tc("relax_constraint", {"step": goal["next_allowed_relaxation"] or "next_day"}, "no slots; relax one step")
        if lt == "hold_slot":
            s["held"] = res["slot"]["slot_id"]
            if self.mode == "fabricate" and not s.get("fab"):
                s["fab"] = True
                return AIMessage(content=json.dumps({"action": "propose", "slot_id": "S99999", "rationale": "made up"}))
            return AIMessage(content=json.dumps({"action": "propose", "slot_id": s["held"], "rationale": "best match from tool results"}))
        return AIMessage(content='{"action": "propose", "slot_id": "none"}')


@pytest.fixture()
def online(monkeypatch, fresh):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    settings.update(offline=False)

    def use(mode):
        fake = FakeLLM(mode)
        llm.set_model_override(fake)
        return fake

    yield use
    llm.set_model_override(None)
    settings.update(offline=True)


def _run(text, patient="GUEST"):
    r = start_run(text, patient)
    while r["status"] == "waiting":
        r = resume_run(r["run_id"], {"approved": True})
    return r, bus.for_run(r["run_id"])


def test_llm_drives_tools_and_books(online):
    fake = online("good")
    r, evs = _run("I need a dermatologist in Baner tomorrow morning")
    assert r["response"]["kind"] == "booked"
    assert r["stats"]["llm_calls"] >= 4 and r["stats"]["fallbacks"] == 0
    calls = [e for e in evs if e["type"] == "tool_call" and e["agent"] == "scheduling"]
    assert any("find candidate doctors" in e["payload"]["reason"] for e in calls)  # LLM's own reason is shown
    assert not any(e["type"] == "fallback" for e in evs)


def test_llm_cannot_skip_ladder(online):
    online("skip_ladder")
    r, evs = _run("I need a gastroenterologist tomorrow")
    assert any(e["type"] == "relaxation" and e["payload"].get("rejected") for e in evs)
    assert r["response"]["kind"] == "booked"
    assert r["response"]["outcome"]["appointments"][0]["mode"] == "tele"
    assert [x["step"] for x in r["response"]["outcome"]["relaxations"]] == ["allow_tele"]


def test_llm_fabricated_slot_rejected(online):
    online("fabricate")
    r, evs = _run("I need a dermatologist in Baner tomorrow morning")
    assert any(e["type"] == "error" and "no tool returned" in e["msg"] for e in evs)
    assert r["response"]["outcome"]["appointments"][0]["slot_id"] != "S99999"


def test_llm_cannot_book_without_approval(online):
    online("book_attempt")
    r, evs = _run("I need a dermatologist in Baner tomorrow morning")
    blocked = [e for e in evs if e["type"] == "tool_result" and e["payload"]["tool"] == "book_slot" and e["payload"]["result"].get("blocked")]
    assert blocked, "first book_slot attempt must be blocked by the gate"
    assert r["response"]["kind"] == "booked"  # booked later, only after the human approval


def test_llm_failure_falls_back_to_offline(online):
    online("crash")
    r, evs = _run("I need a dermatologist in Baner tomorrow morning")
    assert r["response"]["kind"] == "booked"
    fb = [e for e in evs if e["type"] == "fallback"]
    assert fb and any(e["payload"]["step"] == "react_scheduling" for e in fb)
