@echo off
REM Hospital Agent OS — Windows launcher.  run.bat [test|reset|cli]
cd /d %~dp0
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
if not exist .venv\deps-ok ( pip install -r requirements.txt && echo ok> .venv\deps-ok )
if not exist .env copy .env.example .env
if not exist models\triage_classifier.joblib python -m scripts.train_triage
if not exist data\hospital.db python -m scripts.seed
if "%1"=="test" ( python -m pytest -q && python -m scripts.run_scenarios & goto :eof )
if "%1"=="reset" ( python -m scripts.seed & goto :eof )
if "%1"=="cli" ( python -m backend.cli --patient P001 & goto :eof )
echo Hospital Agent OS on http://localhost:8000
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
