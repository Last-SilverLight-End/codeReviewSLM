@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1" -MaxWaitSeconds 30 -MaxTotalSeconds 40
exit /b %ERRORLEVEL%
