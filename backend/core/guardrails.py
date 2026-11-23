"""Non-negotiable safety guardrails.

1. emergency_screen — a HARD RULE (regex, English + Hinglish) that runs first on every user message.
   No agent and no model can override it. (The ML classifier can only *add* emergencies, never remove.)
"""
from __future__ import annotations

import re

_EMERGENCY_PATTERNS: list[tuple[str, str]] = [
    ("cardiac", r"(severe|crushing|sudden|intense|terrible|bad)\s+(chest|heart)\s+pain"),
    ("cardiac", r"chest\s+pain.{0,40}(sweat|radiat|left\s+arm|jaw|breathless|short(ness)?\s+of\s+breath|faint)"),
    ("cardiac", r"(sweat|sweating).{0,30}chest\s+pain"),
    ("cardiac", r"heart\s+attack"),
    ("cardiac", r"seene\s+(mein|me)\s+(bahut|tez|zor|bohot)"),
    ("cardiac", r"seene.{0,25}(pasina|paseena)"),
    ("cardiac", r"dil\s+ka\s+daura"),
    ("breathing", r"(can'?t|cannot|can\s+not|unable\s+to|not\s+able\s+to)\s+breathe"),
    ("breathing", r"(not|stopped)\s+breathing|choking|turning\s+blue|gasping"),
    ("breathing", r"saans\s+(nahi|nahin)\s+(aa|le)"),
    ("neuro", r"(face\s+droop|facial\s+droop|slurred\s+speech|one\s+side\s+(of\s+the\s+body\s+)?(is\s+)?weak|sudden\s+weakness|stroke)"),
    ("neuro", r"(seizure|convulsion|having\s+fits|jhatke|mirgi)"),
    ("neuro", r"(unconscious|unresponsive|not\s+responding|passed\s+out|collapsed|behosh)"),
    ("neuro", r"worst\s+headache\s+of\s+my\s+life"),
    ("neuro", r"lakwa|muh\s+tedha"),
    ("bleeding", r"(heavy|severe|profuse)\s+bleeding|bleeding.{0,20}(won'?t|will\s+not|doesn'?t|not)\s+stop|khoon\s+ruk"),
    ("bleeding", r"vomiting\s+blood|blood\s+in\s+vomit|khoon\s+ki\s+ulti|coughing\s+(up\s+)?blood"),
    ("trauma", r"bone\s+sticking\s+out|open\s+fracture|(serious|major)\s+accident|head\s+injury"),
    ("mental_health", r"(suicid|kill\s+myself|end\s+my\s+life|self[-\s]?harm|overdose|took\s+too\s+many\s+pills)"),
    ("poisoning", r"(poison|swallowed\s+(bleach|acid|chemical))"),
    ("allergy", r"(throat|tongue|face)\s+(is\s+)?swell\w*.{0,30}(breath|breathe)|anaphyla"),
]
_NEGATIONS = re.compile(r"\b(no|not|without|never|denies)\s+(\w+\s+){0,2}$")

ESCALATION_MESSAGE = (
    "⚠️ This sounds like a medical emergency. I will not book a routine appointment for this.\n"
    "• Call **108** (ambulance) or **112** now, or go to the nearest Emergency Room immediately.\n"
    "• Nearest 24×7 ERs: Kothrud Care Hospital (Paud Road), Shivajinagar General Hospital (JM Road).\n"
    "• If someone is with you, ask them to stay with you. Do not drive yourself.\n"
    "I have alerted the hospital's emergency desk and logged this conversation."
)


def emergency_screen(text: str) -> dict:
    t = " " + (text or "").lower() + " "
    hits = []
    for cat, pat in _EMERGENCY_PATTERNS:
        for m in re.finditer(pat, t):
            prefix = t[max(0, m.start() - 25): m.start()]
            if _NEGATIONS.search(prefix):
                continue
            hits.append({"category": cat, "match": m.group(0).strip()})
            break
    return {
        "emergency": bool(hits),
        "matches": hits,
        "category": hits[0]["category"] if hits else None,
        "rule": "hard-rule regex (EN + Hinglish); cannot be overridden",
    }
