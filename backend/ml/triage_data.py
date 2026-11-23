"""Synthetic but realistic triage dataset: symptom sentence -> (specialty, urgency).

English + Hinglish, generated from templates with variation and noise (typos, fillers,
relations, durations). Each base phrase gets a `phrase_id` so we can also measure
generalisation to *unseen phrasings* (group split), not just template recall.
"""
from __future__ import annotations

import random

SYMPTOMS: dict[str, dict[str, list[str]]] = {
    "cardiology": {
        "routine": ["mild chest discomfort when climbing stairs", "high blood pressure readings at home",
                    "occasional palpitations", "need a heart check-up", "irregular heartbeat sometimes",
                    "swelling in my ankles in the evening", "high cholesterol report", "bp is high",
                    "need an ECG done", "heart murmur mentioned by my GP", "chest pain on and off for months",
                    "heart racing at night", "family history of heart disease, want check-up"],
        "soon": ["chest tightness when I walk fast", "palpitations with dizziness", "breathlessness while walking",
                 "very high bp like 180 by 110", "chest pain that comes and goes", "fluttering in chest and feeling faint"],
        "emergency": ["severe chest pain and sweating", "crushing chest pain spreading to the left arm",
                      "chest pain with sweating and breathlessness", "heart attack symptoms", "sudden severe chest pain",
                      "chest pain radiating to jaw with cold sweat"],
        "h_routine": ["seene mein halka dard", "bp high rehta hai", "dil ki dhadkan kabhi kabhi tez ho jati hai"],
        "h_soon": ["seene mein dard", "chalte waqt saans phoolti hai", "seene mein jakdan"],
        "h_emergency": ["seene mein bahut tez dard aur pasina", "dil ka daura jaisa lag raha hai",
                        "seene mein tez dard baayen haath tak"],
    },
    "dermatology": {
        "routine": ["itchy skin rash", "acne on my face", "dry patches on skin", "hair fall", "dandruff and scalp itching",
                    "dark spots on face", "eczema on my hands", "fungal infection between toes", "a mole that I want checked",
                    "pimples and oily skin", "white patches on skin", "itching all over the body", "skin allergy",
                    "nail fungus", "rash on my arm"],
        "soon": ["rash spreading quickly over my body", "painful boils on skin", "skin blisters that are oozing",
                 "red swollen skin that is warm", "hives all over after eating"],
        "h_routine": ["skin pe khujli", "chehre pe pimples", "baal bahut jhad rahe hain", "skin pe daane"],
        "h_soon": ["poore badan pe laal daane fail rahe hain", "skin pe phode ho gaye"],
    },
    "orthopedics": {
        "routine": ["knee pain", "lower back pain", "shoulder stiffness", "pain in my heel in the morning",
                    "neck pain from desk work", "joint pain in fingers", "ankle sprain from last week",
                    "knee pain while climbing stairs", "frozen shoulder", "back ache after lifting", "hip pain while walking", "sports injury to my knee",
                    "pain in my elbow", "stiff joints in the morning"],
        "soon": ["swollen knee after a fall", "cannot put weight on my ankle", "severe back pain going down my leg",
                 "wrist pain after falling, maybe fracture", "locked knee that won't straighten"],
        "emergency": ["bone sticking out after an accident", "fell from height and cannot move my leg",
                      "open fracture bleeding badly"],
        "h_routine": ["ghutne mein dard", "kamar dard", "kandhe mein dard", "joint mein dard rehta hai"],
        "h_soon": ["girne ke baad pair suj gaya", "kamar dard pair tak ja raha hai"],
    },
    "neurology": {
        "routine": ["migraine headaches", "frequent headaches", "tingling in my hands", "numbness in fingers",
                    "trouble sleeping and headaches", "mild memory problems", "dizziness on standing",
                    "tremor in my hands", "pins and needles in feet", "headache every evening", "forgetfulness",
                    "headache behind the eyes", "numbness in my leg"],
        "soon": ["worst migraine with vomiting", "headache with blurred vision", "repeated fainting spells",
                 "sudden numbness that went away", "severe headache for three days"],
        "emergency": ["face drooping and slurred speech", "sudden weakness on one side of the body", "having a seizure",
                      "stroke symptoms", "convulsions and not waking up", "sudden worst headache of my life"],
        "h_routine": ["sar dard rehta hai", "haath mein jhunjhuni", "chakkar aate hain", "neend nahi aati aur sar dard"],
        "h_soon": ["bahut tez sar dard aur ulti", "aankhon ke aage andhera aur sar dard"],
        "h_emergency": ["muh tedha ho gaya aur bolne mein dikkat", "lakwa maar gaya", "mirgi ka daura pad raha hai"],
    },
    "ent": {
        "routine": ["ear pain", "blocked nose", "sore throat", "hearing loss in one ear", "ringing in the ears",
                    "sinus pressure", "snoring problem", "ear wax blockage", "hoarse voice", "tonsil pain",
                    "itchy ears", "runny nose for weeks", "throat infection", "pain in the ear while swallowing"],
        "soon": ["ear discharge with fever", "severe throat pain cannot swallow", "nose bleeding again and again",
                 "sudden hearing loss", "swelling in the neck with sore throat"],
        "emergency": ["nose bleeding that will not stop", "throat swelling and difficulty breathing"],
        "h_routine": ["kaan mein dard", "naak band hai", "gale mein kharash", "kaan mein seeti bajti hai"],
        "h_soon": ["kaan se paani aa raha hai aur bukhar", "gala itna dukh raha hai ki nigal nahi pa raha"],
    },
    "pediatrics": {
        "routine": ["my child has a cough", "baby vaccination due", "my son has a mild fever", "growth check for my daughter",
                    "my child is not eating well", "toddler has a runny nose", "kid has a mild rash", "child bed wetting",
                    "baby has colic", "my kid has a cold", "my daughter has a fever", "my son keeps coughing at night",
                    "newborn check-up", "child has stomach ache"],
        "soon": ["my baby has high fever for two days", "child vomiting since morning", "toddler has ear pain and fever",
                 "my child has diarrhoea and is weak", "infant not feeding since last night"],
        "emergency": ["my baby is having fits", "child is unconscious", "baby is not breathing properly and turning blue",
                      "child had a convulsion with high fever"],
        "h_routine": ["bacche ko khansi hai", "bacche ko halka bukhar", "bacche ka teeka lagwana hai"],
        "h_soon": ["bacche ko do din se tez bukhar", "bachha subah se ulti kar raha hai"],
        "h_emergency": ["bacche ko jhatke aa rahe hain", "bachha behosh ho gaya"],
    },
    "general_medicine": {
        "routine": ["fever and body ache", "cold and cough", "annual health check-up", "diabetes follow-up",
                    "feeling tired all the time", "thyroid report review", "mild fever since yesterday",
                    "weakness and fatigue", "vitamin deficiency", "sugar levels are high", "body pain and chills",
                    "general check-up", "viral fever", "low energy and weight loss"],
        "soon": ["high fever with chills", "fever for five days", "dengue symptoms with body pain",
                 "very high sugar readings", "fever and severe weakness"],
        "emergency": ["unconscious and not responding", "heavy bleeding that won't stop", "took an overdose of pills",
                      "severe allergic reaction cannot breathe", "collapsed suddenly"],
        "h_routine": ["bukhar aur badan dard", "sardi khansi", "kamzori lagti hai", "sugar badh gayi hai"],
        "h_soon": ["paanch din se tez bukhar", "thand lagke bukhar aa raha hai"],
        "h_emergency": ["behosh ho gaye hain", "khoon ruk nahi raha", "saans nahi aa rahi"],
    },
    "gastroenterology": {
        "routine": ["acidity after meals", "stomach pain", "indigestion and bloating", "constipation",
                    "gas problem", "acid reflux at night", "loose motions on and off", "IBS follow-up", "heartburn",
                    "burning in stomach after food", "nausea after eating", "stomach ache since days", "bloated belly"],
        "soon": ["severe stomach pain on the right side", "yellow eyes and dark urine", "vomiting and stomach cramps",
                 "blood in stool", "persistent diarrhoea for a week"],
        "emergency": ["vomiting blood", "black tarry stool and fainting", "severe abdominal pain and rigid belly"],
        "h_routine": ["pet dard", "acidity ho rahi hai", "pet phoola rehta hai", "kabz ki problem"],
        "h_soon": ["pet mein tez dard aur ulti", "aankhen peeli ho gayi hain"],
        "h_emergency": ["khoon ki ulti", "pet mein bahut tez dard, pet sakht ho gaya"],
    },
}

AMBIGUOUS = [
    ("neurology", "routine", "dizziness and ringing in ears"), ("ent", "routine", "dizziness and ringing in ears"),
    ("pediatrics", "routine", "my child has a skin rash"), ("dermatology", "routine", "my child has a skin rash"),
    ("gastroenterology", "routine", "burning in chest after meals"), ("cardiology", "routine", "burning in chest after meals"),
    ("general_medicine", "routine", "headache and fever"), ("neurology", "routine", "headache and fever"),
    ("orthopedics", "routine", "neck pain with headache"), ("neurology", "routine", "neck pain with headache"),
    ("general_medicine", "soon", "fever with vomiting"), ("gastroenterology", "soon", "fever with vomiting"),
    ("pediatrics", "routine", "my son has stomach pain"), ("gastroenterology", "routine", "my son has stomach pain"),
    ("cardiology", "soon", "breathless and tired"), ("general_medicine", "soon", "breathless and tired"),
]
for _sp, _u, _ph in AMBIGUOUS:
    SYMPTOMS[_sp].setdefault("amb_" + _u, []).append(_ph)

SYN = {
    "pain": ["ache", "discomfort", "pain", "hurting"], "child": ["kid", "child", "little one"],
    "fever": ["fever", "temperature", "high temperature"], "stomach": ["stomach", "tummy", "belly", "abdomen"],
    "severe": ["severe", "very bad", "intense", "terrible"], "mild": ["mild", "slight", "little"],
    "vomiting": ["vomiting", "throwing up"], "breathlessness": ["breathlessness", "shortness of breath"],
    "dizziness": ["dizziness", "giddiness", "vertigo"], "headache": ["headache", "head pain"],
    "headaches": ["headaches", "head pains"], "itchy": ["itchy", "itching"], "son": ["son", "boy"],
    "daughter": ["daughter", "girl"], "baby": ["baby", "infant"], "sudden": ["sudden", "abrupt"],
}

EN_TEMPLATES = [
    "{s}", "I have {s}", "I have been having {s} {dur}", "{s} {dur}, need to see a doctor",
    "my {rel} has {s}", "suffering from {s} {dur}", "need an appointment for {s}", "{s}. please help",
    "experiencing {s} {dur}", "book a doctor, I have {s}", "{s} {dur}", "I want to consult someone for {s}",
]
EN_TEMPLATES_PED = [
    "{s}", "{s} {dur}", "need a doctor, {s}", "{s}. please help", "{s} {dur}, what should I do",
]
H_TEMPLATES = ["{s} hai", "mujhe {s} hai {dur}", "{s} ho raha hai", "mere {rel} ko {s} hai",
               "{dur} {s} hai, doctor chahiye", "{s} {dur}", "doctor ko dikhana hai, {s}"]
DUR_EN = ["since yesterday", "for 2 days", "for a week", "for a month", "since morning", "for the past few weeks",
          "since last night", "for 3 days", ""]
DUR_H = ["kal se", "2 din se", "ek hafte se", "subah se", "kaafi dino se", ""]
REL_EN = ["father", "mother", "wife", "husband", "grandmother", "brother", "sister"]
REL_H = ["papa", "mummy", "dadi", "bhai", "behen", "pati", "patni"]
FILLERS = ["", "", "", "please", "kindly", "hi,", "hello,", "doctor,"]

URG = {"routine": "routine", "soon": "soon", "emergency": "emergency",
       "h_routine": "routine", "h_soon": "soon", "h_emergency": "emergency",
       "amb_routine": "routine", "amb_soon": "soon"}


def _syn(rng: random.Random, ph: str) -> str:
    out = []
    for w in ph.split():
        alts = SYN.get(w)
        out.append(rng.choice(alts) if alts and rng.random() < 0.5 else w)
    return " ".join(out)
PER_CLASS = {"routine": 7, "soon": 7, "emergency": 7, "h_routine": 7, "h_soon": 7, "h_emergency": 7}


def _typo(rng: random.Random, s: str) -> str:
    if len(s) < 6:
        return s
    i = rng.randrange(1, len(s) - 2)
    return s[:i] + s[i + 1] + s[i] + s[i + 2:]


def generate(seed: int = 7, target: int = 2800) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    seen: set[str] = set()
    pid = 0
    phrase_ids: dict[tuple[str, str], int] = {}
    pool = []
    for spec, groups in SYMPTOMS.items():
        for g, phrases in groups.items():
            for ph in phrases:
                phrase_ids[(spec, ph)] = pid
                pid += 1
                pool.append((spec, g, ph))
    attempts = 0
    while len(rows) < target and attempts < target * 20:
        attempts += 1
        spec, g, ph = rng.choice(pool)
        hing = g.startswith("h_")
        if hing:
            tpl = rng.choice(H_TEMPLATES)
            text = tpl.format(s=ph, dur=rng.choice(DUR_H), rel=rng.choice(REL_H))
        else:
            tpls = EN_TEMPLATES_PED if spec == "pediatrics" else EN_TEMPLATES
            tpl = rng.choice(tpls)
            text = tpl.format(s=_syn(rng, ph), dur=rng.choice(DUR_EN), rel=rng.choice(REL_EN))
        f = rng.choice(FILLERS)
        if f:
            text = f"{f} {text}"
        if rng.random() < 0.08:
            text = _typo(rng, text)
        if rng.random() < 0.3:
            text = text.lower()
        text = " ".join(text.split())
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"text": text, "specialty": spec, "urgency": URG[g], "language": "hinglish" if hing else "english",
                     "phrase_id": phrase_ids[(spec, ph)]})
    return rows
