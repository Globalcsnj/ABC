@echo off
title ABC Pawnshop Inventory
cd /d "%~dp0"

echo ================================================
echo   ABC Pawnshop Inventory
echo ================================================
echo.
echo Checking for updates...
git pull
if errorlevel 1 (
    echo.
    echo [!] Could not check for updates ^(no internet or git?^).
    echo     Starting with the version you already have.
)
echo.

echo Installing/updating dependencies...
pip install -r requirements.txt -q

REM Open the browser to the app after a short delay (HTTPS if a cert exists)
if exist "%~dp0data\certs\cert.pem" (
    start "" cmd /c "timeout /t 4 >nul & start https://localhost:8000"
) else (
    start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
)

echo.
echo Starting server... (leave this window open; close it to stop)
python run.py
pause
