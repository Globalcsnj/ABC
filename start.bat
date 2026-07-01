@echo off
title ABC Pawnshop Inventory
echo Starting ABC Pawnshop Inventory System...
cd /d "%~dp0"
pip install -r requirements.txt -q
REM Open the browser to the app after a short delay
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"
python run.py
pause
