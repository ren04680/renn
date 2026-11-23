"""Rule-based request parser (`re` + `datetime`) — used offline, when the LLM fails, and to
validate/complete LLM parses. Produces the same structure the Supervisor's LLM parse produces."""
from __future__ import annotations

import re
from datetime import date, timedelta

SPECIALTY_SYNONYMS = {
    "cardiology": ["cardiologist", "cardiology", "heart specialist", "heart doctor", "cardiac"],
    "dermatology": ["dermatologist", "dermatology", "skin doctor", "skin specialist", "derma"],
    "orthopedics": ["orthopedic", "orthopaedic", "orthopedist", "orthopedics", "ortho", "bone doctor", "bone specialist"],
    "neurology": ["neurologist", "neurology", "neuro", "brain specialist", "nerve specialist"],
    "ent": ["ent", "ear nose throat", "ear, nose", "otolaryngologist", "ent specialist"],
    "pediatrics": ["pediatrician", "paediatrician", "pediatrics", "child specialist", "kids doctor", "child doctor"],
    "general_medicine": ["general physician", "general medicine", "family doctor", "physician", "gp"],
    "gastroenterology": ["gastroenterologist", "gastroenterology", "gastro", "stomach specialist"],
}
SPECIALTY_LABEL = {
    "cardiology": "Cardiology", "dermatology": "Dermatology", "orthopedics": "Orthopedics", "neurology": "Neurology",
    "ent": "ENT", "pediatrics": "Pediatrics", "general_medicine": "General Medicine", "gastroenterology": "Gastroenterology",
}
LOCALITIES = {
    "Kothrud": ["kothrud"], "Baner": ["baner"], "Hadapsar": ["hadapsar"], "Loni Kalbhor": ["loni kalbhor", "loni"],
    "Viman Nagar": ["viman nagar", "vimannagar"], "Shivajinagar": ["shivajinagar", "shivaji nagar"],
}
RELATIONS = {
    "mother": ["mother", "mom", "mum", "maa", "mummy", "mommy"], "father": ["father", "dad", "papa"],
    "spouse": ["wife", "husband", "spouse"], "son": ["son"], "daughter": ["daughter"],
    "child": ["child", "kid"], "parent": ["parent"], "sibling": ["brother", "sister", "sibling"],
}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
SESSIONS = {"morning": ("09:00", "12:00"), "afternoon": ("12:00", "16:00"), "evening": ("16:00", "20:00")}

UNSUPPORTED = [
    ("ophthalmology (eye care)", r"\b(eye|eyes|vision|ophthalm\w*|cataract|spectacles|glasses|aankh\w*)\b"),
    ("dentistry", r"\b(dentist|dental|tooth|teeth|toothache|gums?|daant|daat)\b"),
    ("gynaecology / obstetrics", r"\b(pregnan\w*|gyn(a)?ec\w*|obstetric\w*|periods?|menstrua\w*)\b"),
    ("psychiatry / mental health", r"\b(depress\w*|anxiety|psychiatr\w*|mental health|panic attacks?)\b"),
    ("urology / nephrology", r"\b(kidney stones?|urolog\w*|nephrolog\w*|prostate)\b"),
    ("oncology", r"\b(cancer|tumou?r|oncolog\w*|chemo\w*)\b"),
]

SYMPTOM_WORDS = re.compile(
    r"\b(pain|ache|aching|dard|fever|bukhar|rash|itch\w*|khujli|cough|khansi|cold|vomit\w*|ulti|nausea|dizz\w*|chakkar|"
    r"headache|migraine|swelling|swollen|bleed\w*|burn\w*|acidity|acne|pimples?|sore|blocked|numb\w*|tingl\w*|"
    r"breath\w*|palpitation\w*|bp|sugar|diabetes|injury|sprain|fracture|infection|allergy|tired|weak\w*|"
    r"stiff\w*|hair fall|dandruff|constipation|diarrh\w*|loose motions?|gas|bloat\w*|ear|throat|nose|knee|back|"
    r"shoulder|chest|stomach|pet|skin|eczema|seizure|fits|sweat\w*|insomnia|sleep)\b", re.I)


def _find_specialties(t: str) -> list[tuple[int, str]]:
    found = []
    for spec, syns in SPECIALTY_SYNONYMS.items():
        for s in sorted(syns, key=len, reverse=True):
            for m in re.finditer(r"\b" + re.escape(s) + r"s?\b", t):
                if s == "gp" and "gps" in t:
                    continue
                found.append((m.start(), spec))
    found.sort()
    out: list[tuple[int, str]] = []
    for pos, spec in found:
        if not out or out[-1][1] != spec or pos - out[-1][0] > 25:
            out.append((pos, spec))
    # de-dup same specialty mentioned twice close together
    seen = set()
    uniq = []
    for pos, spec in out:
        if spec in seen:
            continue
        seen.add(spec)
        uniq.append((pos, spec))
    return uniq


def _find_relations(t: str) -> list[tuple[int, str]]:
    out = []
    for rel, syns in RELATIONS.items():
        for s in syns:
            for m in re.finditer(r"\b(my|meri|mere|for)\s+(\w+\s+)?" + re.escape(s) + r"\b", t):
                out.append((m.start(), rel))
    out.sort()
    return out


def parse_date(t: str, today: date) -> tuple[str | None, str | None, str | None]:
    """Returns (date_from, date_to, description)."""
    def iso(d: date) -> str:
        return d.isoformat()

    if re.search(r"\bday after tomorrow\b|\bparso\b", t):
        d = today + timedelta(days=2)
        return iso(d), iso(d), "day after tomorrow"
    if re.search(r"\btomorrow\b|\btmrw\b|\btmr\b|\bkal\b", t):
        d = today + timedelta(days=1)
        return iso(d), iso(d), "tomorrow"
    if re.search(r"\btoday\b|\baaj\b", t):
        return iso(today), iso(today), "today"
    if re.search(r"\bnext week\b|\bagle hafte\b", t):
        nm = today + timedelta(days=7 - today.weekday())
        return iso(nm), iso(nm + timedelta(days=6)), "next week"
    if re.search(r"\bthis week\b", t):
        end = today + timedelta(days=6 - today.weekday())
        start = today + timedelta(days=1)
        if end < start:
            end = start
        return iso(start), iso(end), "this week"
    m = re.search(r"\bin (\d{1,2}) days?\b", t)
    if m:
        d = today + timedelta(days=int(m.group(1)))
        return iso(d), iso(d), f"in {m.group(1)} days"
    for i, wd in enumerate(WEEKDAYS):
        m = re.search(r"\b(next\s+|this\s+|on\s+)?" + wd + r"\b", t)
        if m:
            delta = (i - today.weekday()) % 7
            if delta == 0:
                delta = 7
            if m.group(1) and m.group(1).strip() == "next" and delta < 7 and (today + timedelta(days=delta)).isocalendar()[1] == today.isocalendar()[1]:
                delta += 7
            d = today + timedelta(days=delta)
            return iso(d), iso(d), wd.title()
    m = re.search(r"\b(\d{1,2})(st|nd|rd|th)?\s*(of\s+)?(" + "|".join(MONTHS) + r")[a-z]*\b", t) or \
        re.search(r"\b(" + "|".join(MONTHS) + r")[a-z]*\s+(\d{1,2})(st|nd|rd|th)?\b", t)
    if m:
        g = m.groups()
        if g[0].isdigit():
            day, mon = int(g[0]), MONTHS.index(g[3][:3]) + 1
        else:
            mon, day = MONTHS.index(g[0][:3]) + 1, int(g[1])
        try:
            d = date(today.year, mon, day)
            if d < today:
                d = date(today.year + 1, mon, day)
            return iso(d), iso(d), d.strftime("%d %b")
        except ValueError:
            pass
    m = re.search(r"\bon (the )?(\d{1,2})(st|nd|rd|th)\b", t)
    if m:
        day = int(m.group(2))
        try:
            d = date(today.year, today.month, day)
            if d < today:
                nm = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
                d = nm.replace(day=day)
            return iso(d), iso(d), d.strftime("%d %b")
        except ValueError:
            pass
    return None, None, None


def _hm(h: int, m: int = 0) -> str:
    return f"{h:02d}:{m:02d}"


def _to24(h: int, ampm: str | None, ctx_pm: bool = False) -> int:
    if ampm:
        ampm = ampm.lower().replace(".", "")
        if ampm.startswith("p") and h < 12:
            return h + 12
        if ampm.startswith("a") and h == 12:
            return 0
        return h
    if ctx_pm or 1 <= h <= 7:
        return h + 12 if h < 12 else h
    return h


def parse_time(t: str) -> tuple[str | None, str | None, str | None]:
    tm = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"
    m = re.search(r"\b(?:between|from)\s+" + tm + r"\s*(?:and|to|-)\s*" + tm, t) or re.search(r"\b" + tm + r"\s*(?:-|to)\s*" + tm + r"\b", t)
    if m:
        h1, m1, ap1, h2, m2, ap2 = m.groups()
        ap1 = ap1 or ap2
        a = _to24(int(h1), ap1)
        b = _to24(int(h2), ap2 or ap1)
        if b <= a:
            b += 12 if b + 12 <= 23 else 0
        if 6 <= a < b <= 22:
            return _hm(a, int(m1 or 0)), _hm(b, int(m2 or 0)), f"{_hm(a, int(m1 or 0))}–{_hm(b, int(m2 or 0))}"
    m = re.search(r"\bafter\s+" + tm, t)
    if m:
        h = _to24(int(m.group(1)), m.group(3))
        return _hm(h, int(m.group(2) or 0)), "20:00", f"after {_hm(h, int(m.group(2) or 0))}"
    m = re.search(r"\bbefore\s+" + tm, t)
    if m:
        h = _to24(int(m.group(1)), m.group(3))
        return "08:00", _hm(h, int(m.group(2) or 0)), f"before {_hm(h, int(m.group(2) or 0))}"
    m = re.search(r"\b(?:at|around|by)\s+" + tm, t) or re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if m:
        h = _to24(int(m.group(1)), m.group(3))
        if 6 <= h <= 21:
            mm = int(m.group(2) or 0)
            return _hm(h, mm), _hm(h + 1, mm), f"around {_hm(h, mm)}"
    for name, (a, b) in SESSIONS.items():
        if re.search(r"\b" + name + r"\b", t):
            return a, b, name
    if re.search(r"\bsubah\b", t):
        return "09:00", "12:00", "morning"
    if re.search(r"\bshaam\b|\bsham\b", t):
        return "16:00", "20:00", "evening"
    return None, None, None


def parse_request(text: str, today: date | None = None) -> dict:
    today = today or date.today()
    raw = text or ""
    t = " " + raw.lower().replace("’", "'") + " "
    t = re.sub(r"\s+", " ", t)

    df, dt, dtext = parse_date(t, today)
    tf, tt, ttext = parse_time(t)

    locality = None
    for loc, syns in LOCALITIES.items():
        if any(re.search(r"\b" + re.escape(s) + r"\b", t) for s in syns):
            locality = loc
            break
    near_me = bool(re.search(r"\bnear (me|my (home|house|place))\b|\bnearby\b", t))

    mode, mode_explicit = None, False
    if re.search(r"\b(tele|teleconsult\w*|online|video|virtual|remote)\b", t):
        mode, mode_explicit = "tele", True
    if re.search(r"\b(in[- ]person|physically|visit the hospital|in the clinic|offline)\b", t):
        mode, mode_explicit = "in_person", True
    in_person_only = bool(re.search(r"\b(only in[- ]person|in[- ]person only|no (tele|online|video))\b", t))

    doctor_name = None
    m = re.search(r"\bdr\.?\s+([a-z]+)(\s+[a-z]+)?", t)
    if m:
        doctor_name = (m.group(1) + (m.group(2) or "")).strip()
    usual = bool(re.search(r"\b(usual|regular|same|my|family)\s+(doctor|dr|physician|specialist)\b|\blast time\b", t)) and not doctor_name

    billing = bool(re.search(r"\b(cost|how much|fee|fees|price|charges?|insurance|cover(ed|age)?|kitna|paisa|bill)\b", t))
    booking_verbs = bool(re.search(r"\b(book|appointment|schedule|see a|see an|consult|visit|need a|need an|want a|want to see|dikhana|milna)\b", t))
    reschedule = bool(re.search(r"\b(reschedule|move my appointment|change my appointment|postpone)\b", t))
    cancel = bool(re.search(r"\bcancel\b.{0,25}\b(appointment|booking|visit)\b", t))

    specs = _find_specialties(t)
    unsupported = next((name for name, pat in UNSUPPORTED if re.search(pat, t)), None)
    rels = _find_relations(t)
    has_symptoms = bool(SYMPTOM_WORDS.search(t))

    coupling = {
        "same_day": bool(re.search(r"\bsame day\b|\bsame date\b|\bek hi din\b", t)),
        "back_to_back": bool(re.search(r"\bback[- ]to[- ]back\b|\bone after (the )?other\b|\bconsecutive\b|\btogether\b", t)),
        "same_hospital": "soft" if re.search(r"\bsame (hospital|place|clinic)\b", t) else None,
    }
    if coupling["same_hospital"] and not re.search(r"if possible|preferably|ideally", t):
        coupling["same_hospital"] = "soft"  # stay soft: never block a booking on it, but rank it first

    # goals: who is each appointment for?
    goals: list[dict] = []
    if len(specs) >= 2 or (len(specs) >= 1 and len(rels) >= 1 and re.search(r"\bfor me\b|\bmyself\b", t)):
        # associate each specialty with the nearest following "for me"/"for my X"
        for_me = [m.start() for m in re.finditer(r"\bfor me\b|\bmyself\b|\bmy own\b", t)]
        for i, (pos, spec) in enumerate(specs):
            nxt = specs[i + 1][0] if i + 1 < len(specs) else len(t)
            who = "self"
            cands = [(p, "self") for p in for_me if pos <= p < nxt] + [(p, r) for p, r in rels if pos <= p < nxt]
            if cands:
                who = sorted(cands)[0][1]
            goals.append({"who": who, "specialty": spec, "symptoms": None})
    else:
        who = "self"
        if rels:
            who = rels[0][1]
        goals.append({
            "who": who,
            "specialty": specs[0][1] if specs else None,
            "symptoms": raw.strip() if (has_symptoms and not specs) else None,
        })

    if cancel:
        intent = "cancel"
    elif reschedule:
        intent = "reschedule"
    elif billing and not (booking_verbs and (specs or has_symptoms)):
        intent = "billing"
    elif specs or has_symptoms or booking_verbs or usual or doctor_name:
        intent = "book"
    else:
        intent = "unknown"

    prefs_stated = []
    if re.search(r"\bi (prefer|like|usually want)\b.*\b(evening|morning|afternoon)", t):
        prefs_stated.append(f"Prefers {re.search(r'(evening|morning|afternoon)', t).group(1)} slots (stated by patient).")
    if re.search(r"\bi (prefer|like)\b.*\b(online|tele|video)", t):
        prefs_stated.append("Prefers teleconsultation (stated by patient).")

    return {
        "intent": intent,
        "goals": goals,
        "multi_goal": len(goals) > 1,
        "constraints": {
            "date_from": df, "date_to": dt, "date_text": dtext,
            "time_from": tf, "time_to": tt, "time_text": ttext,
            "locality": locality, "near_me": near_me,
            "mode": mode, "mode_explicit": mode_explicit, "in_person_only": in_person_only,
        },
        "doctor_name": doctor_name,
        "usual_doctor": usual,
        "coupling": coupling if len(goals) > 1 else None,
        "billing_question": billing,
        "has_symptoms": has_symptoms,
        "stated_preferences": prefs_stated,
        "unsupported": unsupported if not specs else None,
        "parser": "rule-based",
    }
