@echo off
REM ABC MoneyLoan - "What Changed on This PC" report
REM Double-click this file. It asks for administrator rights (so it can read the
REM sign-in history), runs the report, and saves a copy to your Desktop.

REM --- Re-launch as administrator if we aren't already ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Asking for administrator rights so we can read the sign-in history...
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

cd /d "%~dp0"
echo ================================================
echo   What Changed on This PC - building report...
echo ================================================
echo.

REM Change 14 to 30 below to look back a full month.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0system-change-report.ps1" -Days 14

echo.
echo Done. A copy was also saved to your Desktop (PC-Changes-...txt).
pause
