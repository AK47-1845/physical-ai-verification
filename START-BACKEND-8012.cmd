@echo off
REM Night-shift tree: backend on 8012 with the project venv.
cd /d "%~dp0"
set LOG=%~dp0backend-8012.log
echo [%date% %time%] START-BACKEND-8012 clicked > "%LOG%"
if not exist ".venv\Scripts\python.exe" (
  echo [%date% %time%] ERROR: .venv missing >> "%LOG%"
  echo [ERROR] Project venv missing. Tell Muse: VENV MISSING.
  pause
  exit /b 1
)
set VV_RATE_LIMIT=600
".venv\Scripts\python.exe" backend/tools/doctor.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: doctor failed, see backend-8012.log >> "%LOG%"
  echo [ERROR] Backend self-check FAILED. Paste backend-8012.log to Muse.
  pause
  exit /b 1
)
echo [%date% %time%] Doctor PASS, starting uvicorn on 8012 >> "%LOG%"
echo API: http://127.0.0.1:8012  - health at /healthz, docs at /docs
echo Keep this window OPEN while using the site. Progress: backend-8012.log
echo.
".venv\Scripts\python.exe" -m uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8012
echo [%date% %time%] Server exited with code %errorlevel% >> "%LOG%"
pause
