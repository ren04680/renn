"""API smoke tests + the full scenario suite (the jury evidence) as a pytest."""
from datetime import date, timedelta

from fastapi.testclient import TestClient


def test_api_chat_resume_and_ops(fresh):
    from backend.api.main import app

    with TestClient(app) as cl:
        assert cl.get("/api/health").json()["ok"]
        r = cl.post("/api/chat", json={"patient_id": "P001", "message": "Book with my usual doctor next week", "run_id": "apitest1"}).json()
        assert r["status"] == "waiting" and r["interrupt"]["kind"] == "approval"
        assert r["interrupt"]["proposal"]["items"][0]["doctor_id"] == "D11"
        r = cl.post("/api/resume", json={"run_id": "apitest1", "value": {"approved": True}}).json()
        assert r["response"]["kind"] == "booked"
        bb = cl.get("/api/runs/apitest1/blackboard").json()
        assert bb["goal"] and len(bb["subtasks"]) >= 8 and bb["critic_verdicts"][0]["verdict"] == "APPROVE"
        d2 = (date.today() + timedelta(days=2)).isoformat()
        sched = cl.get(f"/api/ops/schedule?day={d2}&specialty=cardiology").json()
        assert any(d["doctor_id"] == "D01" for d in sched["doctors"])
        assert cl.get("/api/metrics").status_code == 200
        assert len(cl.get("/api/runs/apitest1/events").json()) > 20


def test_all_scenarios_pass(fresh):
    from scripts.run_scenarios import run

    rows = run()
    failed = [(r["id"], [c["check"] for c in r["checks"] if not c["pass"]]) for r in rows if not r["pass"]]
    assert not failed, failed
    assert len(rows) >= 14
