"""Triage agent: symptoms → specialty + urgency.

Order is fixed: emergency_screen (hard rule) → classify_symptoms (trained model) → optional LLM review.
The LLM may override the specialty WITH stated reasoning, but it can never downgrade an emergency.
"""
from __future__ import annotations

from backend.core.context import RunContext
from backend.core.fallback_parser import SPECIALTY_LABEL
from backend.core.llm import LLMUnavailable, llm_json, note_fallback
from backend.tools.registry import call_tool

AGENT = "triage"
CONF_ACCEPT = 0.45
CONF_REVIEW = 0.75
EMERGENCY_PROB = 0.5
URGENCY_RANK = {"routine": 0, "soon": 1, "emergency": 2}

SYSTEM = f"""You are the Triage agent in a hospital. A trained classifier has labelled the patient's
symptoms. Review it. You may change the specialty if the classifier is clearly wrong, giving a
one-sentence reason. You may raise urgency, never lower it. Allowed specialties: {list(SPECIALTY_LABEL)}.
Allowed urgency: routine | soon | emergency.
Return JSON: {{"specialty": "...", "urgency": "...", "override": true|false, "reasoning": "..."}}"""


def run(c: RunContext, goal_ref: str) -> dict:
    g = c.cache["goals"][goal_ref]
    text = g.get("symptoms") or c.cache.get("text", "")
    t = c.trace
    es = call_tool(c, AGENT, "emergency_screen", {"text": text}, reason="hard safety rule always runs before any classification")
    if es.get("emergency"):
        res = {"specialty": None, "urgency": "emergency", "source": "hard-rule", "matches": es.get("matches")}
        c.bb.write(AGENT, "facts", {f"triage_{goal_ref}": res}, msg=f"triage_{goal_ref}: EMERGENCY (hard rule)")
        return res
    cl = call_tool(c, AGENT, "classify_symptoms", {"text": text}, reason="map free-text symptoms to a specialty and urgency")
    spec, conf, urg = cl["specialty"], cl["specialty_conf"], cl["urgency"]
    res = {"specialty": spec if conf >= CONF_ACCEPT else None, "specialty_conf": conf, "urgency": urg,
           "urgency_conf": cl["urgency_conf"], "emergency_prob": cl["emergency_prob"], "top3": cl["top3"],
           "evidence": cl["evidence"], "source": "classifier"}
    if cl["emergency_prob"] >= EMERGENCY_PROB:
        res["urgency"] = "emergency"
        t.decision(AGENT, f"Classifier emergency probability {cl['emergency_prob']:.0%} ≥ {EMERGENCY_PROB:.0%} → treat as EMERGENCY (never downgraded).")
    elif conf < CONF_REVIEW and not c.offline:
        try:
            out = llm_json(c, AGENT, "triage_review", SYSTEM,
                           f"Patient text: {text}\nClassifier: {cl['top3']} urgency={urg} ({cl['urgency_conf']:.2f})")
            ns, nu = out.get("specialty"), out.get("urgency")
            if ns in SPECIALTY_LABEL and nu in URGENCY_RANK:
                if URGENCY_RANK[nu] < URGENCY_RANK[urg]:
                    t.decision(AGENT, f"LLM tried to lower urgency {urg}→{nu}: rejected (urgency can only go up).")
                    nu = urg
                if ns != spec:
                    t.decision(AGENT, f"Override classifier {spec} ({conf:.0%}) → {ns}: {out.get('reasoning', '')[:160]}")
                    res.update({"specialty": ns, "source": "llm-override", "override_reason": out.get("reasoning", "")})
                elif res["specialty"] is None:
                    res["specialty"] = ns
                res["urgency"] = nu
        except LLMUnavailable as e:
            note_fallback(c, AGENT, "triage_review", e)
    if res["specialty"] is None:
        t.thought(AGENT, f"Low confidence ({conf:.0%} for {spec}) — not guessing; the Supervisor will ask the patient.")
    else:
        info = call_tool(c, AGENT, "get_specialty_info", {"specialty": res["specialty"]}, reason="confirm the specialty exists in our network")
        res["specialty_info"] = info.get("description")
        t.thought(AGENT, f"Symptoms → {SPECIALTY_LABEL[res['specialty']]} ({conf:.0%}), urgency {res['urgency']}; evidence: {', '.join(cl['evidence'][:3])}.")
    c.bb.write(AGENT, "facts", {f"triage_{goal_ref}": res},
               msg=f"triage_{goal_ref}: {res['specialty'] or 'unknown'} / {res['urgency']}")
    return res
