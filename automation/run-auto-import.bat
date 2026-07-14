@echo off
REM ABC MoneyLoan - import all Bravo CSVs sitting in the watch folder, once.
REM Double-click to run manually, or point Windows Task Scheduler at this file.
cd /d "%~dp0"
python auto_import.py
echo.
echo Done. See auto_import.log for details.
pause
