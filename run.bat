@echo off
REM Hospital Agent OS - Windows launcher. Usage: run.bat  /  run.bat test  /  run.bat reset  /  run.bat cli
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM ---- Pick a normal CPython 3.11-3.13. The experimental free-threaded builds (3.13t) have no
REM ---- Windows wheels for scikit-learn/scipy, so pip would try to compile them and fail.
set "PY="
for %%V in (3.13 3.12 3.11) do (
  if not defined PY (
    py -%%V -c "import sys, sysconfig; sys.exit(1 if sysconfig.get_config_var('Py_GIL_DISABLED') else 0)" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys, sysconfig; ok = sys.version_info[:2] in ((3, 11), (3, 12), (3, 13)) and not sysconfig.get_config_var('Py_GIL_DISABLED'); sys.exit(0 if ok else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo ERROR: no suitable Python found. Only a free-threaded or unsupported Python is installed.
  echo Install Python 3.12 or 3.13 from python.org with the normal installer - NOT the free-threaded option -
  echo and tick "Add python.exe to PATH". Then run .\run.bat again.
  exit /b 1
)
echo Using Python: %PY%

REM ---- An old .venv made with a free-threaded or broken Python is removed and rebuilt.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys, sysconfig; sys.exit(1 if sysconfig.get_config_var('Py_GIL_DISABLED') else 0)" >nul 2>nul
  if errorlevel 1 (
    echo Existing .venv uses a free-threaded or broken Python - recreating it ...
    rmdir /s /q ".venv"
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment with %PY% ...
  %PY% -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: could not create .venv - see the message above.
  exit /b 1
)
call ".venv\Scripts\activate.bat"

if not exist ".venv\deps-ok" (
  echo [2/4] Installing Python packages - first run takes a few minutes ...
  python -m pip install --upgrade pip --retries 10 --timeout 60
  python -m pip install --prefer-binary --retries 10 --timeout 60 -r requirements.txt
  if errorlevel 1 (
    echo First install attempt failed - retrying once ...
    python -m pip install --prefer-binary --retries 10 --timeout 60 -r requirements.txt
  )
  if errorlevel 1 (
    echo Retrying without chromadb - the app then uses its built-in vector store ...
    python -m pip install --prefer-binary --retries 10 --timeout 60 -r requirements-core.txt
  )
  python -c "import fastapi, langgraph, sklearn, uvicorn, sqlalchemy" && echo ok> ".venv\deps-ok"
)
if not exist ".venv\deps-ok" (
  echo ERROR: package installation failed - scroll up for the pip error.
  echo If you see SSL or connection errors, your network is blocking PyPI downloads:
  echo switch to a mobile hotspot or pause antivirus HTTPS scanning, then run .\run.bat again.
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
