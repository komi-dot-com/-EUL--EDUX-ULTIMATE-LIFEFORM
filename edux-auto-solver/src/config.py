import os
import shutil
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=None):
        p = Path(dotenv_path) if dotenv_path else Path(".env")
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Tìm và nạp file .env từ thư mục dự án (nếu có)
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
ENV_PATH = PROJECT_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

# =============================================================================
# CẤU HÌNH HỆ THỐNG & CDP
# =============================================================================
BASE_URL = "https://edux.cmcu.edu.vn/student"
CDP_URL = "http://127.0.0.1:9222"
CHROME_PROFILE_DIR = str(PROJECT_ROOT / "chrome_profile")
DATA_DIR = PROJECT_ROOT / "data"
CACHE_FILE = DATA_DIR / "question_cache.json"

# Đảm bảo thư mục data tồn tại
DATA_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# CẤU HÌNH KẾT NỐI CÔNG CỤ AI CODING (KHÔNG CẦN API KEY)
# Hỗ trợ:
#   - auto        : Tự động chọn công cụ AI Coding tốt nhất đang cài trên máy (Antigravity -> Codex -> Claude -> OpenCode)
#   - antigravity : Kết nối trực tiếp Antigravity CLI (`agy`)
#   - codex       : Kết nối trực tiếp OpenAI Codex CLI (`codex exec`)
#   - claude      : Kết nối trực tiếp Claude Code CLI (`claude -p`)
#   - opencode    : Kết nối trực tiếp OpenCode CLI (`opencode run`)
# =============================================================================
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").strip().lower()
AI_MODEL = os.getenv("AI_MODEL", "gemini-3.8-flash-low").strip()
AI_EFFORT = os.getenv("AI_EFFORT", "low").strip().lower()

# Giữ biến DEFAULT_MODEL và FALLBACK_MODELS để tương thích ngược nếu module khác import
DEFAULT_MODEL = AI_MODEL
FALLBACK_MODELS = [
    "gemini-3.8-flash-low",
    "gemini-3.8-flash-medium",
    "gemini-4-argon-low",
    "gpt-6-luna",
    "claude-sonnet-5-5-low"
]

def detect_available_ai_tools() -> dict:
    """Quét và phát hiện các công cụ AI Coding CLI đã cài đặt trên máy."""
    extra_paths = [
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".gemini" / "antigravity" / "bin"),
        str(Path.home() / ".config" / "Antigravity" / "bin"),
        str(Path.home() / ".opencode" / "bin"),
        "/usr/local/bin",
        "/usr/bin"
    ]
    current_path = os.environ.get("PATH", "")
    search_path = os.pathsep.join(extra_paths + [current_path])

    tools = {}
    for name, binary in [
        ("antigravity", "agy"),
        ("codex", "codex"),
        ("claude", "claude"),
        ("opencode", "opencode"),
        ("copilot", "copilot"),
    ]:
        found = shutil.which(binary, path=search_path)
        if found:
            tools[name] = found
    return tools

ALLOWED_DOMAINS = [
    "edux.cmcu.edu.vn",
    "cmcu.edu.vn",
    "microsoftonline.com",
    "login.microsoftonline.com",
    "live.com",
    "google.com",
    "accounts.google.com"
]

# =============================================================================
# SCRIPT CHỐNG PHÁT HIỆN ẨN TAB / RỜI MÀN HÌNH (ANTI-VISIBILITY)
# =============================================================================
ANTI_VISIBILITY_SCRIPT = """
(() => {
    try {
        Object.defineProperty(document, 'hidden', {
            get: () => false,
            configurable: true
        });
        Object.defineProperty(document, 'visibilityState', {
            get: () => 'visible',
            configurable: true
        });
        Object.defineProperty(document, 'webkitVisibilityState', {
            get: () => 'visible',
            configurable: true
        });
    } catch (e) {}

    const blockedEvents = [
        'visibilitychange',
        'webkitvisibilitychange',
        'blur',
        'focusout',
        'pagehide'
    ];
    blockedEvents.forEach(eventType => {
        window.addEventListener(eventType, (e) => {
            e.stopImmediatePropagation();
            e.stopPropagation();
        }, true);
        document.addEventListener(eventType, (e) => {
            e.stopImmediatePropagation();
            e.stopPropagation();
        }, true);
    });

    try {
        Document.prototype.hasFocus = () => true;
        window.onblur = null;
        window.onfocusout = null;
        document.onvisibilitychange = null;
    } catch (e) {}
})();
"""

def infer_field(subject_name: str) -> str:
    """Nhận diện chuyên ngành môn học để tối ưu prompt cho AI Coding Agent."""
    s = subject_name.lower()
    if "phần mềm" in s or "software" in s:
        return "Công nghệ Phần mềm, Kiến trúc Hệ thống & Quy trình Agile (Software Engineering)"
    if "lập trình" in s or "python" in s or "c++" in s or "java" in s or "prog" in s or "cơ sở lập trình" in s:
        return "Khoa học Máy tính, Thuật toán & Ngôn ngữ Lập trình Chuyên sâu"
    if "dữ liệu" in s or "database" in s or "sql" in s:
        return "Hệ Cơ sở Dữ liệu, Mô hình Dữ liệu & SQL"
    if "web" in s or "mạng" in s or "network" in s:
        return "Phát triển Ứng dụng Web, Kiến trúc Client-Server & An ninh Mạng"
    if "toán" in s or "math" in s:
        return "Toán rời rạc, Đại số Tuyến tính & Toán Tin học"
    if "pháp lý" in s or "luật" in s or "đạo đức" in s:
        return "Pháp lý CNTT, Sở hữu Trí tuệ & Đạo đức Nghề nghiệp"
    if "khởi nghiệp" in s or "kỹ năng" in s:
        return "Quản trị Doanh nghiệp, Khởi nghiệp Sáng tạo & Kỹ năng Mềm"
    return "Khoa học Công nghệ Thông tin & Chuyên ngành Đại học"
