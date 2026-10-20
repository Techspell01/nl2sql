@echo off
rem Starts Argus and opens it in your browser. Double-click this file, or run: start.bat
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The virtual environment is missing. See README: Setup.
  pause
  exit /b 1
)
if not exist "data\warehouse.duckdb" (
  echo No warehouse yet - building it from data\raw ...
  ".venv\Scripts\python.exe" scripts\build_warehouse.py
  if errorlevel 1 (
    echo Build failed. Put the Olist CSVs in data\raw, or run: .venv\Scripts\python scripts\build_warehouse.py --sample
    pause
    exit /b 1
  )
)
echo Starting on http://127.0.0.1:8000  (press Ctrl+C here to stop)
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn nl2sql.api:app --host 127.0.0.1 --port 8000
