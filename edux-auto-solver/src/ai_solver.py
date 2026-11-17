import os
import re
import json
import time
import queue
import atexit
import tempfile
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable

from src.config import (
    AI_PROVIDER,
    AI_MODEL,
    AI_EFFORT,
    detect_available_ai_tools,
    infer_field
)
from src.utils import console
from src.storage import QuestionCache


def _reap_process_async(proc: Optional[subprocess.Popen]):
    """Đóng tiến trình CLI ngầm để không bao giờ chặn luồng chính (tránh chờ 5s Language Server tắt)."""
    if not proc:
        return

    def _reaper():
        try:
            if proc.stdin:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            proc.wait(timeout=1.5)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    threading.Thread(target=_reaper, daemon=True).start()


class _AgyStreamSession:
    """
    Phiên kết nối liên tục (Persistent Stream-JSON) với Google Antigravity CLI (`agy`).
    - Loại bỏ hoàn toàn 23-25s chi phí khởi tạo MCP/Plugin ở mỗi câu hỏi.
    - Sau khi khởi làm ấm (Warmup), mỗi lượt (hoặc mỗi Batch 8-10 câu) chỉ mất ~3.5 - 5 giây!
    """

    def __init__(self, agy_bin: str, model: str, effort: str, max_turns: int = 16):
        self.agy_bin = agy_bin
        self.model = model
        self.effort = effort if effort in ("low", "medium", "high") else "low"
        self.max_turns = max_turns

        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._line_queue: "queue.Queue[tuple]" = queue.Queue()
        self._turns = 0
        self._warmed = False
        self._warming = False

    def matches(self, agy_bin: str, model: str, effort: str) -> bool:
        norm_effort = effort if effort in ("low", "medium", "high") else "low"
        return (
            self.agy_bin == agy_bin
            and self.model == model
            and self.effort == norm_effort
        )

    def is_alive(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)

    def is_warm(self) -> bool:
        return self.is_alive() and self._warmed

    def _start_locked(self):
        if self.is_alive() and self._turns < self.max_turns:
            return
        if self._proc:
            _reap_process_async(self._proc)
            self._proc = None

        self._line_queue = queue.Queue()
        self._turns = 0
        self._warmed = False

        cmd = [
            self.agy_bin,
            "--disable-slash-commands",
            "--effort", self.effort,
            "--input-format", "stream-json",
            "--output-format", "stream-json",
        ]
        if self.model and not self.model.startswith("gpt-6") and self.model != "default":
            cmd.extend(["--model", self.model])

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd="/tmp",
            bufsize=1
        )
        self._proc = proc
        q_ref = self._line_queue

        def _stdout_reader():
            try:
                if proc.stdout:
                    for raw_line in proc.stdout:
                        q_ref.put(("line", raw_line))
            except Exception as err:
                q_ref.put(("err", str(err)))
            finally:
                q_ref.put(("eof", ""))

        threading.Thread(target=_stdout_reader, daemon=True).start()

    def prewarm_async(self):
        """Khởi động ngầm phiên Antigravity CLI ngay khi mở tool để đạt độ trễ 0s khi bấm Giải."""
        if self.is_warm() or self._warming:
            return

        def _warm_worker():
            if self.is_warm():
                return
            self._warming = True
            try:
                with self._lock:
                    if self.is_warm() or self._turns > 0:
                        return
                    self._start_locked()
                    self._send_turn_locked("Reply ONLY: OK", timeout=45.0)
            except Exception:
                pass
            finally:
                self._warming = False

        threading.Thread(target=_warm_worker, daemon=True).start()

    def _send_turn_locked(self, prompt: str, timeout: float = 55.0) -> str:
        if not self.is_alive():
            self._start_locked()

        assert self._proc is not None and self._proc.stdin is not None
        # Xóa các gói tin cũ còn sót (nếu có) trước khi gửi lượt mới
        while not self._line_queue.empty():
            try:
                self._line_queue.get_nowait()
            except queue.Empty:
                break

        payload = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
        try:
            self._proc.stdin.write(payload)
            self._proc.stdin.flush()
        except Exception as write_err:
            self.close()
            raise RuntimeError(f"Ghi dữ liệu vào phiên Antigravity thất bại: {write_err}")

        deadline = time.time() + timeout
        delta_chunks: List[str] = []

        while True:
            rem = deadline - time.time()
            if rem <= 0:
                self.close()
                raise TimeoutError(f"Phiên Antigravity CLI quá thời gian chờ ({timeout}s)")

            try:
                kind, data = self._line_queue.get(timeout=min(rem, 1.0))
            except queue.Empty:
                if not self.is_alive():
                    self.close()
                    raise RuntimeError("Tiến trình Antigravity CLI đã đóng đột ngột")
                continue

            if kind == "eof":
                self.close()
                if delta_chunks:
                    return "".join(delta_chunks).strip()
                raise RuntimeError("Luồng dữ liệu Antigravity CLI kết thúc sớm (EOF)")
            if kind == "err":
                self.close()
                raise RuntimeError(f"Lỗi đọc luồng Antigravity CLI: {data}")

            line = data.strip()
            if not line:
                continue

            try:
                ev = json.loads(line)
            except Exception:
                continue

            etype = ev.get("event")
            if etype == "step_update":
                su = ev.get("step_update") or {}
                if su.get("step_type") == "agent_response" and su.get("text_delta"):
                    delta_chunks.append(su["text_delta"])
            elif etype == "result":
                res = ev.get("result") or {}
                status = res.get("status", "")
                resp_text = (res.get("response") or "".join(delta_chunks)).strip()
                if status == "ERROR" and not resp_text:
                    err_msg = res.get("error") or "Lỗi không xác định từ Antigravity stream"
                    self.close()
                    raise RuntimeError(err_msg)
                self._turns += 1
                self._warmed = True
                return resp_text

    def ask(self, prompt: str, timeout: float = 55.0) -> str:
        with self._lock:
            if not self.is_alive() or self._turns >= self.max_turns:
                self._start_locked()
            return self._send_turn_locked(prompt, timeout=timeout)

    def close(self):
        proc = self._proc
        self._proc = None
        self._turns = 0
        self._warmed = False
        if proc:
            _reap_process_async(proc)


class AICodingSolver:
    """
    Bộ giải bài tập kết nối trực tiếp với các công cụ AI Coding trên máy:
    - Google Antigravity CLI (`agy`) [Hỗ trợ Persistent Stream-JSON + Batch Turbo]
    - OpenAI Codex CLI (`codex exec`) [Hỗ trợ Batch + Parallel Workers + Vision `-i`]
    - Claude Code CLI (`claude -p`)
    - OpenCode CLI (`opencode run`)
    Hoàn toàn KHÔNG cần API Key, tự động xoay vòng (fallback) và hỗ trợ đính kèm ảnh (Vision).
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        cache: Optional[QuestionCache] = None,
        api_key: Optional[str] = None,  # Giữ tham số để tương thích ngược
        auto_prewarm: bool = True,
    ):
        self.cache = cache or QuestionCache()
        self.available_tools = detect_available_ai_tools()
        self.provider = (provider or os.getenv("AI_PROVIDER", AI_PROVIDER) or "auto").strip().lower()
        self.active_model = (model or os.getenv("AI_MODEL", AI_MODEL) or "gemini-3.8-flash-low").strip()
        self.effort = (effort or os.getenv("AI_EFFORT", AI_EFFORT) or "low").strip().lower()
        self._agy_session: Optional[_AgyStreamSession] = None
        self._session_guard = threading.Lock()

        if not self.available_tools:
            console.print(
                "[bold yellow][!] Cảnh báo: Không tìm thấy công cụ AI Coding CLI (agy, codex, claude, opencode) trong PATH![/bold yellow]"
            )
        elif auto_prewarm:
            self.prewarm_async()

        atexit.register(self.close)

    def _get_agy_session(self) -> Optional[_AgyStreamSession]:
        agy_bin = self.available_tools.get("antigravity")
        if not agy_bin:
            return None
        with self._session_guard:
            if self._agy_session and not self._agy_session.matches(agy_bin, self.active_model, self.effort):
                self._agy_session.close()
                self._agy_session = None
            if not self._agy_session:
                self._agy_session = _AgyStreamSession(
                    agy_bin=agy_bin,
                    model=self.active_model,
                    effort=self.effort
                )
            return self._agy_session

    def prewarm_async(self):
        """Làm ấm sẵn phiên Antigravity CLI ở chế độ nền nếu đang được chọn."""
        if "antigravity" in self.available_tools and self.provider in ("auto", "antigravity"):
            sess = self._get_agy_session()
            if sess:
                sess.prewarm_async()

    def reconfigure(self, provider: str, model: str, effort: str):
        """Cập nhật cấu hình nóng và tự động khởi tạo lại phiên stream nếu đổi model/effort."""
        self.provider = (provider or "auto").strip().lower()
        self.active_model = (model or "gemini-3.8-flash-low").strip()
        self.effort = (effort or "low").strip().lower()
        self.available_tools = detect_available_ai_tools()
        self.prewarm_async()

    def close(self):
        """Đóng phiên stream ngầm an toàn khi thoát chương trình."""
        with self._session_guard:
            if self._agy_session:
                self._agy_session.close()
                self._agy_session = None

    def get_provider_order(self, has_image: bool = False) -> List[str]:
        """Xác định thứ tự ưu tiên các công cụ AI Coding CLI."""
        all_installed = [p for p in ["antigravity", "codex", "claude", "opencode"] if p in self.available_tools]
        if not all_installed:
            return []

        if self.provider != "auto" and self.provider in self.available_tools:
            ordered = [self.provider] + [p for p in all_installed if p != self.provider]
        else:
            ordered = list(all_installed)

        if has_image and self.provider == "auto" and "codex" in ordered and ordered[0] != "codex":
            ordered.remove("codex")
            ordered.insert(0, "codex")

        return ordered

    def get_status_summary(self) -> str:
        """Chuỗi mô tả trạng thái kết nối AI Coding CLI."""
        if not self.available_tools:
            return "Chưa cài CLI (Fallback Mode)"
        order = self.get_provider_order()
        primary = order[0] if order else "auto"
        tools_str = ", ".join(self.available_tools.keys())
        warm_tag = " · Turbo Stream" if primary == "antigravity" else " · Batch Parallel"
        return f"{primary.upper()} ({self.active_model}{warm_tag}) [Installed: {tools_str}]"

    def _call_antigravity(self, prompt: str, image_path: Optional[str] = None, timeout: float = 55.0) -> str:
        """
        Gọi Google Antigravity CLI (`agy`):
        - Câu hỏi văn bản: Đi qua Persistent Stream-JSON (~3.5s/lượt thay vì 28s).
        - Câu hỏi có ảnh đính kèm: Hỗ trợ fallback hoặc truyền đường dẫn ảnh.
        """
        agy_bin = self.available_tools["antigravity"]
        full_prompt = prompt
        if image_path:
            full_prompt = f"[HÌNH ẢNH ĐỀ BÀI ĐÍNH KÈM TẠI ĐƯỜNG DẪN: {image_path}]\n\n{prompt}"

        if not image_path:
            sess = self._get_agy_session()
            if sess:
                try:
                    return sess.ask(full_prompt, timeout=timeout)
                except Exception:
                    sess.close()

        cmd = [
            agy_bin,
            "--disable-slash-commands",
            "--effort", self.effort if self.effort in ["low", "medium", "high"] else "low",
        ]
        if self.active_model and not self.active_model.startswith("gpt-6") and self.active_model != "default":
            cmd.extend(["--model", self.active_model])

        cmd.append(f"-p={full_prompt}")

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(timeout),
            cwd="/tmp"
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            raise RuntimeError(f"Antigravity CLI lỗi (code {proc.returncode}): {proc.stderr.strip()}")
        return proc.stdout.strip()

    def _call_codex(self, prompt: str, image_path: Optional[str] = None, timeout: float = 60.0) -> str:
        """Gọi OpenAI Codex CLI (`codex exec`) ở chế độ non-interactive, hỗ trợ Vision `-i`."""
        codex_bin = self.available_tools["codex"]
        with tempfile.NamedTemporaryFile(prefix="edux_codex_", suffix=".json", delete=False) as tf:
            out_path = tf.name

        try:
            cmd = [
                codex_bin,
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "-c", f'model_reasoning_effort="{self.effort if self.effort in ["low", "medium", "high"] else "low"}"',
                "-o", out_path,
            ]
            if self.active_model and (
                self.active_model.startswith("gpt-")
                or self.active_model.startswith("o1")
                or self.active_model.startswith("o3")
                or self.active_model.startswith("o4")
                or self.active_model.startswith("codex")
            ):
                cmd.extend(["-m", self.active_model])

            if image_path and os.path.exists(image_path):
                cmd.extend(["-i", image_path])

            cmd.append(prompt)

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=int(timeout),
                cwd="/tmp"
            )
            if os.path.exists(out_path):
                content = Path(out_path).read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    return content

            if proc.returncode != 0:
                raise RuntimeError(f"Codex CLI lỗi (code {proc.returncode}): {proc.stderr.strip()}")
            return proc.stdout.strip()
        finally:
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except Exception:
                pass

    def _call_claude(self, prompt: str, image_path: Optional[str] = None, timeout: float = 45.0) -> str:
        """Gọi Claude Code CLI (`claude -p`)."""
        claude_bin = self.available_tools["claude"]
        full_prompt = prompt
        if image_path:
            full_prompt = f"[File ảnh câu hỏi: {image_path}]\n\n{prompt}"

        cmd = [claude_bin, "-p", full_prompt]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(timeout),
            cwd="/tmp"
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            raise RuntimeError(f"Claude CLI lỗi (code {proc.returncode}): {proc.stderr.strip()}")
        return proc.stdout.strip()

    def _call_opencode(self, prompt: str, image_path: Optional[str] = None, timeout: float = 45.0) -> str:
        """Gọi OpenCode CLI (`opencode run`)."""
        opencode_bin = self.available_tools["opencode"]
        cmd = [opencode_bin, "run", prompt]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(timeout),
            cwd="/tmp"
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            raise RuntimeError(f"OpenCode CLI lỗi (code {proc.returncode}): {proc.stderr.strip()}")
        return proc.stdout.strip()

    def _invoke_provider(self, prov: str, prompt: str, image_path: Optional[str] = None, timeout: float = 55.0) -> str:
        if prov == "antigravity":
            return self._call_antigravity(prompt, image_path=image_path, timeout=timeout)
        if prov == "codex":
            return self._call_codex(prompt, image_path=image_path, timeout=timeout)
        if prov == "claude":
            return self._call_claude(prompt, image_path=image_path, timeout=timeout)
        if prov == "opencode":
            return self._call_opencode(prompt, image_path=image_path, timeout=timeout)
        raise ValueError(f"Provider không hợp lệ: {prov}")

    @staticmethod
    def _normalize_tf_label(val: Any) -> str:
        s = str(val or "").strip().lower()
        if s in ("đúng", "dung", "d", "true", "t", "1", "yes"):
            return "Đúng"
        return "Sai"

    def _normalize_single_answer(self, q_data: Dict[str, Any], parsed_json: Dict[str, Any], prov: str) -> Dict[str, Any]:
        q_type = q_data.get("type", "choice")
        options = q_data.get("options", [])
        sub_statements = q_data.get("sub_statements", [])

        out: Dict[str, Any] = dict(parsed_json)
        if "r" in out and "reasoning" not in out:
            out["reasoning"] = out.pop("r")

        if q_type == "multi_true_false" or sub_statements:
            out["question_type"] = "multi_true_false"
            expected_len = max(len(sub_statements), 4)
            subs = out.get("sub_answers") or []
            if isinstance(subs, list) and len(subs) >= len(sub_statements) and len(subs) > 0:
                out["sub_answers"] = [self._normalize_tf_label(x) for x in subs[:expected_len]]
            else:
                out["sub_answers"] = ["Đúng", "Sai", "Đúng", "Sai"][:expected_len]
        elif q_type == "text" or q_data.get("has_text_input"):
            out["question_type"] = "text"
            txt = str(out.get("text_answer") or "").strip()
            out["text_answer"] = txt if txt else "Hoàn thành"
        else:
            out["question_type"] = "choice"
            raw_opts = out.get("selected_options") or []
            if isinstance(raw_opts, str):
                raw_opts = [raw_opts]
            valid_prefixes = {str(o.get("prefix", "")).strip().upper(): str(o.get("prefix", "")).strip() for o in options if isinstance(o, dict)}
            cleaned_opts = []
            for ro in raw_opts:
                key = str(ro).strip().rstrip(".)").strip().upper()
                if key in ("DUNG", "ĐÚNG", "TRUE"):
                    key = "ĐÚNG"
                elif key in ("SAI", "FALSE"):
                    key = "SAI"
                if valid_prefixes and key in valid_prefixes:
                    cleaned_opts.append(valid_prefixes[key])
                elif key:
                    cleaned_opts.append(key if len(key) <= 2 else str(ro).strip())
            if not cleaned_opts:
                cleaned_opts = [options[0]["prefix"]] if options else ["A"]
            out["selected_options"] = cleaned_opts

        out["provider"] = prov
        return out

    def _make_fallback_answer(self, q_data: Dict[str, Any]) -> Dict[str, Any]:
        q_type = q_data.get("type", "choice")
        options = q_data.get("options", [])
        sub_statements = q_data.get("sub_statements", [])

        if q_type == "multi_true_false" or sub_statements:
            return {
                "question_type": "multi_true_false",
                "sub_answers": ["Đúng", "Sai", "Đúng", "Sai"][: max(len(sub_statements), 4)],
                "reasoning": "Fallback an toàn do CLI bận"
            }
        if q_type == "text" or q_data.get("has_text_input"):
            return {
                "question_type": "text",
                "text_answer": "Hoàn thành",
                "reasoning": "Fallback an toàn do CLI bận"
            }
        default_opt = options[0]["prefix"] if options else "A"
        return {
            "question_type": "choice",
            "selected_options": [default_opt],
            "reasoning": "Fallback an toàn do CLI bận"
        }

    def _build_batch_prompt(
        self,
        batch_questions: List[Dict[str, Any]],
        subject_name: str,
        chapter_name: str
    ) -> str:
        field = infer_field(subject_name)
        blocks = []

        for q in batch_questions:
            q_num = q.get("q_num", 1)
            q_type = q.get("type", "choice")
            prompt_text = q.get("prompt", "")
            options = q.get("options", [])
            sub_statements = q.get("sub_statements", [])

            if q_type == "multi_true_false" or sub_statements:
                st_lines = "\n".join(
                    f"  {s.get('index', i + 1)}. {s.get('text', '')}"
                    for i, s in enumerate(sub_statements)
                )
                blocks.append(
                    f"[Q{q_num}] TYPE=multi_true_false ({len(sub_statements) or 4} mệnh đề Đúng/Sai)\n"
                    f"ĐỀ: {prompt_text}\n"
                    f"MỆNH ĐỀ:\n{st_lines}"
                )
            elif q_type == "text" or q.get("has_text_input"):
                blocks.append(
                    f"[Q{q_num}] TYPE=text (Tự luận / Điền từ)\n"
                    f"ĐỀ: {prompt_text}"
                )
            else:
                opt_lines = "\n".join(
                    f"  {opt.get('prefix')}. {opt.get('text')}"
                    for opt in options
                ) or "  (Không có phương án)"
                blocks.append(
                    f"[Q{q_num}] TYPE=choice (Trắc nghiệm)\n"
                    f"ĐỀ: {prompt_text}\n"
                    f"PHƯƠNG ÁN:\n{opt_lines}"
                )

        joined_blocks = "\n\n".join(blocks)
        return (
            f"Bạn là Chuyên gia hàng đầu về {field}.\n"
            f"Môn học: {subject_name} | Bài: {chapter_name}\n"
            f"Nhiệm vụ: Giải chính xác tuyệt đối 10/10 tất cả {len(batch_questions)} câu hỏi dưới đây.\n"
            f"QUY TẮC BẮT BUỘC: CHỈ TRẢ VỀ DUY NHẤT 1 MẢNG JSON HỢP LỆ, KHÔNG DÙNG TOOL, KHÔNG VIẾT BẤT KỲ CHỮ NÀO NGOÀI MẢNG JSON.\n"
            f"Cấu trúc phần tử trong mảng JSON theo từng TYPE:\n"
            f'- Với TYPE=choice: {{"q": <số_câu>, "r": "<giải thích <=8 từ>", "selected_options": ["A"]}}\n'
            f'- Với TYPE=multi_true_false: {{"q": <số_câu>, "r": "<giải thích <=8 từ>", "sub_answers": ["Đúng", "Sai", "Đúng", "Sai"]}}\n'
            f'- Với TYPE=text: {{"q": <số_câu>, "r": "<giải thích <=8 từ>", "text_answer": "<câu trả lời ngắn gọn, đầy đủ ý cốt lõi>"}}\n\n'
            f"{joined_blocks}"
        )

    def _parse_batch_json_response(self, text: str) -> Dict[int, Dict[str, Any]]:
        if not text:
            raise ValueError("Phản hồi batch rỗng từ AI CLI")

        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

        arr = None
        try:
            loaded = json.loads(cleaned)
            if isinstance(loaded, list):
                arr = loaded
            elif isinstance(loaded, dict):
                for k in ("answers", "results", "items", "questions", "data"):
                    if isinstance(loaded.get(k), list):
                        arr = loaded[k]
                        break
                if arr is None and "q" in loaded:
                    arr = [loaded]
        except Exception:
            pass

        if arr is None:
            m = re.search(r"(\[\s*\{.*\}\s*\])", cleaned, re.DOTALL)
            if m:
                arr = json.loads(m.group(1))

        if not isinstance(arr, list):
            raise ValueError(f"Không thể phân tích mảng JSON từ phản hồi batch: {text[:200]}")

        mapped: Dict[int, Dict[str, Any]] = {}
        for item in arr:
            if not isinstance(item, dict):
                continue
            raw_q = item.get("q") or item.get("q_num") or item.get("id")
            if raw_q is None:
                continue
            try:
                q_num = int(re.sub(r"\D+", "", str(raw_q)))
                mapped[q_num] = item
            except Exception:
                continue
        return mapped

    def _solve_one_batch(
        self,
        batch_questions: List[Dict[str, Any]],
        subject_name: str,
        chapter_name: str
    ) -> Dict[int, Dict[str, Any]]:
        """Giải 1 lô câu hỏi văn bản qua AI CLI, tự động fallback nếu thiếu câu."""
        if not batch_questions:
            return {}
        if len(batch_questions) == 1:
            q = batch_questions[0]
            return {q["q_num"]: self.solve(q, subject_name=subject_name, chapter_name=chapter_name)}

        prompt = self._build_batch_prompt(batch_questions, subject_name=subject_name, chapter_name=chapter_name)
        providers = self.get_provider_order(has_image=False)

        batch_results: Dict[int, Dict[str, Any]] = {}
        used_prov = providers[0] if providers else "auto"

        for prov in providers:
            try:
                raw_text = self._invoke_provider(prov, prompt, image_path=None, timeout=65.0)
                parsed_map = self._parse_batch_json_response(raw_text)
                if parsed_map:
                    used_prov = prov
                    cache_batch = []
                    for q in batch_questions:
                        q_num = q["q_num"]
                        raw_item = parsed_map.get(q_num)
                        if raw_item and any(k in raw_item for k in ("selected_options", "sub_answers", "text_answer")):
                            norm_ans = self._normalize_single_answer(q, raw_item, prov=used_prov)
                            batch_results[q_num] = norm_ans
                            cache_batch.append({
                                "prompt": q.get("prompt", ""),
                                "options": q.get("options") or q.get("sub_statements") or [],
                                "q_type": q.get("type", "choice"),
                                "answer": norm_ans,
                                "subject": subject_name
                            })
                    if cache_batch:
                        self.cache.store_answers_batch(cache_batch, subject=subject_name)
                    if len(batch_results) >= len(batch_questions):
                        return batch_results
                    break
            except Exception:
                continue

        # Giải bù từng câu nếu có câu bị thiếu trong phản hồi batch
        for q in batch_questions:
            q_num = q["q_num"]
            if q_num not in batch_results:
                batch_results[q_num] = self.solve(q, subject_name=subject_name, chapter_name=chapter_name)

        return batch_results

    def solve_batch(
        self,
        questions: List[Dict[str, Any]],
        subject_name: str = "",
        chapter_name: str = "",
        batch_size: int = 8,
        on_batch_done: Optional[Callable[[Dict[int, Dict[str, Any]]], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[int, Dict[str, Any]]:
        """
        Giải hàng loạt danh sách câu hỏi tốc độ cao:
        1. Lấy ngay từ QuestionCache (0s) cho các câu đã có trong ngân hàng đề.
        2. Chạy song song các câu hỏi có ảnh (Vision) trên luồng riêng.
        3. Gom các câu văn bản thành từng lô (Batch 8 câu) qua phiên Warm Stream-JSON hoặc Parallel CLI,
           gọi callback `on_batch_done` ngay khi mỗi lô hoàn tất để điền đáp án tức thì lên trình duyệt.
        """
        all_results: Dict[int, Dict[str, Any]] = {}
        uncached_text_qs: List[Dict[str, Any]] = []
        image_qs: List[Dict[str, Any]] = []

        cached_ready: Dict[int, Dict[str, Any]] = {}
        for q in questions:
            q_num = q.get("q_num", 1)
            q_type = q.get("type", "choice")
            prompt_text = q.get("prompt", "")
            options = q.get("options", [])
            sub_statements = q.get("sub_statements", [])
            screenshot_bytes = q.get("screenshot_bytes")

            if screenshot_bytes:
                image_qs.append(q)
                continue

            cached_ans = self.cache.get_answer(
                prompt=prompt_text,
                options=options or sub_statements,
                q_type=q_type
            )
            if cached_ans:
                ans_copy = dict(cached_ans)
                ans_copy["cached"] = True
                all_results[q_num] = ans_copy
                cached_ready[q_num] = ans_copy
            else:
                uncached_text_qs.append(q)

        if cached_ready and on_batch_done:
            on_batch_done(cached_ready)

        if not uncached_text_qs and not image_qs:
            return all_results

        # Chia lô thông minh: nếu lô có câu tự luận (text) thì gom tối đa 4 câu/lô để câu trả lời chi tiết
        batches: List[List[Dict[str, Any]]] = []
        current_batch: List[Dict[str, Any]] = []
        current_limit = batch_size

        for q in uncached_text_qs:
            is_text_q = (q.get("type") == "text" or q.get("has_text_input"))
            if is_text_q:
                current_limit = min(current_limit, 4)
            current_batch.append(q)
            if len(current_batch) >= current_limit:
                batches.append(current_batch)
                current_batch = []
                current_limit = batch_size
        if current_batch:
            batches.append(current_batch)

        providers = self.get_provider_order(has_image=False)
        primary_prov = providers[0] if providers else "auto"

        # Chạy song song câu hỏi hình ảnh (Vision) nếu có
        vision_pool: Optional[ThreadPoolExecutor] = None
        vision_futures = {}
        if image_qs:
            vision_pool = ThreadPoolExecutor(max_workers=min(2, len(image_qs)))
            for iq in image_qs:
                fut = vision_pool.submit(self.solve, iq, subject_name, chapter_name)
                vision_futures[fut] = iq["q_num"]

        try:
            # Nếu dùng CLI không trạng thái (codex/claude/opencode) và có nhiều batch -> chạy song song 2 worker
            if primary_prov != "antigravity" and len(batches) > 1:
                with ThreadPoolExecutor(max_workers=min(2, len(batches))) as pool:
                    fut_map = {
                        pool.submit(self._solve_one_batch, b, subject_name, chapter_name): b
                        for b in batches
                    }
                    for fut in as_completed(fut_map):
                        if should_stop and should_stop():
                            break
                        b_res = fut.result()
                        all_results.update(b_res)
                        if on_batch_done and b_res:
                            on_batch_done(b_res)
            else:
                # Với Antigravity Stream-JSON đã làm ấm: chạy tuần tự từng batch trên cùng 1 phiên mở sẵn (~4s/batch)
                for b in batches:
                    if should_stop and should_stop():
                        break
                    b_res = self._solve_one_batch(b, subject_name=subject_name, chapter_name=chapter_name)
                    all_results.update(b_res)
                    if on_batch_done and b_res:
                        on_batch_done(b_res)

            # Thu hoạch kết quả Vision
            for fut in as_completed(vision_futures):
                if should_stop and should_stop():
                    break
                q_num = vision_futures[fut]
                try:
                    v_ans = fut.result()
                except Exception:
                    v_ans = self._make_fallback_answer(next(x for x in image_qs if x["q_num"] == q_num))
                all_results[q_num] = v_ans
                if on_batch_done:
                    on_batch_done({q_num: v_ans})
        finally:
            if vision_pool:
                vision_pool.shutdown(wait=False)

        return all_results

    def solve(self, question_data: Dict[str, Any], subject_name: str = "", chapter_name: str = "") -> Dict[str, Any]:
        """
        Giải 1 câu hỏi qua Công cụ AI Coding CLI (Antigravity / Codex / Claude / OpenCode)
        với Question Cache (0s), Persistent Stream-JSON và hỗ trợ hình ảnh (Vision).
        """
        q_num = question_data.get("q_num", 1)
        q_type = question_data.get("type", "choice")
        prompt_text = question_data.get("prompt", "")
        options = question_data.get("options", [])
        sub_statements = question_data.get("sub_statements", [])
        screenshot_bytes = question_data.get("screenshot_bytes")

        # 1. Kiểm tra Cache trong ngân hàng đề (nếu câu hỏi thuần văn bản)
        if not screenshot_bytes:
            cached_ans = self.cache.get_answer(
                prompt=prompt_text,
                options=options or sub_statements,
                q_type=q_type
            )
            if cached_ans:
                console.print(
                    "[bold green][CACHE HIT] Đã tìm thấy đáp án trong ngân hàng đề! Lấy ngay lập tức (0s).[/bold green]"
                )
                return cached_ans

        # 2. Xây dựng Prompt chuyên sâu
        field = infer_field(subject_name)
        has_image = bool(screenshot_bytes)

        header_instruction = (
            f"Bạn là Chuyên gia hàng đầu về {field}.\n"
            f"Nhiệm vụ: Giải bài tập đại học trên hệ thống LMS với độ chính xác tuyệt đối 10/10.\n"
            f"QUAN TRỌNG: CHỈ TRẢ VỀ DUY NHẤT 1 KHỐI JSON HỢP LỆ, KHÔNG GIẢI THÍCH DÀI DÒNG BÊN NGOÀI JSON, KHÔNG DÙNG TOOL."
        )

        if q_type == "multi_true_false" or sub_statements:
            st_text = "\n".join([f"{s.get('index', i+1)}. {s.get('text', '')}" for i, s in enumerate(sub_statements)])
            user_content = f"""{header_instruction}

MÔN HỌC: {subject_name} | CHƯƠNG: {chapter_name} | CÂU {q_num}
THỂ LOẠI: ĐÚNG / SAI (4 mệnh đề con)
{'(LƯU Ý: Quan sát hình ảnh minh họa đính kèm để trả lời)' if has_image else ''}

ĐỀ BÀI:
\"\"\"{prompt_text}\"\"\"

DANH SÁCH MỆNH ĐỀ CẦN ĐÁNH GIÁ ĐÚNG HOẶC SAI:
{st_text}

YÊU CẦU:
Phân tích kỹ từng mệnh đề (1, 2, 3, 4) dựa trên kiến thức chuẩn của học phần {subject_name} trước khi kết luận "Đúng" hoặc "Sai".
Trả về ĐÚNG cấu trúc JSON sau:
{{
  "question_type": "multi_true_false",
  "reasoning": "Phân tích ngắn gọn từng ý 1, 2, 3, 4 vì sao Đúng/Sai.",
  "sub_answers": ["Đúng", "Sai", "Đúng", "Sai"]
}}"""
        elif q_type == "text" or question_data.get("has_text_input"):
            user_content = f"""{header_instruction}

MÔN HỌC: {subject_name} | CHƯƠNG: {chapter_name} | CÂU {q_num}
THỂ LOẠI: TỰ LUẬN / ĐIỀN TỪ
{'(LƯU Ý: Quan sát hình ảnh minh họa đính kèm để trả lời)' if has_image else ''}

ĐỀ BÀI:
\"\"\"{prompt_text}\"\"\"

YÊU CẦU:
Trả lời chính xác, đầy đủ các ý cốt lõi, đúng thuật ngữ chuyên ngành của môn {subject_name}.
Trả về ĐÚNG cấu trúc JSON sau:
{{
  "question_type": "text",
  "reasoning": "Ý chính cần trình bày.",
  "text_answer": "Câu trả lời đầy đủ, rõ ràng điền vào ô"
}}"""
        else:
            options_formatted = (
                "\n".join([f"- {opt['prefix']}. {opt['text']}" for opt in options])
                if options
                else "(Không có options)"
            )
            user_content = f"""{header_instruction}

MÔN HỌC: {subject_name} | CHƯƠNG: {chapter_name} | CÂU {q_num}
THỂ LOẠI: TRẮC NGHIỆM
{'(LƯU Ý: Quan sát hình ảnh minh họa đính kèm để trả lời)' if has_image else ''}

ĐỀ BÀI:
\"\"\"{prompt_text}\"\"\"

DANH SÁCH PHƯƠNG ÁN:
{options_formatted}

YÊU CẦU:
Đọc kỹ câu hỏi và đối chiếu từng phương án A, B, C, D để chọn đáp án chính xác nhất (loại trừ các phương án bẫy).
Trả về ĐÚNG cấu trúc JSON sau:
{{
  "question_type": "choice",
  "reasoning": "Giải thích ngắn gọn vì sao phương án này đúng và các phương án khác sai.",
  "selected_options": ["A"]
}}"""

        temp_img_path = None
        if screenshot_bytes:
            try:
                with tempfile.NamedTemporaryFile(prefix="edux_vision_", suffix=".png", delete=False) as img_f:
                    img_f.write(screenshot_bytes)
                    temp_img_path = img_f.name
            except Exception:
                temp_img_path = None

        last_error = None
        providers = self.get_provider_order(has_image=has_image)

        try:
            for prov in providers:
                for attempt in range(2):
                    try:
                        raw_text = self._invoke_provider(prov, user_content, image_path=temp_img_path, timeout=50.0)
                        parsed_json = self._parse_json_response(raw_text)
                        norm_ans = self._normalize_single_answer(question_data, parsed_json, prov=prov)

                        self.cache.store_answer(
                            prompt=prompt_text,
                            options=options or sub_statements,
                            q_type=q_type,
                            answer=norm_ans,
                            subject=subject_name
                        )
                        return norm_ans
                    except Exception as e:
                        last_error = e
                        time.sleep(0.25)
                        continue
        finally:
            if temp_img_path and os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except Exception:
                    pass

        console.print(
            f"[yellow][!] Công cụ AI Coding CLI gặp lỗi ({last_error}), sử dụng fallback mặc định an toàn.[/yellow]"
        )
        return self._make_fallback_answer(question_data)

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        if not text:
            raise ValueError("Phản hồi rỗng từ AI CLI")
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
        try:
            res = json.loads(cleaned)
            if isinstance(res, list) and res and isinstance(res[0], dict):
                return res[0]
            if isinstance(res, dict):
                return res
        except Exception:
            pass

        matches = list(re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL))
        for m in reversed(matches):
            try:
                candidate = json.loads(m.group(0))
                if isinstance(candidate, dict) and any(
                    k in candidate for k in ["selected_options", "sub_answers", "text_answer", "question_type"]
                ):
                    return candidate
            except Exception:
                continue
        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"Không thể phân tích JSON từ phản hồi: {text[:200]}")


# Alias giữ tương thích ngược hoàn toàn với toàn bộ codebase
GeminiSolver = AICodingSolver

