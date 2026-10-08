@echo off
REM Night-shift tree: site on 5204 against backend 8012.
cd /d "%~dp0"
set LOG=%~dp0site-5204.log
echo [%date% %time%] START-SITE-5204 clicked > "%LOG%"
where node >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: Node.js not found >> "%LOG%"
  echo [ERROR] Node.js not found. Install Node.js 24 LTS, double-click again.
  pause
  exit /b 1
)
if not exist "site\.next\BUILD_ID" (
  echo [%date% %time%] ERROR: site\.next missing, production build not present >> "%LOG%"
  echo [ERROR] Production build missing. Tell Muse: BUILD MISSING.
  pause
  exit /b 1
)
set BACKEND_URL=http://127.0.0.1:8012
echo [%date% %time%] Preflight OK, starting next start on 5204 >> "%LOG%"
echo Serving: http://127.0.0.1:5204
echo Backend must run first: double-click START-BACKEND-8012.cmd.
echo Keep this window OPEN while reviewing. Progress: site-5204.log
echo.
call npm --prefix site run start -- --hostname 127.0.0.1 --port 5204
echo [%date% %time%] Server exited with code %errorlevel% >> "%LOG%"
pause
