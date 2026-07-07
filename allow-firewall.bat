@echo off
REM Opens Windows Firewall for the ABC Inventory app (port 8000) so phones
REM on the same WiFi can connect. Must be run as Administrator.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   This must be run as Administrator.
    echo   Right-click this file and choose "Run as administrator".
    echo.
    pause
    exit /b
)

netsh advfirewall firewall delete rule name="ABC Inventory" >nul 2>&1
netsh advfirewall firewall add rule name="ABC Inventory" dir=in action=allow protocol=TCP localport=8000 profile=private,domain

echo.
echo ================================================
echo   Firewall opened for ABC Inventory (port 8000).
echo   Phones on the same WiFi can now connect.
echo ================================================
echo.
pause
