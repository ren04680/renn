import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEMO_OFFLINE", "1")


@pytest.fixture(scope="session", autouse=True)
def _model():
    from backend.config import TRIAGE_MODEL_PATH

    if not TRIAGE_MODEL_PATH.exists():
        from scripts.train_triage import main

        main()


@pytest.fixture()
def fresh():
    """Reset the demo DB to its known state."""
    from backend.config import settings
    from scripts.seed import reset_demo

    reset_demo(verbose=False)
    settings.update(inject_fault=False, offline=True)
    yield


@pytest.fixture()
def ctx_factory():
    import uuid

    from backend.core.context import new_context

    def make(patient="P001"):
        return new_context("t-" + uuid.uuid4().hex[:8], patient)

    return make
