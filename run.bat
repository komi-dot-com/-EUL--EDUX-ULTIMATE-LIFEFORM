@echo off
chcp 65001 >nul
setlocal

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

if exist "%ROOT_DIR%\edux-auto-solver\run.bat" (
    call "%ROOT_DIR%\edux-auto-solver\run.bat" %*
    exit /b %errorlevel%
)

echo [X] Khong tim thay "%ROOT_DIR%\edux-auto-solver\run.bat"!
pause
exit /b 1
