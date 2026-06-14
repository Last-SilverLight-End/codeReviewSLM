@echo off
chcp 65001 >nul

set "ARGS="

:parse
if "%~1"=="" goto run
if /I "%~1"=="--docker" set "ARGS=%ARGS% -Docker"
if /I "%~1"=="--ollama" set "ARGS=%ARGS% -Ollama"
if /I "%~1"=="--all" set "ARGS=%ARGS% -Docker -Ollama"
if /I "%~1"=="--no-pause" set "ARGS=%ARGS% -NoPause"
shift
goto parse

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-dev.ps1" %ARGS%
exit /b %ERRORLEVEL%
