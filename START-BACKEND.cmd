@echo off
cd /d "%~dp0"
set LOG=%~dp0backend.log
echo [%date% %time%] START-BACKEND clicked > "%LOG%"
where python >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: python not found >> "%LOG%"
  echo [ERROR] Python not found. Install Python 3.10+, then double-click again.
  pause
  exit /b 1
)
python --version >> "%LOG%" 2>&1
python -c "import fastapi, uvicorn" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] Service deps missing, installing first-run requirements >> "%LOG%"
  echo First run: installing backend service deps, one moment...
  python -m pip install -r backend/requirements-service.txt >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo [%date% %time%] ERROR: pip install failed, see backend.log >> "%LOG%"
    echo [ERROR] Service deps failed to install. Tell Muse: BACKEND DEPS FAILED.
    pause
    exit /b 1
  )
)
python backend/tools/doctor.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: doctor failed, see backend.log >> "%LOG%"
  echo [ERROR] Backend self-check FAILED. The window below shows why.
  echo         Fix it, or paste backend.log to Muse.
  type "%LOG%"
  pause
  exit /b 1
)
echo [%date% %time%] Doctor PASS, starting uvicorn on 8000 >> "%LOG%"
echo API: http://127.0.0.1:8000  (raw JSON only, no page here)
echo Playground: open the site, then click Playground in the sidebar.
echo Keep this window OPEN while trying things out. Progress: backend.log
echo.
python -m uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000
echo [%date% %time%] Server exited with code %errorlevel% >> "%LOG%"
echo.
echo Server stopped. If the Playground says OFFLINE, tell Muse to read backend.log.
pause
