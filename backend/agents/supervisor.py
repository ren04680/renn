"""Supervisor agent (Unit 4): reads the user goal, decomposes it into subtasks on the blackboard,
decides which specialist acts next (dependency-aware dispatch), handles re-plans (critic REVISE,
booking race, clarification) and decides when the goal is done."""
from __future__ import annotations

from datetime import date

from backend.config import MAX_CLARIFY_ROUNDS
from backend.core.blackboard import Subtask
from backend.core.context import RunContext
from backend.core.fallback_parser import LOCALITIES, RELATIONS, SPECIALTY_LABEL, parse_request
from backend.core.llm import LLMUnavailable, llm_json, note_fallback
from backend.tools.common import date_label

AGENT = "supervisor"

OWNER_NODE = {"recall": "memory", "triage": "triage", "gap_check": "gap_check", "schedule": "scheduling",
              "cost": "billing", "verify": "critic", "approve": "approval", "book": "book",
              "notify": "notification", "remember": "remember", "billing_answer": "billing"}
AGENT_LABEL = {"memory": "Memory agent", "triage": "Triage agent", "scheduling": "Scheduling agent",
               "billing": "Billing agent", "critic": "Critic", "human": "Patient (human approval)",
               "notification": "Notification agent", "supervisor": "Supervisor"}

SYSTEM_PARSE = """You are the Supervisor of a hospital appointment multi-agent system in Pune.
Decompose the patient's message into goals and constraints. Today is {today} ({weekday}).
Specialties: {specs}. Localities: {locs}. Relations: {rels}.
Return ONLY JSON:
{{"intent": "book|billing|reschedule|cancel|unknown",
  "goals": [{{"who": "self|<relation>", "specialty": "<specialty or null>", "symptoms": "<symptom text or null>"}}],
  "constraints": {{"date_from": "YYYY-MM-DD|null", "date_to": "YYYY-MM-DD|null", "time_from": "HH:MM|null",
                   "time_to": "HH:MM|null", "locality": "<locality|null>", "mode": "tele|in_person|null"}},
  "usual_doctor": true|false, "doctor_name": "<surname or null>",
  "coupling": {{"same_day": bool, "back_to_back": bool, "same_hospital": "soft|null"}} or null,
  "plan_summary": "<one sentence: how you will decompose and delegate>"}}
Use one goal per appointment (two people or two specialties = two goals). Do not invent constraints."""


# ----------------------------------------------------------------------------- parsing
def parse(c: RunContext, text: str) -> dict:
    base = parse_request(text)
    if c.offline:
        c.trace.thought(AGENT, "Offline mode: parsing with the rule-based parser (re + datetime).")
        return base
    try:
        today = date.today()
        out = llm_json(c, AGENT, "parse_and_decompose",
                       SYSTEM_PARSE.format(today=today.isoformat(), weekday=today.strftime("%A"), specs=list(SPECIALTY_LABEL),
                                           locs=list(LOCALITIES), rels=list(RELATIONS)), text)
        merged = _merge(base, out)
        merged["parser"] = "llm (validated against rule parser)"
        if out.get("plan_summary"):
            c.trace.thought(AGENT, f"LLM plan: {str(out['plan_summary'])[:200]}", {"llm": True})
        return merged
    except (LLMUnavailable, Exception) as e:  # noqa: BLE001
        note_fallback(c, AGENT, "parse_and_decompose", e)
        return base


def _merge(base: dict, llm: dict) -> dict:
    m = {**base}
    if llm.get("intent") in ("book", "billing", "reschedule", "cancel", "unknown"):
        m["intent"] = llm["intent"] if not (llm["intent"] == "unknown" and base["intent"] != "unknown") else base["intent"]
    goals = []
    for g in llm.get("goals") or []:
        who = g.get("who") if g.get("who") in (["self"] + list(RELATIONS)) else "self"
        spec = g.get("specialty") if g.get("specialty") in SPECIALTY_LABEL else None
        goals.append({"who": who, "specialty": spec, "symptoms": g.get("symptoms") or None})
    if goals:
        # never lose an explicit specialty the rule parser found
        for i, g in enumerate(goals):
            if not g["specialty"] and i < len(base["goals"]) and base["goals"][i]["specialty"]:
                g["specialty"] = base["goals"][i]["specialty"]
        m["goals"] = goals
        m["multi_goal"] = len(goals) > 1
    lc = llm.get("constraints") or {}
    bc = dict(base["constraints"])
    for k in ("date_from", "date_to", "time_from", "time_to"):
        v = lc.get(k)
        if v and v != "null" and not bc.get(k):
            bc[k] = v
    if lc.get("locality") in LOCALITIES and not bc.get("locality"):
        bc["locality"] = lc["locality"]
    if lc.get("mode") in ("tele", "in_person") and not bc.get("mode"):
        bc["mode"], bc["mode_explicit"] = lc["mode"], True
    m["constraints"] = bc
    m["usual_doctor"] = bool(base["usual_doctor"] or llm.get("usual_doctor"))
    if llm.get("coupling") and m.get("multi_goal"):
        cp = llm["coupling"]
        m["coupling"] = {"same_day": bool(cp.get("same_day")), "back_to_back": bool(cp.get("back_to_back")),
                         "same_hospital": "soft" if cp.get("same_hospital") else None}
    return m


# ----------------------------------------------------------------------------- planning
def plan(c: RunContext, round_no: int = 1) -> list[Subtask]:
    text = c.cache["text"]
    parsed = parse(c, text)
    c.cache["parsed"] = parsed
    pre = "" if round_no == 1 else f"R{round_no}."
    goals = {}
    for i, g in enumerate(parsed["goals"], start=1):
        goals[f"G{i}"] = {"who": g["who"], "specialty": g["specialty"], "symptoms": g.get("symptoms"),
                          "doctor_id": None, "patient_id": c.patient_id if g["who"] == "self" else None}
    if parsed.get("doctor_name"):
        from backend.db.models import Doctor
        from backend.db.session import get_session

        d = None
        with get_session() as s:
            for tok in parsed["doctor_name"].split():
                if len(tok) >= 3 and tok not in ("tomorrow", "today", "next", "the", "for", "and"):
                    d = s.query(Doctor).filter(Doctor.name.ilike(f"% {tok}%")).first()
                    if d:
                        break
            if d:
                goals["G1"]["doctor_id"] = d.id
                goals["G1"]["specialty"] = goals["G1"]["specialty"] or d.specialty
                c.trace.thought(AGENT, f"Patient named {d.name} → pinning goal G1 to {d.id}.")
    for ref, carried in (c.cache.get("carry_goals") or {}).items():
        if ref in goals:
            for k, v in carried.items():
                if v and not goals[ref].get(k):
                    goals[ref][k] = v
            if carried.get("specialty"):
                goals[ref]["symptoms"] = None  # already triaged — don't re-classify text that now contains scheduling answers
    c.cache["goals"] = goals
    sts: list[Subtask] = []

    def add(kind, owner, title, deps, goal_ref=None, params=None) -> str:
        sid = f"{pre}T{len(sts) + 1}"
        sts.append(Subtask(id=sid, title=title, kind=kind, owner=owner, depends_on=deps, goal_ref=goal_ref, params=params or {}))
        return sid

    intent = parsed["intent"]
    c.bb.write(AGENT, "goal", text, msg=f"goal: {text[:100]}")
    if intent == "billing":
        r = add("recall", "memory", "Load profile, insurance and upcoming appointments", [], "G1")
        add("billing_answer", "billing", "Answer the cost / insurance question from data", [r], "G1")
    elif intent == "cancel" or parsed.get("unsupported"):
        r = add("recall", "memory", "Load profile and upcoming appointments", [], "G1")
        add("gap_check", "supervisor", "Check the request is within what this system may do", [r])
    else:
        recalls, triages = {}, []
        for ref, g in goals.items():
            who = "patient" if g["who"] == "self" else f"patient's {g['who']}"
            recalls[ref] = add("recall", "memory", f"Recall memory & preferences ({who})", [], ref)
        for ref, g in goals.items():
            needs = not g["specialty"] and (g.get("symptoms") or not (parsed.get("usual_doctor") or g.get("doctor_id")))
            if needs and (g.get("symptoms") or parsed.get("has_symptoms")):
                triages.append(add("triage", "triage", f"Classify symptoms → specialty + urgency ({ref})", [recalls[ref]], ref))
        gap = add("gap_check", "supervisor", "Gap check: is anything essential missing?", list(recalls.values()) + triages)
        if len(goals) > 1:
            cp = parsed.get("coupling") or {"same_day": True, "back_to_back": False, "same_hospital": None}
            refs = list(goals)
            s1 = add("schedule", "scheduling", f"Find {_lbl(goals['G1'])} slot for {goals['G1']['who']}", [gap], "G1",
                     {"joint_with": refs[1:], "coupling": cp})
            s2 = add("schedule", "scheduling", f"Find {_lbl(goals['G2'])} slot for {goals['G2']['who']} (coupled with {s1})", [gap], "G2",
                     {"joint_with": [refs[0]], "coupling": cp, "solved_with": s1})
            sched = [s1, s2]
        else:
            title = f"Find best {_lbl(goals['G1'])} slot" if goals["G1"]["specialty"] or goals["G1"].get("doctor_id") else "Find best slot (specialty from triage/memory)"
            sched = [add("schedule", "scheduling", title, [gap], "G1", {"reschedule": intent == "reschedule"})]
        cost = add("cost", "billing", "Attach fee + insurance estimate", sched)
        ver = add("verify", "critic", "Verify proposal (ids exist, slot free, matches request)", [cost])
        appr = add("approve", "human", "Patient approves / rejects (interrupt)", [ver])
        book = add("book", "scheduling", "Book — gated by approval token", [appr])
        notif = add("notify", "notification", "Draft + send confirmation", [book])
        add("remember", "memory", "Decide what is worth remembering", [notif])
    c.bb.write(AGENT, "subtasks", sts)
    summary = " → ".join(f"{s.id}:{s.kind}@{s.owner}" for s in sts)
    c.bb.write(AGENT, "decisions", {"type": "plan", "round": round_no, "intent": intent, "goals": goals,
                                    "coupling": parsed.get("coupling"), "parser": parsed.get("parser")},
               msg=f"plan (round {round_no}, intent={intent}, {len(goals)} goal(s))")
    c.trace.decision(AGENT, f"Decomposed into {len(sts)} subtasks: {summary}",
                     {"subtasks": [s.model_dump() for s in sts], "goals": goals, "coupling": parsed.get("coupling")})
    if parsed.get("multi_goal"):
        cp = parsed.get("coupling") or {}
        c.trace.thought(AGENT, f"Multi-goal request: {len(goals)} linked goals with coupling constraint "
                        + ", ".join(k.replace('_', ' ') + ('' if v is True else f' ({v})') for k, v in cp.items() if v)
                        + " → one joint search, one combined proposal, one approval.")
    return sts


def _lbl(g: dict) -> str:
    return SPECIALTY_LABEL.get(g.get("specialty") or "", "doctor")


# ----------------------------------------------------------------------------- gap check
def gap_check(c: RunContext) -> dict:
    """Returns {"ok": True} or {"question": ...} or {"fail": ...} or {"emergency": ...}."""
    goals = c.cache["goals"]
    parsed = c.cache["parsed"]
    if parsed.get("unsupported"):
        return {"info": f"Our hospital network doesn't offer **{parsed['unsupported']}** yet, so I won't book an unrelated "
                        "specialist just to have something to show you. Please consult a dedicated clinic for this — or, if you also "
                        "have another problem, describe it and I'll find the right doctor."
                        + (" If you are struggling right now, you can call Tele-MANAS on **14416** (free, 24×7)." if "mental" in parsed["unsupported"] else "")}
    if parsed["intent"] == "cancel":
        up = (c.bb.facts.get("memory_G1") or {}).get("upcoming") or []
        lst = "".join(f"\n• {a['doctor_name']} — {date_label(a['date'])} {a['start']} (ref {a['appointment_id']})" for a in up[:5])
        return {"info": "Cancelling isn't something I do on my own: it needs front-desk confirmation in this hospital. "
                        + (f"Your upcoming appointments:{lst}\nCall the front desk with the reference number, or ask me to **reschedule** instead." if up
                           else "You have no upcoming appointments.")}
    for ref, g in goals.items():
        tri = c.bb.facts.get(f"triage_{ref}") or {}
        if tri.get("urgency") == "emergency":
            return {"emergency": f"Triage flagged an emergency for {ref}"}
        if tri.get("specialty") and not g.get("specialty"):
            g["specialty"] = tri["specialty"]
        if g.get("unresolved"):
            return {"fail": g["unresolved"] + " Please ask them to register, or book from their own account."}
    if parsed["intent"] == "reschedule":
        mem = c.bb.facts.get("memory_G1") or {}
        up = mem.get("upcoming") or []
        g = goals["G1"]
        cand = [a for a in up if not g.get("specialty") or a["specialty"] == g["specialty"]]
        if not cand:
            return {"fail": "You have no upcoming appointment to reschedule."}
        a = cand[0]
        g.update({"specialty": a["specialty"], "doctor_id": g.get("doctor_id") or a["doctor_id"],
                  "reschedule_of": {"appointment_id": a["appointment_id"], "date": a["date"], "start": a["start"],
                                    "doctor_name": a["doctor_name"]}})
        c.trace.thought(AGENT, f"Reschedule target: {a['appointment_id']} ({a['doctor_name']} {a['date']} {a['start']}).")
    missing = [ref for ref, g in goals.items() if not g.get("specialty")]
    if parsed["intent"] == "unknown" or missing:
        rounds = c.cache.get("clarify_rounds", 0)
        if rounds >= MAX_CLARIFY_ROUNDS:
            return {"fail": "I still couldn't work out which specialist you need, so I haven't booked anything. "
                            "Please describe your symptoms or name a specialty (e.g. 'dermatologist')."}
        q = "Sure — I can help with that. What is the problem (symptoms), or which specialist do you need? And when would you like to come?"
        if parsed["intent"] != "unknown" and parsed["constraints"].get("date_from"):
            q = "Got it. What symptoms do you have, or which specialist would you like to see?"
        tri = c.bb.facts.get("triage_G1") or {}
        if tri.get("top3"):
            opts = ", ".join(SPECIALTY_LABEL[x["specialty"]] for x in tri["top3"][:2])
            q += f" (From your description it could be {opts}, but I'm not confident enough to guess.)"
        return {"question": q, "missing": missing, "purpose": "specialty",
                "suggestions": ["Knee pain", "Skin rash", "Chest discomfort", "Fever and cough"]}
    if parsed["intent"] in ("book", "reschedule") and not c.cache.get("prefs_asked"):
        pq = preference_question(c)
        if pq:
            c.cache["prefs_asked"] = True
            return pq
    return {"ok": True}


def preference_question(c: RunContext) -> dict | None:
    """Receptionist-style intake: ask (once, in one message) only for what is missing and cannot be inferred.
    Memory fills what it can (usual time of day, home area, usual doctor) — those are *told*, not asked."""
    goals = c.cache["goals"]
    parsed = c.cache["parsed"]
    pc = parsed["constraints"]
    flex = parsed.get("flexible") or {}
    prefs = [g.get("prefs") or {} for g in goals.values()]
    known_from_memory = []
    need_date = not pc.get("date_from") and not flex.get("date")
    mem_time = all(p.get("time") for p in prefs)
    need_time = not pc.get("time_from") and not flex.get("time") and not mem_time
    if not pc.get("time_from") and not flex.get("time") and mem_time:
        known_from_memory.append(f"your usual **{prefs[0]['time']}** slots")
    home = all(p.get("home_locality") for p in prefs)
    area_given = pc.get("locality") or pc.get("mode") == "tele" or flex.get("area")
    need_area = not area_given and not home
    if not area_given and home:
        known_from_memory.append(f"hospitals near **{prefs[0]['home_locality']}**")
    g1 = goals.get("G1") or {}
    if g1.get("prefs", {}).get("usual_doctor_id") and not g1.get("doctor_id"):
        from backend.db.models import Doctor
        from backend.db.session import get_session

        with get_session() as s:
            d = s.get(Doctor, g1["prefs"]["usual_doctor_id"])
            if d and d.specialty == g1.get("specialty"):
                known_from_memory.append(f"your usual doctor **{d.name}** if free")
    if not (need_date or need_time or need_area):
        if known_from_memory:
            c.trace.thought(AGENT, "No need to ask the patient: memory supplies " + ", ".join(k.replace("**", "") for k in known_from_memory) + ".")
        return None
    what = " + ".join(SPECIALTY_LABEL.get(g.get("specialty"), "doctor") for g in goals.values())
    qs = []
    if need_date:
        qs.append("**Which day?** (e.g. tomorrow, Friday, next week — or “earliest”)")
    if need_time:
        qs.append("**What time?** Morning (9:30–12:00) or evening (4:00–6:30) — or “any time”")
    if need_area:
        qs.append("**Which area of Pune** suits you (Kothrud, Baner, Hadapsar, Viman Nagar, Shivajinagar, Loni Kalbhor) — or is an **online** consultation fine?")
    head = f"Sure — let's book your **{what}** appointment. " + ("A few quick questions so I pick the right slot:" if len(qs) > 1 else "One quick question:")
    body = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(qs)) if len(qs) > 1 else qs[0]
    tail = ("\nFrom what I remember, I'll use " + ", ".join(known_from_memory) + " — tell me if you'd prefer otherwise.") if known_from_memory else ""
    if need_date and not need_time and not need_area:
        sugg = ["Tomorrow", "Day after tomorrow", "Next week", "Earliest available"]
    elif need_area:
        sugg = ["Tomorrow morning, Kothrud", "Tomorrow evening, anywhere", "Earliest, any time, anywhere", "Online consultation, earliest"]
    else:
        sugg = ["Tomorrow morning", "Tomorrow evening", "Day after tomorrow, any time", "Earliest, any time"]
    missing = [m for m, n in (("date", need_date), ("time", need_time), ("area", need_area)) if n]
    c.trace.thought(AGENT, f"Before searching, ask the patient for: {', '.join(missing)}"
                    + (f"; memory already gives: {', '.join(k.replace('**', '') for k in known_from_memory)}" if known_from_memory else "") + ".")
    return {"question": head + "\n" + body + tail, "missing": missing, "purpose": "preferences", "suggestions": sugg}


# ----------------------------------------------------------------------------- dispatch
def next_subtask(c: RunContext) -> Subtask | None:
    ready = c.bb.ready()
    return ready[0] if ready else None


def explain_dispatch(c: RunContext, st: Subtask) -> None:
    deps = ", ".join(f"{d} ✓" for d in st.depends_on) or "none"
    who = AGENT_LABEL.get(st.owner, st.owner)
    c.trace.decision(AGENT, f"Dispatch {st.id} '{st.title}' → {who} (deps: {deps})",
                     {"subtask": st.id, "owner": st.owner, "kind": st.kind, "goal_ref": st.goal_ref})


def skip_downstream(c: RunContext, kinds: tuple[str, ...], why: str) -> None:
    for s in c.bb.subtasks:
        if s.kind in kinds and s.status == "pending":
            c.bb.set_status(AGENT, s.id, "skipped", {"why": why}, msg=f"{s.id} skipped — {why}")


def reset_for_replan(c: RunContext, kinds: tuple[str, ...], why: str) -> None:
    for s in c.bb.subtasks:
        if s.kind in kinds and s.status in ("done", "failed", "running"):
            c.bb.set_status(AGENT, s.id, "pending", msg=f"{s.id} re-opened — {why}")


# ----------------------------------------------------------------------------- final answer
def compose_response(c: RunContext) -> dict:
    o = c.bb.facts.get("outcome") or {}
    st = o.get("status")
    if st == "booked":
        lines = []
        for a in o["appointments"]:
            mode = "🎥 video consultation" if a["mode"] == "tele" else f"at {a['hospital_name']}, {a['locality']}"
            pay = f" — you pay ₹{a['patient_pays']}" if a.get("patient_pays") is not None else ""
            who = f" for {a['patient_name']}" if a["patient_id"] != c.patient_id else ""
            lines.append(f"✅ **{a['doctor_name']}** ({SPECIALTY_LABEL.get(a['specialty'], a['specialty'])}){who} — "
                         f"{date_label(a['date'])}, {a['start']}–{a['end']}, {mode}{pay}. Ref **{a['appointment_id']}**.")
        text = ("Rescheduled. " if o.get("rescheduled") else "Booked! ") + "\n".join(lines)
        if o.get("disclosures"):
            text += "\n\nWhat I changed from your request: " + " ".join(o["disclosures"])
        text += "\nA confirmation SMS has been sent."
        return {"kind": "booked", "text": text, "outcome": o}
    if st == "waitlisted":
        text = (f"I couldn't find any {SPECIALTY_LABEL.get(o.get('specialty'), o.get('specialty'))} slot even after relaxing "
                f"your request step by step ({', '.join(r['step'].replace('_', ' ') for r in o.get('relaxations', [])) or 'no relaxation possible'}). "
                f"I won't invent one — you're on the **waitlist** (position #{o.get('position') or '?'}). "
                "The moment a matching slot frees up I'll hold it for you and ask you to confirm.")
        return {"kind": "waitlisted", "text": text, "outcome": o}
    if st == "rejected":
        return {"kind": "rejected", "text": "Okay — nothing was booked and the held slot has been released. "
                                            "Tell me what you'd like to change (time, area, doctor, mode).", "outcome": o}
    if st == "emergency":
        return {"kind": "emergency", "text": o.get("message", ""), "outcome": o}
    if st == "billing":
        return {"kind": "billing", "text": o.get("answer", ""), "outcome": o}
    if st == "info":
        return {"kind": "text", "text": o.get("text", ""), "outcome": o}
    reason = o.get("reason") or "I couldn't complete this request."
    return {"kind": "failed", "text": f"Sorry — {reason} Nothing was booked (I never guess a slot).", "outcome": o}
