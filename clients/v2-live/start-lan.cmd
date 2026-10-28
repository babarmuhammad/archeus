@echo off
rem V2 Live on your local network, for a phone. On demand only: it binds the PC's private Wi-Fi or Ethernet address, never 0.0.0.0 and never a VPN adapter.
rem It does not open the firewall; see README, "Open it on your phone". Usage: start-lan.cmd [port]   (default 8000). Close this window or press Ctrl+C to stop.
setlocal
cd /d "%~dp0"
set PORT=%~1
if not defined PORT set PORT=8000
echo %PORT%| findstr /r "^[0-9][0-9]*$" >nul || (echo Port must be a number. & exit /b 1)
set PYX=py
where py >nul 2>nul || set PYX=python
set LANIP=
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$n = Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -notmatch 'VPN|TAP|TUN|Virtual|VMware|VirtualBox|Hyper-V|WireGuard|Tailscale|ZeroTier|Bluetooth|Loopback' }; if ($n) { Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $n.ifIndex | Where-Object { $_.IPAddress -match '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)' } | Sort-Object { (Get-NetIPInterface -InterfaceIndex $_.InterfaceIndex -AddressFamily IPv4).InterfaceMetric } | Select-Object -First 1 -ExpandProperty IPAddress }"`) do set LANIP=%%I
if not defined LANIP (echo No private Wi-Fi or Ethernet IPv4 address found, so nothing was started. Connect to the network, or use start.cmd on this PC. & exit /b 1)
echo.
echo   V2 Live on your network: http://%LANIP%:%PORT%/
echo.
echo   WARNING: anyone on this network who can reach that address can open this prototype.
echo   It shows fixture data only, nothing real and nothing connected to a Core.
echo   Windows blocks other devices until you add the firewall rule from README, "Open it on your phone".
echo   Close this window or press Ctrl+C to stop.
echo.
%PYX% -m http.server %PORT% --bind %LANIP%
