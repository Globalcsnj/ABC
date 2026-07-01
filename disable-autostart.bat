@echo off
REM Removes ABC Inventory from Windows startup.
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ABC Inventory.lnk"
if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo Auto-start DISABLED. ABC Inventory will no longer start with Windows.
) else (
    echo Auto-start was not enabled ^(nothing to remove^).
)
echo.
pause
