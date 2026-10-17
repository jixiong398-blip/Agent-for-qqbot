@echo off
chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
rem Prebuilt: select this complete bundle offline. Source checkout: explicit maintainer build only.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0extras\scripts\bootstrap.ps1" update %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
