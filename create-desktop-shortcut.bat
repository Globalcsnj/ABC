@echo off
REM Creates a desktop shortcut named "ABC Inventory" that launches start.bat
setlocal
set "TARGET=%~dp0start.bat"
set "ICONDIR=%~dp0"
set "SHORTCUT=%USERPROFILE%\Desktop\ABC Inventory.lnk"

powershell -NoProfile -Command ^
  "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath='%TARGET%';" ^
  "$s.WorkingDirectory='%ICONDIR%';" ^
  "$s.Description='ABC MoneyLoan Pawnshop Inventory';" ^
  "$s.Save()"

echo.
echo Done. A shortcut named "ABC Inventory" is now on your Desktop.
echo Double-click it anytime to start the inventory system.
pause
