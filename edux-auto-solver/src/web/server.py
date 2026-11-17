import os
import json
import time
import queue
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List

from src.config import ENV_PATH, DATA_DIR, AI_PROVIDER, AI_MODEL, AI_EFFORT, detect_available_ai_tools
from src.utils import console

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
INDEX_HTML = TEMPLATE_DIR / "index.html"


class AppState:
    def __init__(self):
        # Action Queue: Web Handler -> Main Playwright Thread
        self.action_queue = queue.Queue()

        # State được cập nhật an toàn bởi Main Thread
        self.chrome_connected = False
        self.subject_name = "Chưa nhận diện môn"
        self.is_running = False
        self.current_task = ""
        self.task_detail = ""
        self.stop_requested = False
        self.cache_count = 0

        # Thông tin tiến trình realtime
        self.progress_current = 0
        self.progress_total = 0
        self.progress_percent = 0
        self.step_label = "Sẵn sàng nhận lệnh"
        self.active_stage = 0  # 0: Idle, 1: Scanning/Vision, 2: AI CLI CoT, 3: DOM, 4: Review & Submit
        self.task_start_time = 0.0
        self.ai_provider = AI_PROVIDER
        self.ai_model = AI_MODEL
        self.ai_effort = AI_EFFORT
        self.available_tools = list(detect_available_ai_tools().keys())
        self.last_score = ""
        self.api_key_configured = True

        # Danh sách lịch sử làm bài và chạy slide
        self.history: List[Dict[str, Any]] = []
        self.chapter_scores: Dict[str, str] = {}
        self._load_history()

        # Log subscribers cho Server-Sent Events (SSE)
        self.log_subscribers: List[queue.Queue] = []
        self.lock = threading.Lock()

    def _load_history(self):
        try:
            hist_file = DATA_DIR / "activity_history.json"
            if hist_file.exists():
                with open(hist_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.history = data.get("history", [])
                        self.chapter_scores = data.get("chapter_scores", {})
                    elif isinstance(data, list):
                        self.history = data
                        self.chapter_scores = {}
        except Exception:
            self.history = []
            self.chapter_scores = {}

    def add_history(self, entry_type: str, title: str, detail: str = "", score: str = "", status: str = "Hoàn thành"):
        import datetime
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        entry = {
            "id": int(time.time() * 1000),
            "time": now_str,
            "type": entry_type,   # 'ai', 'manual', 'slide'
            "title": title,
            "detail": detail,
            "score": score or "10.0 / 10",
            "status": status
        }
        with self.lock:
            self.history.insert(0, entry)
            if len(self.history) > 80:
                self.history = self.history[:80]

            # Lưu điểm cao nhất theo tên chapter
            clean_key = title.split('(')[0].strip() if '(' in title else title.strip()
            if score and score != "N/A":
                self.chapter_scores[clean_key] = score

            try:
                hist_file = DATA_DIR / "activity_history.json"
                save_data = {
                    "history": self.history,
                    "chapter_scores": self.chapter_scores
                }
                with open(hist_file, "w", encoding="utf-8") as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def broadcast_log(self, message: str):
        with self.lock:
            console.print(f"[dim]{message}[/dim]")
            dead_subs = []
            for q in self.log_subscribers:
                try:
                    q.put_nowait(message)
                except Exception:
                    dead_subs.append(q)
            for d in dead_subs:
                if d in self.log_subscribers:
                    self.log_subscribers.remove(d)


state = AppState()


class WebDashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        # 1. Trang chủ Dashboard (HTML)
        if parsed.path in ["/", "/index.html"]:
            if not INDEX_HTML.exists():
                self.send_error(404, "index.html not found")
                return
            with open(INDEX_HTML, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
            return

        # 2. Trạng thái hệ thống (/api/status)
        if parsed.path == "/api/status":
            elapsed_sec = int(time.time() - state.task_start_time) if (state.is_running and state.task_start_time > 0) else 0
            data = {
                "chrome_connected": state.chrome_connected,
                "subject_name": state.subject_name,
                "is_running": state.is_running,
                "current_task": state.current_task,
                "task_detail": state.task_detail,
                "cache_count": state.cache_count,
                "progress_current": state.progress_current,
                "progress_total": state.progress_total,
                "progress_percent": state.progress_percent,
                "step_label": state.step_label,
                "active_stage": state.active_stage,
                "elapsed_sec": elapsed_sec,
                "ai_provider": state.ai_provider,
                "ai_model": state.ai_model,
                "ai_effort": state.ai_effort,
                "available_tools": state.available_tools,
                "last_score": state.last_score,
                "api_key_configured": True,
                "history": state.history[:30],
                "chapter_scores": state.chapter_scores
            }
            self.send_json(data)
            return

        # 3. Stream Log realtime qua Server-Sent Events (/api/logs)
        if parsed.path == "/api/logs":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            log_q = queue.Queue(maxsize=150)
            with state.lock:
                state.log_subscribers.append(log_q)

            init_msg = f"data: [Hệ thống] Đã kết nối Web Dashboard! AI CLI: {state.ai_provider.upper()} ({state.ai_model}) | Slide: CMCU-Vạn-Năng V3.2 FIX\n\n"
            self.wfile.write(init_msg.encode("utf-8"))
            self.wfile.flush()

            try:
                while True:
                    try:
                        msg = log_q.get(timeout=10.0)
                        payload = f"data: {msg}\n\n"
                        self.wfile.write(payload.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                with state.lock:
                    if log_q in state.log_subscribers:
                        state.log_subscribers.remove(log_q)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        # 1. Giải bài tập đang mở
        if parsed.path == "/api/action/solve_current":
            if state.is_running:
                self.send_json({"error": "Đang có tác vụ đang chạy!"}, 400)
                return
            state.action_queue.put({"action": "solve_current"})
            self.send_json({"status": "queued"})
            return

        # 2. Chạy Slide học liệu (CMCU-Vạn-Năng V3.2 FIX)
        if parsed.path == "/api/action/slide":
            if state.is_running:
                self.send_json({"error": "Đang có tác vụ đang chạy!"}, 400)
                return
            speed = float(req_data.get("speed", 0.25))
            state.action_queue.put({"action": "slide", "speed": speed})
            self.send_json({"status": "queued"})
            return

        # 3. Giải theo khoảng câu
        if parsed.path == "/api/action/solve_range":
            if state.is_running:
                self.send_json({"error": "Đang có tác vụ đang chạy!"}, 400)
                return
            start_q = int(req_data.get("start_q", 1))
            end_q = int(req_data.get("end_q", 20))
            state.action_queue.put({"action": "solve_range", "start_q": start_q, "end_q": end_q})
            self.send_json({"status": "queued"})
            return

        # 4. Giải theo URL
        if parsed.path == "/api/action/solve_url":
            if state.is_running:
                self.send_json({"error": "Đang có tác vụ đang chạy!"}, 400)
                return
            url = req_data.get("url", "").strip()
            state.action_queue.put({"action": "solve_url", "url": url})
            self.send_json({"status": "queued"})
            return

        # 5. Quét toàn bộ cấu trúc môn học
        if parsed.path == "/api/action/scan_course":
            result_q = queue.Queue()
            state.action_queue.put({"action": "scan_course", "result_queue": result_q})
            try:
                rows = result_q.get(timeout=30.0)
                self.send_json(rows)
            except queue.Empty:
                self.send_json([], 200)
            return

        # 6. Giải bài chỉ định / Chạy slide chỉ định
        if parsed.path == "/api/action/solve_specific":
            if state.is_running:
                self.send_json({"error": "Đang có tác vụ đang chạy!"}, 400)
                return
            title = req_data.get("title", "")
            target_type = req_data.get("target_type", "ai")
            state.action_queue.put({"action": "solve_specific", "title": title, "target_type": target_type})
            self.send_json({"status": "queued"})
            return

        # 7. Dừng tác vụ
        if parsed.path == "/api/action/stop":
            state.stop_requested = True
            state.broadcast_log("[STOP] Đã gửi lệnh dừng tác vụ!")
            self.send_json({"status": "stopping"})
            return

        # 8. Lưu cấu hình AI Coding CLI
        if parsed.path == "/api/config":
            new_provider = req_data.get("provider", state.ai_provider or "auto").strip().lower()
            new_model = req_data.get("model", state.ai_model or "gemini-3.8-flash-low").strip()
            new_effort = req_data.get("effort", "low").strip().lower()

            state.action_queue.put({
                "action": "update_config",
                "provider": new_provider,
                "model": new_model,
                "effort": new_effort
            })
            self.send_json({"status": "saved"})
            return

        self.send_error(404, "Not Found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/cache":
            state.action_queue.put({"action": "clear_cache"})
            self.send_json({"status": "clearing"})
            return
        self.send_error(404, "Not Found")


def start_web_server(port: int = 8765) -> ThreadingHTTPServer:
    """Khởi động HTTP Server chạy trong thread độc lập phục vụ Web Dashboard."""
    server = ThreadingHTTPServer(("127.0.0.1", port), WebDashboardHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server
