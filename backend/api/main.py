"""FastAPI app: REST + Server-Sent Events (live agent trace) + serves the built React UI.

Run:  uvicorn backend.api.main:app --port 8000
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from backend.api.routes import router
from backend.config import DB_PATH, MODELS_DIR, ROOT, TRIAGE_MODEL_PATH
from backend.core.events import event_bus
from backend.core.trace import bus

DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not TRIAGE_MODEL_PATH.exists():
        from scripts.train_triage import main as train

        await asyncio.to_thread(train)
    from scripts.seed import reset_demo

    if not DB_PATH.exists() or not _schema_ok() or _seeded_for() != date.today().isoformat():
        # demo fixtures are relative to "today": reseed when the calendar day changed (jury-day safety)
        await asyncio.to_thread(reset_demo)
    from backend.core import vector_memory
    from backend.core.graph import get_graph

    await asyncio.to_thread(vector_memory.ensure_index)
    get_graph()
    await event_bus.start()
    yield


app = FastAPI(title="Hospital Agent OS", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")


@app.get("/api/stream")
async def stream(request: Request, since: int = 0):
    last = request.headers.get("last-event-id")
    cursor = int(last) if last and last.isdigit() else since

    async def gen():
        nonlocal cursor
        idle = 0
        while True:
            if await request.is_disconnected():
                break
            evs = bus.since(cursor, limit=400)
            if evs:
                for e in evs:
                    cursor = e["seq"]
                    yield {"id": str(e["seq"]), "event": "trace", "data": json.dumps(e, ensure_ascii=False, default=str)}
                idle = 0
            else:
                idle += 1
                if idle % 60 == 0:
                    yield {"event": "ping", "data": str(cursor)}
                await asyncio.sleep(0.12)

    return EventSourceResponse(gen())


@app.get("/models/{name}")
def model_file(name: str):
    p = MODELS_DIR / name
    if p.exists() and p.suffix in (".png", ".json"):
        return FileResponse(p)
    return JSONResponse({"error": "not found"}, status_code=404)


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        f = DIST / full_path
        if full_path and f.exists() and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    def root():
        return {"message": "API running. Build the UI with `cd frontend && npm install && npm run build`.",
                "docs": "/docs"}


def _schema_ok() -> bool:
    """An older database (e.g. from before a model change) is rebuilt instead of crashing."""
    try:
        from backend.db.models import Base
        from backend.db.session import engine

        with engine.connect() as conn:
            for t in Base.metadata.sorted_tables:
                have = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({t.name})").fetchall()}
                if not {c.name for c in t.columns} <= have:
                    return False
        return True
    except Exception:
        return False


def _seeded_for() -> str | None:
    try:
        from backend.db.session import engine

        with engine.connect() as conn:
            return conn.exec_driver_sql("SELECT MIN(date) FROM slots").scalar()
    except Exception:
        return None
