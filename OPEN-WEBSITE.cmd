@echo off
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 24 LTS first, then run this file again.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:5192"
node tools\preview.mjs
pause