"""Seed the mock Hospital Information System.

Deterministic: fixed random seed + dates computed relative to TODAY (never hard-coded).
Demo fixtures are applied on top of the random data so every jury scenario behaves the same
way on any day. Run:  python -m scripts.seed      (or `reset_demo()` from code / the UI button)
"""
from __future__ import annotations

import csv
import os
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import DATA_DIR  # noqa: E402
from backend.db import models as M  # noqa: E402
from backend.db.session import engine, get_session, init_db  # noqa: E402

SEED = 42
N_DAYS = 14

HOSPITALS = [
    ("H01", "Kothrud Care Hospital", "Kothrud", "hospital", "Paud Road, Kothrud", "INS1,INS2,INS3"),
    ("H02", "Baner Lifeline Hospital", "Baner", "hospital", "Baner Road, Baner", "INS2,INS3"),
    ("H03", "Hadapsar Sunrise Hospital", "Hadapsar", "hospital", "Magarpatta Road, Hadapsar", "INS1,INS2,INS4"),
    ("H04", "Viman Nagar City Hospital", "Viman Nagar", "hospital", "Nagar Road, Viman Nagar", "INS2"),
    ("H05", "Shivajinagar General Hospital", "Shivajinagar", "hospital", "JM Road, Shivajinagar", "INS1,INS3,INS4"),
    ("H06", "Loni Kalbhor Community Clinic", "Loni Kalbhor", "clinic", "Solapur Highway, Loni Kalbhor", "INS1,INS4"),
]
LOCALITIES = ["Kothrud", "Baner", "Hadapsar", "Loni Kalbhor", "Viman Nagar", "Shivajinagar"]

SPECIALTIES = [
    "cardiology", "dermatology", "orthopedics", "neurology",
    "ent", "pediatrics", "general_medicine", "gastroenterology",
]

# id, name, specialty, hospital, tele_available
DOCTORS = [
    ("D01", "Dr. Anil Kulkarni", "cardiology", "H01", False),
    ("D02", "Dr. Sunita Rao", "cardiology", "H02", True),
    ("D03", "Dr. Vikram Shah", "cardiology", "H03", False),
    ("D04", "Dr. Farah Khan", "cardiology", "H04", True),
    ("D05", "Dr. Rajesh Iyer", "cardiology", "H05", False),
    ("D06", "Dr. Neha Joshi", "dermatology", "H02", True),
    ("D07", "Dr. Amit Deshmukh", "dermatology", "H01", False),
    ("D08", "Dr. Priya Nair", "dermatology", "H04", True),
    ("D09", "Dr. Kavita Patil", "dermatology", "H05", False),
    ("D10", "Dr. Sameer Gupta", "dermatology", "H03", True),
    ("D11", "Dr. Arjun Mehra", "orthopedics", "H01", False),
    ("D12", "Dr. Pooja Bhide", "orthopedics", "H02", False),
    ("D13", "Dr. Imran Shaikh", "orthopedics", "H03", True),
    ("D14", "Dr. Rohan Kapoor", "orthopedics", "H04", False),
    ("D15", "Dr. Swati Gokhale", "orthopedics", "H05", True),
    ("D16", "Dr. Meera Iyengar", "neurology", "H01", True),
    ("D17", "Dr. Harish Menon", "neurology", "H02", False),
    ("D18", "Dr. Nikhil Bose", "neurology", "H04", True),
    ("D19", "Dr. Anjali Verma", "neurology", "H05", False),
    ("D20", "Dr. Prakash Jadhav", "neurology", "H03", False),
    ("D21", "Dr. Sanjay Pawar", "ent", "H03", False),
    ("D22", "Dr. Ritu Malhotra", "ent", "H01", True),
    ("D23", "Dr. Kiran Shetty", "ent", "H02", False),
    ("D24", "Dr. Vandana Kulkarni", "ent", "H04", True),
    ("D25", "Dr. Ashok Bhosale", "ent", "H05", False),
    ("D26", "Dr. Shreya Apte", "pediatrics", "H01", False),
    ("D27", "Dr. Manoj Tiwari", "pediatrics", "H02", True),
    ("D28", "Dr. Leena Fernandes", "pediatrics", "H04", False),
    ("D29", "Dr. Gaurav Salunkhe", "pediatrics", "H06", True),
    ("D30", "Dr. Divya Reddy", "pediatrics", "H03", False),
    ("D31", "Dr. Suresh Patwardhan", "general_medicine", "H05", True),
    ("D32", "Dr. Asha More", "general_medicine", "H06", True),
    ("D33", "Dr. Rahul Chavan", "general_medicine", "H03", False),
    ("D34", "Dr. Zoya Mirza", "general_medicine", "H02", True),
    ("D35", "Dr. Vivek Sathe", "general_medicine", "H01", False),
    ("D36", "Dr. Ramesh Agarwal", "gastroenterology", "H04", True),
    ("D37", "Dr. Snehal Kale", "gastroenterology", "H01", False),
    ("D38", "Dr. Faisal Qureshi", "gastroenterology", "H03", False),
    ("D39", "Dr. Nandini Kher", "gastroenterology", "H05", True),
    ("D40", "Dr. Ajay Thakur", "gastroenterology", "H02", False),
]
FEE_RANGE = {
    "cardiology": (900, 1300), "dermatology": (600, 900), "orthopedics": (700, 1100),
    "neurology": (900, 1400), "ent": (500, 800), "pediatrics": (500, 800),
    "general_medicine": (300, 600), "gastroenterology": (800, 1200),
}
INSURANCE = [
    ("INS0", "Self-pay (no insurance)", 0, 0, 0, False, 0, "Patient pays the full consultation fee."),
    ("INS1", "MediShield Basic", 50, 0, 100, False, 10000, "50% OPD cover at network hospitals only; ₹100 copay; tele not covered."),
    ("INS2", "CarePlus Gold", 80, 50, 0, True, 25000, "80% in-network, 50% out-of-network; tele covered; no copay."),
    ("INS3", "Senior Care Plus", 70, 30, 200, True, 15000, "70% in-network, 30% out-of-network; ₹200 copay; tele covered."),
    ("INS4", "Govt Employee Health Scheme", 100, 0, 0, False, 50000, "100% at empanelled hospitals, nothing elsewhere."),
]
MORNING = ["09:30", "10:00", "10:30", "11:00", "11:30"]
EVENING = ["16:00", "16:30", "17:00", "17:30", "18:00"]

FIRST_M = ["Aarav", "Vihaan", "Rohit", "Siddharth", "Kunal", "Omkar", "Tejas", "Yash", "Pranav", "Nikhil",
           "Harsh", "Akash", "Sahil", "Varun", "Aditya", "Mihir", "Rahul", "Ketan", "Sachin", "Ajinkya"]
FIRST_F = ["Ananya", "Isha", "Priya", "Sneha", "Pooja", "Neha", "Rutuja", "Shruti", "Aditi", "Gauri",
           "Komal", "Rhea", "Tanvi", "Sayali", "Madhuri", "Kavya", "Asmita", "Prachi", "Nisha", "Meena"]
LAST = ["Sharma", "Patil", "Deshpande", "Kulkarni", "Joshi", "Shinde", "Pawar", "Jadhav", "Gaikwad", "More",
        "Kale", "Bhosale", "Naik", "Desai", "Mehta", "Khan", "Fernandes", "Iyer", "Rao", "Chavan"]
REASONS = {
    "cardiology": ["chest discomfort", "high blood pressure follow-up", "palpitations", "ECG review"],
    "dermatology": ["skin rash", "acne", "eczema flare", "hair fall"],
    "orthopedics": ["knee pain", "back pain", "shoulder stiffness", "ankle sprain"],
    "neurology": ["migraine", "numbness in hands", "dizziness", "sleep issues"],
    "ent": ["ear pain", "sinusitis", "sore throat", "hearing check"],
    "pediatrics": ["child fever", "vaccination", "child cough", "growth check"],
    "general_medicine": ["fever", "annual check-up", "diabetes review", "cold and cough"],
    "gastroenterology": ["acidity", "stomach pain", "indigestion", "IBS follow-up"],
}


def _t(hhmm: str, minutes: int) -> str:
    h, m = map(int, hhmm.split(":"))
    tot = h * 60 + m + minutes
    return f"{tot // 60:02d}:{tot % 60:02d}"


def reset_demo(today: date | None = None, verbose: bool = True, keep_registered: bool = True) -> dict:
    """Drop + recreate everything to the known demo state. Returns a summary dict."""
    rng = random.Random(SEED)
    today = today or date.today()
    days = [today + timedelta(days=i) for i in range(N_DAYS)]
    iso = [d.isoformat() for d in days]
    d1, d2, d3, d4 = iso[1], iso[2], iso[3], iso[4]
    next_monday = today + timedelta(days=7 - today.weekday())
    nm = (next_monday - today).days  # offset of next Monday (1..7)
    now = time.time()

    keep = _snapshot_registered() if keep_registered else {}
    init_db(drop=True)
    with get_session() as s:
        for h in HOSPITALS:
            s.add(M.Hospital(id=h[0], name=h[1], locality=h[2], kind=h[3], address=h[4], network_plans=h[5]))
        for p in INSURANCE:
            s.add(M.InsurancePlan(id=p[0], name=p[1], coverage_pct=p[2], out_of_network_pct=p[3], copay=p[4],
                                  tele_covered=p[5], annual_opd_limit=p[6], notes=p[7]))
        doc_rows = {}
        for did, name, spec, hid, tele in DOCTORS:
            lo, hi = FEE_RANGE[spec]
            fee = rng.randrange(lo, hi + 1, 50)
            langs = ["English", "Hindi"] + (["Marathi"] if rng.random() < 0.7 else [])
            d = M.Doctor(id=did, name=name, specialty=spec, hospital_id=hid, rating=round(rng.uniform(3.8, 4.9), 1),
                         fee=fee, tele_fee=int(round(fee * 0.7, -1)), experience_years=rng.randint(5, 28),
                         languages=",".join(langs), tele_available=tele, in_person=True)
            # fixed values used in the demo script
            if did == "D01":
                d.fee, d.tele_fee, d.rating = 1000, 700, 4.7
            if did == "D11":
                d.fee, d.tele_fee, d.rating = 900, 630, 4.8
            s.add(d)
            doc_rows[did] = d

        # ---------------- schedules ----------------
        # work[(doctor, day_index)] = set of sessions
        work: dict[tuple[str, int], set[str]] = {}
        for did, *_ in DOCTORS:
            working = rng.sample(range(N_DAYS), 8)
            for di in working:
                r = rng.random()
                work[(did, di)] = {"morning"} if r < 0.4 else {"evening"} if r < 0.75 else {"morning", "evening"}
        # forced working sessions for fixtures
        forced = {
            ("D06", 1): {"morning", "evening"},  # simple booking (derma Baner tomorrow morning) + multi-goal
            ("D02", 1): {"evening"},             # multi-goal cardiology at Baner
            ("D26", 1): {"morning"},             # time-window relaxation (pediatrics Kothrud)
            ("D21", 1): {"morning"},             # area relaxation (ENT Hadapsar full)
            ("D22", 1): {"morning", "evening"},  # ENT alternative elsewhere
            ("D36", 1): {"morning"},             # tele relaxation (gastro)
            ("D11", 2): {"evening"},             # clarification scenario (ortho d2 evening)
            ("D01", 2): {"morning"},             # doctor-cancels-block demo
            ("D01", 3): {"morning", "evening"},  # alternatives for the cancelled block
            ("D04", 2): {"morning", "evening"},  # tele alternative cardiology
            ("D11", nm + 1): {"evening"},        # memory: usual doctor next week
            ("D11", nm + 3): {"morning", "evening"},
            ("D19", 3): {"morning"},             # neurology alternative after waitlist window
        }
        work.update(forced)

        slot_rows: list[M.Slot] = []
        n = 0
        slot_index: dict[tuple[str, int, str], M.Slot] = {}
        for (did, di), sessions in sorted(work.items()):
            for sess in ("morning", "evening"):
                if sess not in sessions:
                    continue
                times = MORNING if sess == "morning" else EVENING
                for i, t in enumerate(times):
                    n += 1
                    tele = doc_rows[did].tele_available and i == len(times) - 1
                    sl = M.Slot(id=f"S{n:05d}", doctor_id=did, date=iso[di], start=t, end=_t(t, 30),
                                mode="tele" if tele else "in_person", status="free")
                    slot_rows.append(sl)
                    slot_index[(did, di, t)] = sl

        # random bookings (~40%, today busier)
        for sl in slot_rows:
            di = iso.index(sl.date)
            p = 0.6 if di == 0 else 0.4
            if rng.random() < p:
                sl.status = "booked"

        def setst(did, di, t, status):
            sl = slot_index.get((did, di, t))
            if sl:
                sl.status = status
            return sl

        # ---- fixtures ----
        for t in MORNING:  # D06 tomorrow morning: some free
            setst("D06", 1, t, "free")
        setst("D06", 1, "09:30", "booked")
        for t in ["09:30", "10:00", "10:30"]:
            setst("D26", 1, t, "booked")
        setst("D26", 1, "11:00", "free")
        setst("D26", 1, "11:30", "free")
        for t in MORNING:
            setst("D21", 1, t, "booked")
        for t in ["10:00", "10:30", "16:30"]:
            setst("D22", 1, t, "free")
        # gastro tomorrow: every in-person slot booked; D36 tele slot free
        for sl in slot_rows:
            if sl.date == d1 and doc_rows[sl.doctor_id].specialty == "gastroenterology":
                sl.status = "booked"
        setst("D36", 1, "11:30", "free")
        # neurology tomorrow + day after: everything booked -> waitlist scenario
        for sl in slot_rows:
            if sl.date in (d1, d2) and doc_rows[sl.doctor_id].specialty == "neurology":
                sl.status = "booked"
        for t in ["10:00", "11:00"]:
            setst("D19", 3, t, "free")
        # multi-goal: Baner tomorrow evening D02 16:00 + D06 16:30 free (back-to-back, same hospital)
        for t in ["16:00", "16:30", "17:00"]:
            setst("D02", 1, t, "free")
            setst("D06", 1, t, "free")
        # clarification: ortho day-after evening free
        for t in ["16:30", "17:00", "17:30"]:
            setst("D11", 2, t, "free")
        # memory: usual doctor next week evenings free
        for di in (nm + 1, nm + 3):
            for t in ["16:30", "17:30"]:
                setst("D11", di, t, "free")
        # cancel-block alternatives
        for t in MORNING + EVENING:
            setst("D01", 3, t, "free")
        setst("D01", 3, "09:30", "booked")
        setst("D04", 2, "11:30", "free")
        setst("D04", 2, "18:00", "free")
        s.add_all(slot_rows)

        # ---------------- patients ----------------
        patients = []
        special = {
            "P001": ("Aarav Sharma", 34, "M", "Kothrud", "INS2", "evening", "in_person", "D11", "English"),
            "P014": ("Sunita Sharma", 61, "F", "Kothrud", "INS3", "morning", "in_person", None, "Marathi"),
            "P023": ("Vikram Joshi", 45, "M", "Viman Nagar", "INS2", "evening", "tele", "D04", "English"),
            "P031": ("Meena Kulkarni", 52, "F", "Shivajinagar", "INS1", "morning", "in_person", "D19", "Marathi"),
        }
        for i in range(1, 101):
            pid = f"P{i:03d}"
            if pid in special:
                nm_, age, g, loc, ins, pt, pm, ud, lang = special[pid]
            else:
                g = rng.choice("MF")
                nm_ = f"{rng.choice(FIRST_M if g == 'M' else FIRST_F)} {rng.choice(LAST)}"
                age = rng.randint(3, 80)
                loc = rng.choice(LOCALITIES)
                ins = rng.choice(["INS0", "INS1", "INS2", "INS2", "INS3", "INS4"])
                pt = rng.choice(["morning", "evening", None])
                pm = rng.choice(["in_person", "in_person", "tele", None])
                ud = None
                lang = rng.choice(["English", "Hindi", "Marathi"])
            patients.append(M.Patient(id=pid, name=nm_, age=age, gender=g, phone=f"+91-98{rng.randint(10000000, 99999999)}",
                                      email=f"{nm_.split()[0].lower()}.{pid.lower()}@example.com", locality=loc,
                                      insurance_plan_id=ins, preferred_time=pt, preferred_mode=pm, usual_doctor_id=ud,
                                      language=lang))
        patients.append(M.Patient(id="GUEST", name="Guest Patient", age=30, gender="U", phone="+91-9000000000",
                                  email="guest@example.com", locality="", insurance_plan_id="INS0", preferred_time=None,
                                  preferred_mode=None, usual_doctor_id=None, language="English"))
        s.add_all(patients)
        pmap = {p.id: p for p in patients}

        # family links (relative is the patient's <relation>)
        links = [("P001", "P014", "mother"), ("P014", "P001", "son"), ("P023", "P024", "spouse"),
                 ("P024", "P023", "spouse"), ("P031", "P032", "son"), ("P032", "P031", "mother")]
        others = [p for p in pmap if p.startswith("P") and p not in ("P001", "P014", "P023", "P024", "P031", "P032")]
        for _ in range(18):
            a, b = rng.sample(others, 2)
            rel = rng.choice(["spouse", "child", "parent", "sibling"])
            inv = {"spouse": "spouse", "child": "parent", "parent": "child", "sibling": "sibling"}[rel]
            links += [(a, b, rel), (b, a, inv)]
        for a, b, r in links:
            s.add(M.FamilyLink(patient_id=a, relative_id=b, relation=r))

        # visit history (past)
        doc_by_spec: dict[str, list[str]] = {}
        for did, _, spec, *_ in DOCTORS:
            doc_by_spec.setdefault(spec, []).append(did)
        visits = []
        for p in patients:
            if p.id == "GUEST":
                continue
            for _ in range(rng.randint(0, 4)):
                spec = rng.choice(SPECIALTIES)
                did = rng.choice(doc_by_spec[spec])
                vd = (today - timedelta(days=rng.randint(15, 400))).isoformat()
                visits.append(M.Visit(patient_id=p.id, doctor_id=did, date=vd, specialty=spec,
                                      reason=rng.choice(REASONS[spec]), mode="in_person",
                                      slot_time=rng.choice(MORNING + EVENING)))
        for k, off in enumerate([300, 210, 120, 45]):
            visits.append(M.Visit(patient_id="P001", doctor_id="D11", date=(today - timedelta(days=off)).isoformat(),
                                  specialty="orthopedics", reason="knee pain" if k < 3 else "knee pain follow-up",
                                  mode="in_person", slot_time=rng.choice(EVENING)))
        visits.append(M.Visit(patient_id="P014", doctor_id="D35", date=(today - timedelta(days=60)).isoformat(),
                              specialty="general_medicine", reason="diabetes review", mode="in_person", slot_time="10:00"))
        visits.append(M.Visit(patient_id="P023", doctor_id="D04", date=(today - timedelta(days=90)).isoformat(),
                              specialty="cardiology", reason="high blood pressure follow-up", mode="tele", slot_time="18:00"))
        s.add_all(visits)

        # appointments for booked slots
        appt_n = 0
        def add_appt(sl, pid):
            nonlocal appt_n
            appt_n += 1
            s.add(M.Appointment(id=f"A{appt_n:04d}", patient_id=pid,
                                patient_name=pmap[pid].name if pid else f"Walk-in OPD #{appt_n}",
                                slot_id=sl.id, doctor_id=sl.doctor_id, status="booked",
                                created_at=now - rng.randint(3600, 86400 * 10),
                                reason=rng.choice(REASONS[doc_rows[sl.doctor_id].specialty])))

        cancel_fixture = {"09:30": None, "10:00": "P001", "10:30": "P014", "11:00": "P023"}
        setst("D01", 2, "11:30", "free")
        reg_pool = [p for p in pmap if p.startswith("P") and p not in ("P001", "P014", "P023", "P031")]
        for sl in slot_rows:
            if sl.status != "booked":
                continue
            if sl.doctor_id == "D01" and sl.date == d2 and sl.start in cancel_fixture:
                continue
            pid = rng.choice(reg_pool) if rng.random() < 0.15 else None
            add_appt(sl, pid)
        for t, pid in cancel_fixture.items():
            sl = setst("D01", 2, t, "booked")
            add_appt(sl, pid)

        # waitlist: P031 waiting for neurology over the next 3 days
        s.add(M.WaitlistEntry(id="W0001", patient_id="P031", specialty="neurology", doctor_id=None,
                              date_from=d1, date_to=d3, time_pref="morning", locality="Shivajinagar",
                              mode="any", status="waiting", created_at=now - 7200, run_id=None))

        # ---------------- memories ----------------
        mems = []
        def mem(pid, text, kind):
            mems.append(M.Memory(id=f"M{len(mems) + 1:05d}", patient_id=pid, text=text, kind=kind,
                                 source="seed", created_at=now - rng.randint(86400, 86400 * 200)))
        mem("P001", "Usual doctor: Dr. Arjun Mehra (Orthopedics, Kothrud Care Hospital, D11) — seen 4 times for knee pain.", "preference")
        mem("P001", "Prefers evening slots after 4 PM because of office hours.", "preference")
        mem("P001", "Prefers in-person consultations; lives in Kothrud.", "preference")
        mem("P001", "Mother Sunita Sharma (P014) is registered; P001 often books appointments for her.", "fact")
        mem("P014", "Prefers morning slots; avoids travelling in the evening.", "preference")
        mem("P014", "Prefers hospitals in or near Kothrud.", "preference")
        mem("P014", "Speaks Marathi; son Aarav (P001) usually accompanies her.", "fact")
        mem("P023", "Prefers teleconsultation — travels frequently for work.", "preference")
        mem("P023", "Usual cardiologist: Dr. Farah Khan (D04), follow-ups for blood pressure.", "preference")
        mem("P031", "Has recurring migraines; waiting for a neurology appointment, prefers mornings.", "fact")
        for v in visits:
            d = doc_rows[v.doctor_id]
            mem(v.patient_id, f"Visited {v.specialty.replace('_', ' ').title()} ({d.name}) on {v.date} at {v.slot_time} for {v.reason}.", "episode")
        for p in patients:
            if p.id in special or p.id == "GUEST":
                continue
            if p.preferred_time:
                mem(p.id, f"Prefers {p.preferred_time} slots.", "preference")
            if p.preferred_mode == "tele":
                mem(p.id, "Prefers teleconsultation when possible.", "preference")
        s.add_all(mems)

    _restore_registered(keep)
    # vector index
    from backend.core import vector_memory

    n_mem = vector_memory.rebuild_from_db()
    if "HOSPITAL_DB" not in os.environ:  # test/scenario databases don't overwrite the exported dataset
        export_csvs()
    summary = {
        "today": today.isoformat(),
        "hospitals": len(HOSPITALS), "doctors": len(DOCTORS), "slots": len(slot_rows),
        "free_slots": sum(1 for x in slot_rows if x.status == "free"),
        "patients": len(patients), "visits": len(visits), "memories": n_mem,
        "embedder": vector_memory.embedder_name(), "vector_store": vector_memory.store_backend(),
    }
    if verbose:
        print("Seeded:", summary)
    return summary


def _snapshot_registered() -> dict:
    """Patients created from the UI survive 'Reset demo' (their bookings are reset, their profile is not)."""
    try:
        with engine.connect() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(patients)").fetchall()]
            if "source" not in cols:
                return {}
            pats = [dict(r._mapping) for r in conn.exec_driver_sql("SELECT * FROM patients WHERE source='registered'").fetchall()]
            ids = [p["id"] for p in pats]
            if not ids:
                return {}
            q = ",".join("?" * len(ids))
            links = [dict(r._mapping) for r in conn.exec_driver_sql(
                f"SELECT patient_id, relative_id, relation FROM family_links WHERE patient_id IN ({q}) OR relative_id IN ({q})", tuple(ids + ids)).fetchall()]
            mems = [dict(r._mapping) for r in conn.exec_driver_sql(
                f"SELECT * FROM memories WHERE source='registration' AND patient_id IN ({q})", tuple(ids)).fetchall()]
        return {"patients": pats, "links": links, "memories": mems}
    except Exception:
        return {}


def _restore_registered(keep: dict) -> None:
    if not keep:
        return
    with get_session() as s:
        for p in keep["patients"]:
            s.add(M.Patient(**p))
        for l in keep["links"]:
            s.add(M.FamilyLink(**l))
        for m in keep["memories"]:
            s.add(M.Memory(**m))


def export_csvs() -> None:
    tables = ["hospitals", "doctors", "slots", "insurance_plans", "patients", "family_links", "visits",
              "appointments", "waitlist", "memories"]
    with engine.connect() as conn:
        for t in tables:
            res = conn.exec_driver_sql(f"SELECT * FROM {t}")
            cols = list(res.keys())
            with open(DATA_DIR / f"{t}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(res.fetchall())


if __name__ == "__main__":
    reset_demo()
