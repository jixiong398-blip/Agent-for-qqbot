@echo off
chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
rem Only this instance's authenticated supervisor can stop its captured processes.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0extras\scripts\bootstrap.ps1" stop %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
