"""Central configuration + runtime-mutable demo settings."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
LOGS_DIR = ROOT / "logs"
SUBMISSION_DIR = ROOT / "submission"
DB_PATH = Path(os.getenv("HOSPITAL_DB", str(DATA_DIR / "hospital.db")))
CHROMA_DIR = DATA_DIR / "chroma"
TRIAGE_MODEL_PATH = MODELS_DIR / "triage_classifier.joblib"

for _d in (DATA_DIR, MODELS_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "25"))
HOLD_TTL_SECONDS = int(os.getenv("HOLD_TTL_SECONDS", "300"))
PROACTIVE_HOLD_TTL_SECONDS = int(os.getenv("PROACTIVE_HOLD_TTL_SECONDS", "900"))
EMBEDDINGS = os.getenv("EMBEDDINGS", "auto")

# Hard limits (guardrail #5)
MAX_TOOL_CALLS_PER_AGENT = 15
MAX_CRITIC_LOOPS = 2
MAX_RELAXATIONS = 4
MAX_CLARIFY_ROUNDS = 2
RUN_TIMEOUT_SECONDS = float(os.getenv("RUN_TIMEOUT_SECONDS", "150"))

PRINCIPLE = "Free to think, gated to act. The agent is permitted to fail — never to invent."


class RuntimeSettings:
    """Settings the UI can flip at runtime (inject fault, offline mode)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.inject_fault = False
        self.force_offline = os.getenv("DEMO_OFFLINE", "0").strip() in ("1", "true", "yes")

    @property
    def offline(self) -> bool:
        return self.force_offline or not DEEPSEEK_API_KEY

    @property
    def offline_reason(self) -> str:
        if self.force_offline:
            return "DEMO_OFFLINE=1"
        if not DEEPSEEK_API_KEY:
            return "no DEEPSEEK_API_KEY"
        return ""

    def update(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                if v is None:
                    continue
                if k == "offline":
                    self.force_offline = bool(v)
                elif hasattr(self, k):
                    setattr(self, k, v)

    def as_dict(self) -> dict:
        return {
            "inject_fault": self.inject_fault,
            "offline": self.offline,
            "offline_forced": self.force_offline,
            "offline_reason": self.offline_reason,
            "llm_available": bool(DEEPSEEK_API_KEY),
            "model": DEEPSEEK_MODEL,
        }


settings = RuntimeSettings()
