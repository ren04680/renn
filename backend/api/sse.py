"""SSE endpoint lives in `main.py` (`GET /api/stream`): it tails the in-memory trace bus with a
cursor (Last-Event-ID aware) and streams every agent event to the UI. Re-exported for layout parity."""
from backend.api.main import stream  # noqa: F401
