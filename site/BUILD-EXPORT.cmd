@echo off
REM BUILD-EXPORT.cmd - one double-click static export for free hosting.
REM Builds the site into .next-transfer\ (drag that folder to Cloudflare
REM Pages or Netlify Drop). Restores src\app\api + build dirs afterwards.
REM Stop the site server window first: the live .next\ dir moves aside
REM during the build and comes back untouched when it finishes.
cd /d "%~dp0"
if exist src\app-api-bak (
  echo [fix] leftover api backup from an interrupted run - restoring first.
  if not exist src\app\api move src\app-api-bak src\app\api >nul
)
if exist .next-bak (
  echo [fix] leftover .next backup from an interrupted run - restoring first.
  if not exist .next move .next-bak .next >nul
)
if exist .next-astra-bak (
  if not exist .next-astra move .next-astra-bak .next-astra >nul
)
if exist .next-transfer-bak (
  if not exist .next-transfer move .next-transfer-bak .next-transfer >nul
)
echo [1/4] Moving src\app\api aside (static export can't host API routes)...
move src\app\api src\app-api-bak >nul
if errorlevel 1 (
  echo FAILED to move api dir. Nothing was changed. Press any key.
  pause >nul
  exit /b 1
)
echo [2/4] Moving stale build dirs aside (their cached types break export)...
if exist .next move .next .next-bak >nul
if exist .next-astra move .next-astra .next-astra-bak >nul
if exist .next-transfer move .next-transfer .next-transfer-bak >nul
echo [3/4] Building static export...
set VERIFICATION_STATIC_EXPORT=1
call npm run build
set BUILD_ERR=%ERRORLEVEL%
set VERIFICATION_STATIC_EXPORT=
echo [4/4] Restoring moved dirs...
if exist src\app-api-bak move src\app-api-bak src\app\api >nul
if exist .next-bak move .next-bak .next >nul
if exist .next-astra-bak move .next-astra-bak .next-astra >nul
if exist .next-transfer-bak rmdir /s /q .next-transfer-bak
if not "%BUILD_ERR%"=="0" (
  echo.
  echo BUILD FAILED with errors above. All moved dirs were restored safely.
  echo Paste the errors to your coding assistant to fix, then re-run.
  pause
  exit /b 1
)
echo.
echo DONE. Upload the folder below (drag-drop, free, no card):
echo   %CD%\.next-transfer
echo See DEPLOY_FREE.md for the 2-minute upload steps.
pause
