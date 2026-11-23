"""Memory / Records agent (Unit 3).

recall  — builds the patient's preference picture from vector memory + structured records, resolves
          family links ("my mother" → P014) and "my usual doctor" → a concrete doctor id.
remember — after a run, decides what is worth remembering (LLM when online, rules offline).
"""
from __future__ import annotations

import re

from backend.core.context import RunContext
from backend.core.llm import LLMUnavailable, llm_json, note_fallback
from backend.tools.registry import call_tool

AGENT = "memory"


def _prefs_from_hits(hits: list[dict]) -> dict:
    prefs: dict = {}
    for h in hits:
        t = h["text"].lower()
        if h.get("kind") != "preference" and "prefer" not in t:
            continue
        m = re.search(r"prefers? (morning|evening|afternoon)", t)
        if m and "time" not in prefs:
            prefs["time"] = m.group(1)
            prefs["time_source"] = h["text"]
        if ("teleconsult" in t or "online" in t) and "prefer" in t and "mode" not in prefs:
            prefs["mode"] = "tele"
            prefs["mode_source"] = h["text"]
        if "in-person" in t and "prefer" in t and "mode" not in prefs:
            prefs["mode"] = "in_person"
            prefs["mode_source"] = h["text"]
        m = re.search(r"(kothrud|baner|hadapsar|viman nagar|shivajinagar|loni kalbhor)", t)
        if m and "near" in t or (m and "hospitals in" in t):
            prefs.setdefault("locality", m.group(1).title())
    return prefs


def recall(c: RunContext, goal_ref: str) -> dict:
    goals = c.cache["goals"]
    g = goals[goal_ref]
    requester = c.patient_id
    t = c.trace
    # 1) resolve who the appointment is for
    if g["who"] != "self":
        if requester == "GUEST":
            g["patient_id"] = None
            g["unresolved"] = f"Guest sessions have no family links, so I can't identify your {g['who']}."
        else:
            prof = call_tool(c, AGENT, "get_patient_profile", {"patient_id": requester},
                             reason=f"resolve the patient's '{g['who']}' through registered family links")
            fam = [f for f in prof.get("family", []) if f["relation"] == g["who"] or
                   (g["who"] in ("mother", "father") and f["relation"] == "parent")]
            if fam:
                g["patient_id"] = fam[0]["patient_id"]
                g["patient_name"] = fam[0]["name"]
                t.thought(AGENT, f"'{g['who']}' resolves to {fam[0]['name']} ({fam[0]['patient_id']}) via family links.")
            else:
                g["patient_id"] = None
                g["unresolved"] = f"I couldn't find your {g['who']} among your registered family members."
                t.thought(AGENT, g["unresolved"])
    else:
        g["patient_id"] = requester
    pid = g.get("patient_id")
    if not pid or pid == "GUEST":
        g.setdefault("prefs", {})
        fact = {"patient_id": pid, "prefs": {}, "note": "guest or unresolved patient — no memory used"}
        c.bb.write(AGENT, "facts", {f"memory_{goal_ref}": fact}, msg=f"memory_{goal_ref}: no profile (guest/unresolved)")
        return fact

    prof = call_tool(c, AGENT, "get_patient_profile", {"patient_id": pid}, reason="load stored preferences, insurance and family links")
    profile = prof.get("profile", {})
    g["patient_name"] = profile.get("name", pid)
    spec = g.get("specialty")
    q = "usual doctor preferences time of day mode" + (f" {spec.replace('_', ' ')}" if spec else "")
    if c.cache.get("parsed", {}).get("usual_doctor"):
        q = "usual regular doctor seen many times " + q
    rec = call_tool(c, AGENT, "recall_memory", {"patient_id": pid, "query": q, "k": 5},
                    reason="semantic recall of preferences / usual doctor before searching")
    hits = rec.get("hits", [])
    prefs = _prefs_from_hits(hits)
    # structured profile fills gaps (memory text wins: it is the more recent, explained source)
    if not prefs.get("time") and profile.get("preferred_time"):
        prefs["time"] = profile["preferred_time"]
        prefs["time_source"] = "patient profile"
    if not prefs.get("mode") and profile.get("preferred_mode"):
        prefs["mode"] = profile["preferred_mode"]
        prefs["mode_source"] = "patient profile"
    prefs.setdefault("home_locality", profile.get("locality"))

    usual = None
    if c.cache.get("parsed", {}).get("usual_doctor") or spec:
        hist = call_tool(c, AGENT, "get_visit_history", {"patient_id": pid},
                         reason="find the doctor this patient sees most (records back up the memory)")
        freq = hist.get("frequent_doctors", [])
        if spec:
            freq = [f for f in freq if f["specialty"] == spec]
        if profile.get("usual_doctor") and (not spec or profile["usual_doctor"]["specialty"] == spec):
            u = profile["usual_doctor"]
            usual = {"doctor_id": u["doctor_id"], "name": u["name"], "specialty": u["specialty"], "source": "profile + memory"}
        elif freq and freq[0]["visits"] >= 2:
            f = freq[0]
            usual = {"doctor_id": f["doctor_id"], "name": f["doctor_name"], "specialty": f["specialty"],
                     "source": f"visit history (×{f['visits']})"}
    if usual:
        prefs["usual_doctor_id"] = usual["doctor_id"]
        t.thought(AGENT, f"Usual doctor for {g['patient_name']}: {usual['name']} ({usual['specialty']}) — from {usual['source']}.")
        if c.cache.get("parsed", {}).get("usual_doctor") and g is goals.get("G1"):
            g["doctor_id"] = usual["doctor_id"]
            g["specialty"] = g.get("specialty") or usual["specialty"]
            g["doctor_from_memory"] = True
    pref_txt = ", ".join(f"{k}={v}" for k, v in prefs.items() if not k.endswith("_source") and v)
    t.thought(AGENT, f"Preferences for {g['patient_name']}: {pref_txt or 'none recorded'}.")
    g["prefs"] = prefs
    fact = {"patient_id": pid, "patient_name": g["patient_name"], "prefs": prefs, "usual_doctor": usual,
            "hits": hits[:5], "insurance_plan_id": profile.get("insurance_plan_id"),
            "upcoming": prof.get("upcoming", [])[:5], "family": prof.get("family", [])}
    c.bb.write(AGENT, "facts", {f"memory_{goal_ref}": fact},
               msg=f"memory_{goal_ref}: {len(hits)} hits, prefs({pref_txt or '—'})" + (f", usual={usual['name']}" if usual else ""))
    return fact


# ----------------------------------------------------------------------------- remember
SYSTEM_REMEMBER = """You are the Memory agent of a hospital appointment system. Decide what is worth
remembering long-term about the patient from this run. Only remember durable, useful facts
(preferences the patient stated or accepted, the booking episode). Max 3 items, each < 160 chars.
Return JSON: {"memories": [{"patient_id": "...", "kind": "episode|preference", "text": "..."}]}"""


def remember(c: RunContext) -> list[dict]:
    outcome = c.bb.facts.get("outcome", {})
    parsed = c.cache.get("parsed", {})
    items: list[dict] = []
    # rule-based baseline (always computed; also the offline answer)
    if outcome.get("status") == "booked":
        for a in outcome.get("appointments", []):
            items.append({"patient_id": a["patient_id"], "kind": "episode",
                          "text": f"Booked {a['specialty'].replace('_', ' ')} with {a['doctor_name']} at {a['hospital_name']} on {a['date']} {a['start']} ({a['mode'].replace('_', '-')})."})
        for r in outcome.get("relaxations", []):
            if r["step"] == "allow_tele":
                items.append({"patient_id": c.patient_id, "kind": "preference",
                              "text": "Accepted a teleconsultation when no in-person slot was free."})
    elif outcome.get("status") == "waitlisted":
        items.append({"patient_id": outcome.get("patient_id", c.patient_id), "kind": "episode",
                      "text": f"Waitlisted for {outcome.get('specialty', '').replace('_', ' ')} ({outcome.get('date_from')}..{outcome.get('date_to')}); no slot after full relaxation ladder."})
    for p in parsed.get("stated_preferences", []):
        items.append({"patient_id": c.patient_id, "kind": "preference", "text": p})
    if not c.offline and items:
        try:
            out = llm_json(c, AGENT, "remember", SYSTEM_REMEMBER,
                           f"Run outcome: {outcome}\nPatient said: {c.cache.get('text')}\nCandidate memories: {items}")
            cand = [m for m in out.get("memories", []) if m.get("text") and m.get("patient_id")][:3]
            valid_pids = {i["patient_id"] for i in items}
            cand = [m for m in cand if m["patient_id"] in valid_pids and len(m["text"]) <= 200]
            if cand:
                items = cand
                c.trace.thought(AGENT, f"LLM selected {len(cand)} memory item(s) worth keeping.")
        except LLMUnavailable as e:
            note_fallback(c, AGENT, "remember", e)
    saved = []
    for m in items[:3]:
        if m["patient_id"] in (None, "GUEST"):
            continue
        r = call_tool(c, AGENT, "save_memory", {"patient_id": m["patient_id"], "text": m["text"], "kind": m.get("kind", "episode")},
                      reason="durable fact from this run, useful for future requests")
        if r.get("ok"):
            saved.append(m)
    if not saved:
        c.trace.thought(AGENT, "Nothing durable to remember from this run.")
    return saved
