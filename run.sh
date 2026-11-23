#!/usr/bin/env bash
# Hospital Agent OS — one command to set up and run.
#   ./run.sh          set up (first time) + start backend serving the built UI on http://localhost:8000
#   ./run.sh dev      backend with reload + Vite dev server on http://localhost:5173
#   ./run.sh test     pytest + 18 scenario runs (writes submission/test_results.*)
#   ./run.sh reset    reseed demo data to the known state
#   ./run.sh shots    capture step-by-step screenshots (needs Playwright)
#   ./run.sh cli      interactive CLI (python -m backend.cli --patient P001)
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [ ! -d .venv ]; then
  echo "▶ creating virtualenv"; $PY -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
if [ ! -f .venv/.deps-ok ] || [ requirements.txt -nt .venv/.deps-ok ]; then
  echo "▶ installing Python dependencies"; pip install -q --upgrade pip && { pip install -q -r requirements.txt || { echo "▶ chromadb failed to install — using the built-in vector store fallback"; pip install -q -r requirements-core.txt; }; } && touch .venv/.deps-ok
fi
[ -f .env ] || cp .env.example .env
[ -f models/triage_classifier.joblib ] || { echo "▶ training triage classifier"; python -m scripts.train_triage; }
[ -f data/hospital.db ] || { echo "▶ seeding demo data"; python -m scripts.seed; }
case "${1:-run}" in
  dev)
    (cd frontend && [ -d node_modules ] || npm install)
    uvicorn backend.api.main:app --port 8000 --reload &
    trap 'kill %1' EXIT
    cd frontend && npm run dev ;;
  test)
    python -m pytest -q && python -m scripts.run_scenarios ;;
  reset)
    python -m scripts.seed ;;
  shots)
    python -m scripts.capture_screenshots --start-server ;;
  cli)
    shift; python -m backend.cli "$@" ;;
  build)
    cd frontend && npm install && npm run build ;;
  *)
    if [ ! -f frontend/dist/index.html ]; then (cd frontend && npm install && npm run build); fi
    echo "▶ Hospital Agent OS on http://localhost:${PORT:-8000}  (offline mode unless DEEPSEEK_API_KEY is set in .env)"
    exec uvicorn backend.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" ;;
esac
