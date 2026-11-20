#!/usr/bin/env bash
# =============================================================================
#  EDUX ULTIMATE LIFEFORM v0.7 - SCRIPT KHỞI CHẠY DÀNH CHO LINUX
#  Công nghệ: AI Coding CLI (Antigravity / Codex) + CMCU-Vạn-Năng V3.2 FIX
#  Không cần Gemini API Key!
# =============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Nếu đang ở thư mục ngoài thì tự chuyển vào edux-auto-solver
if [ -d "edux-auto-solver" ] && [ -f "edux-auto-solver/main.py" ]; then
    cd edux-auto-solver
fi

# Bổ sung PATH cho các công cụ AI Coding CLI (agy, codex, claude, opencode) và Homebrew trên macOS
export PATH="$HOME/.local/bin:$HOME/.gemini/antigravity/bin:$HOME/.config/Antigravity/bin:$HOME/.opencode/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:$PATH"

OS_NAME="$(uname -s)"

echo ""
echo -e "\033[1;36m==========================================================================\033[0m"
echo -e "\033[1;33m   ⚡ EDUX ULTIMATE LIFEFORM v0.7 - KHỞI CHẠY TRÊN ${OS_NAME} ⚡\033[0m"
echo -e "\033[1;32m   AI Coding CLI (Antigravity & Codex) + CMCU-Vạn-Năng V3.2 FIX (3/3)\033[0m"
echo -e "\033[1;36m==========================================================================\033[0m"
echo ""

# 1. Kiểm tra các công cụ AI Coding CLI trên máy
echo -e "\033[1;36m[*] Kiểm tra công cụ AI Coding CLI (Không cần API Key):\033[0m"
FOUND_AI=0
if command -v agy &>/dev/null; then
    echo -e "  \033[1;32m[✔] Google Antigravity CLI (agy):\033[0m $(command -v agy)"
    FOUND_AI=1
fi
if command -v codex &>/dev/null; then
    echo -e "  \033[1;32m[✔] OpenAI Codex CLI (codex):\033[0m     $(command -v codex)"
    FOUND_AI=1
fi
if command -v claude &>/dev/null; then
    echo -e "  \033[1;32m[✔] Claude Code CLI (claude):\033[0m     $(command -v claude)"
    FOUND_AI=1
fi
if command -v opencode &>/dev/null; then
    echo -e "  \033[1;32m[✔] OpenCode CLI (opencode):\033[0m      $(command -v opencode)"
    FOUND_AI=1
fi

if [ "$FOUND_AI" -eq 0 ]; then
    echo -e "  \033[1;33m[!] Cảnh báo: Chưa tìm thấy agy hoặc codex trong PATH!\033[0m"
fi
echo ""

# 2. Tìm Python 3 trên Linux
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo -e "\033[1;31m[X] KHÔNG TÌM THẤY PYTHON 3 TRÊN LINUX!\033[0m"
    echo "Vui lòng cài đặt Python 3 (VD: sudo dnf install python3 hoặc sudo apt install python3 python3-venv)"
    exit 1
fi

echo -e "\033[1;36m[+] Sử dụng Python:\033[0m $($PYTHON_CMD --version)"

# 3. Kiểm tra và tạo lại môi trường ảo .venv nếu bị lệch đường dẫn hoặc chưa có
VENV_VALID=false
if [ -x ".venv/bin/python" ]; then
    if .venv/bin/python -c "import sys; print(1)" &>/dev/null; then
        VENV_VALID=true
    else
        echo -e "\033[1;33m[!] Phát hiện .venv cũ không tương thích. Đang tạo lại .venv mới cho Linux...\033[0m"
        rm -rf .venv
    fi
elif [ -d ".venv" ]; then
    echo -e "\033[1;33m[!] Phát hiện .venv của Windows. Đang tạo lại .venv chuẩn cho Linux...\033[0m"
    rm -rf .venv
fi

if [ "$VENV_VALID" = false ]; then
    echo -e "\033[1;36m[+] Đang khởi tạo môi trường ảo (.venv)...\033[0m"
    $PYTHON_CMD -m venv .venv
    echo -e "\033[1;32m[✔] Tạo .venv thành công!\033[0m"
fi

VENV_PYTHON=".venv/bin/python"
VENV_PIP=".venv/bin/pip"

# 4. Cài đặt thư viện cần thiết
if ! $VENV_PYTHON -c "import playwright, rich, dotenv" &>/dev/null; then
    echo -e "\033[1;36m[+] Đang cài đặt các thư viện cần thiết (playwright, rich, python-dotenv)...\033[0m"
    $VENV_PIP install --upgrade pip --quiet 2>/dev/null || true
    $VENV_PIP install -r requirements.txt --quiet || $VENV_PIP install playwright rich python-dotenv
fi

# 5. Đảm bảo file .env tồn tại (Không hỏi API Key!)
if [ ! -f ".env" ]; then
    cat > .env <<EOF
AI_PROVIDER=auto
AI_MODEL=gemini-3.8-flash-low
AI_EFFORT=low
EOF
fi

# 6. Mở khóa Chrome Profile trên Linux (xóa SingletonLock nếu bị kẹt từ phiên trước)
CHROME_PROFILE="$PWD/chrome_profile"
mkdir -p "$CHROME_PROFILE"

CDP_READY=false
if curl -s --connect-timeout 2 "http://127.0.0.1:9222/json/version" 2>/dev/null | grep -q "Browser"; then
    CDP_READY=true
fi

if [ "$CDP_READY" = false ]; then
    rm -f "$CHROME_PROFILE/SingletonLock" "$CHROME_PROFILE/SingletonSocket" "$CHROME_PROFILE/SingletonCookie" 2>/dev/null || true
    rm -rf "$CHROME_PROFILE/Default/Sessions"/* 2>/dev/null || true

    CHROME_BIN=""
    if [ "$OS_NAME" = "Darwin" ]; then
        for mac_candidate in \
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
            "$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
            "/Applications/Chromium.app/Contents/MacOS/Chromium" \
            "$HOME/Applications/Chromium.app/Contents/MacOS/Chromium" \
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
            "$HOME/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
            "$HOME/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
            "/Applications/Arc.app/Contents/MacOS/Arc" \
            "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi"; do
            if [ -x "$mac_candidate" ]; then
                CHROME_BIN="$mac_candidate"
                break
            fi
        done
    fi

    if [ -z "$CHROME_BIN" ]; then
        for candidate in google-chrome google-chrome-stable chromium chromium-browser brave-browser microsoft-edge /usr/bin/google-chrome /usr/bin/chromium /usr/bin/chromium-browser /snap/bin/chromium; do
            if command -v "$candidate" &>/dev/null; then
                CHROME_BIN="$(command -v "$candidate")"
                break
            fi
        done
    fi

    if [ -n "$CHROME_BIN" ]; then
        echo -e "\033[1;36m[+] Đang khởi động trình duyệt trên ${OS_NAME} (Cổng 9222): $CHROME_BIN\033[0m"
        nohup "$CHROME_BIN" \
            --remote-debugging-port=9222 \
            "--user-data-dir=$CHROME_PROFILE" \
            --disable-features=OptimizationGuideModelDownloading,OptimizationHints,OptimizationGuideOnDeviceModel,OnDeviceModelExecution \
            --disable-component-update \
            --disk-cache-size=209715200 \
            --media-cache-size=209715200 \
            --no-default-browser-check \
            --no-first-run \
            "https://edux.cmcu.edu.vn/student" >/dev/null 2>&1 &
        sleep 2.5
    else
        echo -e "\033[1;31m[X] Không tìm thấy Google Chrome, Chromium, Brave hoặc Edge trên ${OS_NAME}!\033[0m"
        echo "Vui lòng cài đặt Google Chrome hoặc Chromium vào /Applications (macOS) hoặc PATH (Linux) trước khi chạy."
        exit 1
    fi
else
    echo -e "\033[1;32m[✔] Đã tìm thấy trình duyệt đang chạy trên cổng 9222!\033[0m"
fi

# 7. Dọn dẹp cache rác an toàn khi thoát
cleanup_on_exit() {
    rm -rf "$CHROME_PROFILE/Default/Sessions" \
           "$CHROME_PROFILE/Default/Cache" \
           "$CHROME_PROFILE/Default/Code Cache" \
           "$CHROME_PROFILE/OptGuideOnDeviceModel" \
           "$CHROME_PROFILE/optimization_guide_model_store" 2>/dev/null || true
}
trap cleanup_on_exit EXIT

# 8. Nếu người dùng truyền tham số (VD: ./run.sh --cli, ./run.sh --slide, ./run.sh --web), chuyển thẳng vào main.py
if [ $# -gt 0 ]; then
    exec "$VENV_PYTHON" main.py "$@"
fi

# Nếu không truyền tham số, hiển thị menu nhanh cho phép chọn chế độ CLI v0.7 hoặc Web Dashboard
echo ""
echo -e "\033[1;36mChọn chế độ điều khiển:\033[0m"
echo -e "  \033[1;33m[1]\033[0m Mở \033[1;32mCông cụ CLI v0.7 (Terminal)\033[0m + chạy ngầm Web Dashboard (Khuyên dùng)"
echo -e "  \033[1;33m[2]\033[0m Mở \033[1;36mWeb Dashboard (http://127.0.0.1:8765)\033[0m trên trình duyệt"
echo -e "  \033[1;33m[3]\033[0m Chạy ngay \033[1;35mCMCU-Vạn-Năng V3.2 FIX\033[0m trên Slide đang mở"
echo -e "  \033[1;33m[4]\033[0m Giải ngay \033[1;32mBài tập đang mở\033[0m bằng AI Coding CLI"
echo ""
read -r -p "👉 Nhập lựa chọn [1-4, mặc định = 1]: " mode_choice
mode_choice="${mode_choice:-1}"

case "$mode_choice" in
    2)
        exec "$VENV_PYTHON" main.py --web
        ;;
    3)
        exec "$VENV_PYTHON" main.py --slide
        ;;
    4)
        exec "$VENV_PYTHON" main.py --solve
        ;;
    *)
        exec "$VENV_PYTHON" main.py --cli
        ;;
esac
