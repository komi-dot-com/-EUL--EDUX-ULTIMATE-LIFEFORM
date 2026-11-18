@echo off
chcp 65001 >nul
setlocal

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

if not exist "%ROOT_DIR%\edux-auto-solver\run.bat" goto :missing

call "%ROOT_DIR%\edux-auto-solver\run.bat" %*
exit /b %errorlevel%

:missing
echo [X] Khong tim thay "%ROOT_DIR%\edux-auto-solver\run.bat"!
pause
exit /b 1
