@echo off
cd /d "%~dp0"
set LOG=%~dp0dev.log
echo [%date% %time%] START-DEV clicked > "%LOG%"
where node >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: Node.js not found >> "%LOG%"
  echo [ERROR] Node.js not found. Install Node.js 24 LTS, then double-click again.
  pause
  exit /b 1
)
node --version >> "%LOG%" 2>&1
if not exist "site\node_modules" (
  echo [%date% %time%] Installing site dependencies >> "%LOG%"
  echo Installing dependencies - one-time, takes a few minutes...
  call npm --prefix site ci >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo [%date% %time%] ERROR: npm ci failed >> "%LOG%"
    echo [ERROR] Install failed. Check internet and try again.
    pause
    exit /b 1
  )
)
echo [%date% %time%] Preflight OK, starting next dev on 5194 >> "%LOG%"
echo Dev server: http://127.0.0.1:5194
echo Keep this window OPEN. Hot reload is on: file edits appear live.
echo Progress is logged to dev.log
echo.
call npm --prefix site run dev -- --hostname 127.0.0.1 --port 5194
echo [%date% %time%] Server exited with code %errorlevel% >> "%LOG%"
echo.
echo Server stopped. If the page never loaded, tell Muse to read dev.log.
pause
