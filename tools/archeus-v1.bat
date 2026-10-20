@echo off
rem Developer tooling, not part of Archeus: the local V1 environment for manual
rem testing (tools\v1_env.py; runbook: notes\v1-local-environment.md). Paths are
rem this file's own, so the checkout can live anywhere.
title Archeus V1 (developer environment)
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (py -3 "%~dp0v1_env.py" %*) else (python "%~dp0v1_env.py" %*)
set rc=%errorlevel%
echo.
echo The Archeus V1 launcher has exited (code %rc%). Press any key to close this window.
pause >nul
exit /b %rc%
