@echo off
chcp 65001 >nul
if exist "%~dp0edux-auto-solver\run.bat" (
    cd /d "%~dp0edux-auto-solver"
    call run.bat
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
    if %errorlevel% neq 0 pause
)
