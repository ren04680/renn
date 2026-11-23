@echo off
REM Hospital Agent OS - Windows launcher. Usage: run.bat  /  run.bat test  /  run.bat reset  /  run.bat cli
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM Prefer the "py" launcher: on many PCs "python" opens the Microsoft Store instead of Python.
set "PY=python"
where py >nul 2>nul && set "PY=py -3"

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment with %PY% ...
  %PY% -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: could not create .venv. Install Python 3.11-3.13 from python.org and tick "Add to PATH".
  exit /b 1
)
call ".venv\Scripts\activate.bat"

if not exist ".venv\deps-ok" (
  echo [2/4] Installing Python packages - first run takes a few minutes ...
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo chromadb failed to install - using the built-in vector store instead.
    python -m pip install -r requirements-core.txt
  )
  python -c "import fastapi, langgraph, sklearn, uvicorn, sqlalchemy" && echo ok> ".venv\deps-ok"
)
if not exist ".venv\deps-ok" (
  echo ERROR: package installation failed - scroll up for the pip error.
  exit /b 1
)

if not exist ".env" copy ".env.example" ".env" >nul
if not exist "models\triage_classifier.joblib" (
  echo [3/4] Training triage classifier ...
  python -m scripts.train_triage
)
if not exist "data\hospital.db" (
  echo [3/4] Seeding demo data ...
  python -m scripts.seed
)

if /i "%~1"=="test" (
  python -m pytest -q
  python -m scripts.run_scenarios
  goto :eof
)
if /i "%~1"=="reset" (
  python -m scripts.seed
  goto :eof
)
if /i "%~1"=="cli" (
  python -m backend.cli --patient P001
  goto :eof
)

echo [4/4] Hospital Agent OS starting - open http://localhost:8000 in Chrome  (Ctrl+C to stop)
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
