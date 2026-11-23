"""Patients registered from the UI: created on the fly, remembered, linkable to family, survive Reset demo."""
from fastapi.testclient import TestClient


def test_register_use_and_survive_reset(fresh):
    from backend.api.main import app

    with TestClient(app) as cl:
        listed = [p["id"] for p in cl.get("/api/patients").json()]
        assert listed == ["P001", "P014", "P023", "P031", "GUEST"]  # the 100 seeded patients are not listed
        assert len(cl.get("/api/patients?all=1").json()) == 101       # ...but remain in the dataset
        r = cl.post("/api/patients", json={"name": "Riya Kapoor", "age": 29, "gender": "F", "locality": "Baner",
                                           "insurance_plan_id": "INS2", "preferred_time": "morning"}).json()
        assert r["id"] == "P101" and r["memories"] >= 2
        m = cl.post("/api/patients", json={"name": "Asha Kapoor", "age": 58, "gender": "F", "locality": "Baner",
                                           "insurance_plan_id": "INS3", "family": {"patient_id": "P101", "relation": "mother"}}).json()
        assert m["id"] == "P102"
        assert cl.post("/api/patients", json={"name": "x", "age": 500}).status_code == 422
        # registration details are used as memory: only the day is asked
        c = cl.post("/api/chat", json={"patient_id": "P101", "message": "looking for a skin doctor", "run_id": "rg1"}).json()
        q = c["interrupt"]["question"]
        assert "Which day" in q and "What time" not in q and "morning" in q and "Baner" in q
        c = cl.post("/api/resume", json={"run_id": "rg1", "value": {"text": "tomorrow"}}).json()
        item = c["interrupt"]["proposal"]["items"][0]
        assert item["patient_id"] == "P101" and item["start"] < "12:00"
        # family link: "my mother" resolves to the newly registered P102
        c = cl.post("/api/chat", json={"patient_id": "P101", "message": "book a cardiologist for my mother tomorrow evening", "run_id": "rg2"}).json()
        assert c["interrupt"]["proposal"]["items"][0]["patient_id"] == "P102"
        cl.post("/api/reset", json={})
        assert [p["id"] for p in cl.get("/api/patients").json()][-2:] == ["P101", "P102"]
        prof = cl.post("/api/chat", json={"patient_id": "P102", "message": "book a doctor for my son", "run_id": "rg3"}).json()
        assert prof["status"] in ("waiting", "done")  # 'son' matches the generic 'child' link after reset
