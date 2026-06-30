@echo off
echo Starting ABC Pawnshop Inventory System...
cd /d "%~dp0"
pip install -r requirements.txt -q
python run.py
pause
