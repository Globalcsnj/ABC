@echo off
REM Makes ABC Inventory start automatically when Windows boots.
REM It places a shortcut to start.bat in the Windows Startup folder.
setlocal
set "TARGET=%~dp0start.bat"
set "WORKDIR=%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\ABC Inventory.lnk"

powershell -NoProfile -Command ^
  "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath='%TARGET%';" ^
  "$s.WorkingDirectory='%WORKDIR%';" ^
  "$s.WindowStyle=7;" ^
  "$s.Description='ABC MoneyLoan Pawnshop Inventory (auto-start)';" ^
  "$s.Save()"

echo.
echo ================================================
echo   Auto-start ENABLED.
echo   ABC Inventory will now launch automatically
echo   every time this computer starts up.
echo ================================================
echo.
echo It runs minimized in the background and opens the
echo browser to http://localhost:8000
echo.
echo To turn it off later, run: disable-autostart.bat
echo.
pause
