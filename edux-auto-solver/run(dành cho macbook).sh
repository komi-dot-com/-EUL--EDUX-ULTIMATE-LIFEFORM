#!/usr/bin/env bash
# =============================================================================
#  EDUX ULTIMATE LIFEFORM - RUN SCRIPT DÀNH CHO MACBOOK (macOS)
# =============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Nếu đang ở thư mục ngoài thì tự chuyển vào edux-auto-solver
if [ -d "edux-auto-solver" ]; then
    cd edux-auto-solver
fi

echo ""
echo "====================================================================="
echo "   EDUX ULTIMATE LIFEFORM - KHỞI TẠO HỆ THỐNG TỰ ĐỘNG CMCU LMS (macOS)"
echo "====================================================================="
echo ""

# 1. Tìm Python 3 trên macOS
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "[X] KHÔNG TÌM THẤY PYTHON 3 TRÊN MACBOOK!"
    echo "Vui lòng cài đặt Python 3 (ví dụ qua: brew install python hoặc tải từ https://www.python.org)"
    exit 1
fi

echo "[+] Đang sử dụng Python: $($PYTHON_CMD --version)"

# 2. Tạo môi trường ảo .venv nếu chưa có
if [ ! -d ".venv" ]; then
    echo "[+] Đang khởi tạo môi trường ảo (.venv)..."
    $PYTHON_CMD -m venv .venv
    if [ ! -d ".venv" ]; then
        echo "[X] Không thể tạo môi trường ảo .venv!"
        exit 1
    fi
    echo "[v] Tạo .venv thành công!"
fi

VENV_PYTHON=".venv/bin/python"
VENV_PIP=".venv/bin/pip"

# 3. Cài đặt thư viện cần thiết
echo "[+] Đang kiểm tra thư viện..."
$VENV_PIP install -r requirements.txt --quiet
if [ $? -ne 0 ]; then
    $VENV_PIP install playwright google-genai rich python-dotenv
fi

# Cài đặt trình duyệt Playwright nếu cần
$VENV_PYTHON -m playwright install chromium --quiet 2>/dev/null || true

# 4. Kiểm tra cấu hình GEMINI_API_KEY
if [ ! -f ".env" ] || ! grep -q "GEMINI_API_KEY=" .env || grep -q "GEMINI_API_KEY=$" .env; then
    echo ""
    echo "---------------------------------------------------------------------"
    echo "  CẤU HÌNH GEMINI API KEY (Lấy miễn phí tại: https://aistudio.google.com/apikey)"
    echo "---------------------------------------------------------------------"
    read -p "Nhập GEMINI_API_KEY của bạn: " input_key
    input_key=$(echo "$input_key" | xargs)
    if [ -n "$input_key" ]; then
        echo "GEMINI_API_KEY=$input_key" > .env
        echo "GEMINI_MODEL=gemini-3.5-flash-lite" >> .env
        echo "[v] Đã lưu API key vào .env!"
    fi
fi

# 5. Khởi động Google Chrome với cổng Remote Debugging 9222 trên macOS
CHROME_PROFILE="$PWD/chrome_profile"
mkdir -p "$CHROME_PROFILE"

CDP_READY=false
if curl -s --connect-timeout 2 "http://127.0.0.1:9222/json/version" 2>/dev/null | grep -q "Browser"; then
    CDP_READY=true
fi

if [ "$CDP_READY" = false ]; then
    echo "[+] Đang khởi động Google Chrome trên macOS (Cổng 9222)..."
    CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if [ ! -f "$CHROME_APP" ]; then
        CHROME_APP="$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    fi

    if [ -f "$CHROME_APP" ]; then
        "$CHROME_APP" \
            --remote-debugging-port=9222 \
            "--user-data-dir=$CHROME_PROFILE" \
            --disable-features=OptimizationGuideModelDownloading,OptimizationHints,OptimizationGuideOnDeviceModel,OnDeviceModelExecution \
            --disable-component-update \
            --disk-cache-size=209715200 \
            --media-cache-size=209715200 \
            --no-default-browser-check \
            --no-first-run \
            "https://edux.cmcu.edu.vn/student" >/dev/null 2>&1 &
        sleep 3
    else
        echo "[!] Không tìm thấy Google Chrome tại /Applications. Vui lòng cài Google Chrome!"
    fi
else
    echo "[v] Đã tìm thấy Google Chrome đang chạy trên cổng 9222!"
fi

# 6. Dọn dẹp cache rác an toàn khi thoát
cleanup_on_exit() {
    rm -rf "$CHROME_PROFILE/Default/Sessions" \
           "$CHROME_PROFILE/Default/Cache" \
           "$CHROME_PROFILE/Default/Code Cache" \
           "$CHROME_PROFILE/OptGuideOnDeviceModel" \
           "$CHROME_PROFILE/optimization_guide_model_store" 2>/dev/null || true
}
trap cleanup_on_exit EXIT

echo ""
echo "[+] Đang kết nối Bot vào Chrome..."
echo ""

# 7. Khởi chạy Bot
$VENV_PYTHON bot.py
