@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-LucidPM.ps1"
set "LUCIDPM_EXIT=%ERRORLEVEL%"

echo.
if not "%LUCIDPM_EXIT%"=="0" (
    echo LucidPM did not start successfully. Review the message above.
) else (
    echo LucidPM has stopped.
)
pause
exit /b %LUCIDPM_EXIT%
