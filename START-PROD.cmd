@echo off
cd /d "%~dp0"
set LOG=%~dp0server.log
echo [%date% %time%] START-PROD clicked > "%LOG%"
where node >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: Node.js not found >> "%LOG%"
  echo [ERROR] Node.js not found. Install Node.js 24 LTS, then double-click again.
  pause
  exit /b 1
)
node --version >> "%LOG%" 2>&1
if not exist "site\.next\BUILD_ID" (
  echo [%date% %time%] ERROR: site\.next missing, production build not present >> "%LOG%"
  echo [ERROR] Production build missing. Tell Muse: BUILD MISSING.
  pause
  exit /b 1
)
echo [%date% %time%] Preflight OK, starting next start on 5193 >> "%LOG%"
echo Serving: http://127.0.0.1:5193
echo Keep this window OPEN while reviewing. Progress is logged to server.log
echo.
call npm --prefix site run start -- --hostname 127.0.0.1 --port 5193
echo [%date% %time%] Server exited with code %errorlevel% >> "%LOG%"
echo.
echo Server stopped. If the page never loaded, tell Muse to read server.log.
pause
