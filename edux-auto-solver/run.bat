@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

:: =============================================================================
::  EDUX ULTIMATE LIFEFORM v0.6 - SCRIPT KHỞI CHẠY DÀNH CHO WINDOWS
::  Công nghệ: AI Coding CLI (Antigravity / Codex) + CMCU-Vạn-Năng V3.2 FIX
::  Không cần Gemini API Key!
:: =============================================================================

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
cd /d "%DIR%"

:: Nếu đang ở thư mục ngoài thì tự chuyển vào edux-auto-solver
if exist "edux-auto-solver\main.py" cd /d "edux-auto-solver"

:: Bổ sung PATH phổ biến cho các công cụ AI Coding CLI trên Windows
set "PATH=%APPDATA%\npm;%USERPROFILE%\.local\bin;%LOCALAPPDATA%\Programs\Antigravity\bin;%LOCALAPPDATA%\Antigravity\bin;%USERPROFILE%\.opencode\bin;%PATH%"

echo.
echo ==========================================================================
echo    EDUX ULTIMATE LIFEFORM v0.6 - KHỞI CHẠY TRÊN WINDOWS
echo    AI Coding CLI (Antigravity ^& Codex) + CMCU-Vạn-Năng V3.2 FIX (3/3)
echo ==========================================================================
echo.

:: 1. Kiểm tra các công cụ AI Coding CLI trên máy
echo [*] Kiểm tra công cụ AI Coding CLI (Không cần API Key):
set "FOUND_AI=0"
for %%C in (agy codex claude opencode) do call :check_cli %%C
if "%FOUND_AI%"=="0" echo   [!] Cảnh báo: Chưa tìm thấy agy, codex, claude hoặc opencode trong PATH!
echo.

:: 2. Tìm Python (Ưu tiên python_embed -> .venv -> Python hệ thống)
set "ACTIVE_PYTHON="
set "EMBED_PYTHON=%CD%\python_embed\python.exe"
set "VENV_DIR=%CD%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%EMBED_PYTHON%" goto :check_venv
set "ACTIVE_PYTHON=%EMBED_PYTHON%"
echo [+] Sử dụng Python Portable tích hợp sẵn.
goto :python_ready

:check_venv
if not exist "%VENV_PYTHON%" goto :check_foreign_venv
"%VENV_PYTHON%" -c "import sys; print(1)" >nul 2>&1
if not errorlevel 1 (
    set "ACTIVE_PYTHON=%VENV_PYTHON%"
    goto :python_ready
)
echo [!] Phát hiện .venv cũ không tương thích. Đang tạo lại .venv mới cho Windows...
rmdir /s /q "%VENV_DIR%" 2>nul
goto :create_venv

:check_foreign_venv
if exist "%VENV_DIR%" (
    echo [!] Phát hiện .venv không phải của Windows. Đang tạo lại .venv chuẩn cho Windows...
    rmdir /s /q "%VENV_DIR%" 2>nul
)

:create_venv
set "SYS_PYTHON="
where py >nul 2>&1
if not errorlevel 1 (
    set "SYS_PYTHON=py -3"
    goto :do_create_venv
)
where python >nul 2>&1
if not errorlevel 1 (
    set "SYS_PYTHON=python"
    goto :do_create_venv
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "SYS_PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :do_create_venv
)

echo [X] KHÔNG TÌM THẤY PYTHON 3 TRÊN WINDOWS!
echo Vui lòng cài đặt Python 3.10+ tại https://www.python.org/downloads/
pause
exit /b 1

:do_create_venv
echo [+] Đang khởi tạo môi trường ảo (.venv)...
!SYS_PYTHON! -m venv "%VENV_DIR%"
if not exist "%VENV_PYTHON%" (
    echo [X] Lỗi tạo môi trường ảo .venv!
    pause
    exit /b 1
)
echo [OK] Tạo .venv thành công!
set "ACTIVE_PYTHON=%VENV_PYTHON%"

:python_ready
for /f "delims=" %%V in ('"%ACTIVE_PYTHON%" --version 2^>^&1') do echo [+] Phiên bản Python: %%V

:: 3. Kiểm tra và cài đặt thư viện cần thiết (chỉ khi thiếu)
"%ACTIVE_PYTHON%" -c "import playwright, rich, dotenv" >nul 2>&1
if errorlevel 1 (
    echo [+] Đang cài đặt các thư viện cần thiết (playwright, rich, python-dotenv)...
    "%ACTIVE_PYTHON%" -m pip install --upgrade pip --quiet >nul 2>&1
    "%ACTIVE_PYTHON%" -m pip install -r requirements.txt --quiet
    if errorlevel 1 "%ACTIVE_PYTHON%" -m pip install playwright rich python-dotenv
)

:: 4. Đảm bảo file .env tồn tại (Không hỏi API Key!)
if not exist ".env" (
    echo AI_PROVIDER=auto> ".env"
    echo AI_MODEL=gemini-3.8-flash-low>> ".env"
    echo AI_EFFORT=low>> ".env"
)

:: 5. Kiểm tra và khởi động trình duyệt qua cổng Remote Debugging 9222
set "CHROME_PROFILE=%CD%\chrome_profile"
if not exist "%CHROME_PROFILE%" mkdir "%CHROME_PROFILE%"

set "CDP_READY=0"
where curl.exe >nul 2>&1
if errorlevel 1 goto :check_cdp_ps
curl.exe -s --connect-timeout 2 "http://127.0.0.1:9222/json/version" 2>nul | findstr /i "Browser" >nul 2>&1
if not errorlevel 1 set "CDP_READY=1"
goto :after_cdp_check

:check_cdp_ps
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:9222/json/version' -TimeoutSec 2; if ($r.Browser) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 set "CDP_READY=1"

:after_cdp_check
if "%CDP_READY%"=="1" (
    echo [OK] Đã tìm thấy trình duyệt đang chạy trên cổng 9222!
    goto :run_app
)

del /f /q "%CHROME_PROFILE%\SingletonLock" "%CHROME_PROFILE%\SingletonSocket" "%CHROME_PROFILE%\SingletonCookie" 2>nul
if exist "%CHROME_PROFILE%\Default\Sessions" del /f /q "%CHROME_PROFILE%\Default\Sessions\*" 2>nul

set "CHROME_BIN="
for %%B in (
    "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"
    "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
    "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
) do (
    if not defined CHROME_BIN (
        if exist "%%~B" set "CHROME_BIN=%%~B"
    )
)

if defined CHROME_BIN (
    echo [+] Đang khởi động trình duyệt trên Windows (Cổng 9222)...
    start "" "!CHROME_BIN!" --remote-debugging-port=9222 --user-data-dir="%CHROME_PROFILE%" --disable-features=OptimizationGuideModelDownloading,OptimizationHints,OptimizationGuideOnDeviceModel,OnDeviceModelExecution --disable-component-update --disk-cache-size=209715200 --media-cache-size=209715200 --no-default-browser-check --no-first-run "https://edux.cmcu.edu.vn/student"
    timeout /t 3 /nobreak >nul
) else (
    echo [!] Không tìm thấy Google Chrome, Brave hoặc Edge theo đường dẫn tiêu chuẩn.
    echo [!] Bot sẽ tự động tìm kiếm khi khởi chạy.
)

:run_app
:: 6. Nếu người dùng truyền tham số (VD: run.bat --cli, --web, --slide, --solve), chuyển thẳng vào main.py
if not "%~1"=="" (
    "%ACTIVE_PYTHON%" main.py %*
    set "EXIT_CODE=!errorlevel!"
    goto :cleanup
)

:: 7. Hiển thị menu chọn chế độ (tương đồng với run.sh trên Linux)
echo.
echo Chọn chế độ điều khiển:
echo   [1] Mở Công cụ CLI v0.6 (Terminal) + chạy ngầm Web Dashboard (Khuyên dùng)
echo   [2] Mở Web Dashboard (http://127.0.0.1:8765) trên trình duyệt
echo   [3] Chạy ngay CMCU-Vạn-Năng V3.2 FIX trên Slide đang mở
echo   [4] Giải ngay Bài tập đang mở bằng AI Coding CLI
echo.
set "MODE_CHOICE="
set /p "MODE_CHOICE=[>] Nhập lựa chọn [1-4, mặc định = 1]: "
if "%MODE_CHOICE%"=="" set "MODE_CHOICE=1"

if "%MODE_CHOICE%"=="2" (
    "%ACTIVE_PYTHON%" main.py --web
) else if "%MODE_CHOICE%"=="3" (
    "%ACTIVE_PYTHON%" main.py --slide
) else if "%MODE_CHOICE%"=="4" (
    "%ACTIVE_PYTHON%" main.py --solve
) else (
    "%ACTIVE_PYTHON%" main.py --cli
)
set "EXIT_CODE=!errorlevel!"

:cleanup
:: 8. Dọn dẹp cache rác an toàn khi thoát
for %%D in (
    "%CHROME_PROFILE%\Default\Sessions"
    "%CHROME_PROFILE%\Default\Cache"
    "%CHROME_PROFILE%\Default\Code Cache"
    "%CHROME_PROFILE%\OptGuideOnDeviceModel"
    "%CHROME_PROFILE%\optimization_guide_model_store"
) do (
    if exist "%%~D" rmdir /s /q "%%~D" 2>nul
)

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [X] Chương trình kết thúc với mã lỗi %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%

:check_cli
where %1 >nul 2>&1
if errorlevel 1 goto :eof
for /f "delims=" %%P in ('where %1 2^>nul') do (
    echo   [OK] %1: %%P
    set "FOUND_AI=1"
    goto :eof
)
goto :eof
