@echo off
rem V2 Live: serves this folder on 127.0.0.1:8000 and opens the browser. Close the server window to stop it.
cd /d "%~dp0"
set PYX=py
where py >nul 2>nul || set PYX=python
start "V2 Live server (127.0.0.1:8000)" /min %PYX% -m http.server 8000 --bind 127.0.0.1
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8000/
