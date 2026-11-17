import json
import hashlib
import re
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from src.config import CACHE_FILE
from src.utils import console


class QuestionCache:
    """
    Ngan hang cau hoi & Cache ket qua giai thong minh.
    Luu tru cau hoi va dap an de tai su dung ngay lap tuc (0s latency, 0 token cost).
    Ho tro ghi theo lo (batch flush) va thread-safe cho che do giai song song.
    """
    INVALID_PROMPT_PATTERNS = (
        "cau hoi chua lam",
        " thời gian còn lại",
        "thoi gian con lai",
        "danh sach cau hoi",
    )

    def __init__(self, cache_path: Path = CACHE_FILE):
        self.cache_path = Path(cache_path)
        self.memory_cache: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._dirty = False
        self._load_cache()

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        # Xoa ky tu dac biet, dua ve chu thuong va gop khoang trang
        cleaned = re.sub(r"\s+", " ", text).strip().lower()
        cleaned = re.sub(r"[^\w\s]", "", cleaned)
        return cleaned

    def _is_valid_prompt(self, prompt: str) -> bool:
        if not prompt or not prompt.strip():
            return False
        s = prompt.strip()
        low = s.lower()
        if low.startswith("câu hỏi chưa làm") or low.startswith("cau hoi chua lam"):
            return False
        if s.endswith("...") or s.endswith("…"):
            return False
        if re.match(r"^câu\s*\d+\s*$", low):
            return False
        norm = self._normalize_text(prompt)
        if len(norm) < 4:
            return False
        for bad in self.INVALID_PROMPT_PATTERNS:
            if norm.startswith(bad.strip()):
                return False
        return True

    def _make_key(self, prompt: str, options: list = None, q_type: str = "choice") -> str:
        norm_prompt = self._normalize_text(prompt)
        opts_str = ""
        if options:
            opts_norm = [self._normalize_text(opt.get("text", "")) for opt in options if isinstance(opt, dict)]
            opts_str = "_".join(sorted(opts_norm))
        raw_key = f"{q_type}|{norm_prompt}|{opts_str}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _load_cache(self):
        with self._lock:
            if not self.cache_path.exists():
                self.memory_cache = {}
                return
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Loc bo cac muc loi do UI "Cau hoi chua lam" tu phien cu
                self.memory_cache = {
                    k: v for k, v in data.items()
                    if isinstance(v, dict) and self._is_valid_prompt(v.get("prompt", ""))
                }
            except Exception as e:
                console.print(f"[yellow][!] Khong the doc file cache ({e}), khoi tao bo nho cache moi.[/yellow]")
                self.memory_cache = {}

    def _save_cache(self):
        with self._lock:
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = self.cache_path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self.memory_cache, f, ensure_ascii=False, indent=2)
                tmp_path.replace(self.cache_path)
                self._dirty = False
            except Exception as e:
                console.print(f"[red][X] Loi khi ghi cache: {e}[/red]")

    def flush(self):
        """Ghi xuong dia neu co du lieu moi chua luu (batch save)."""
        with self._lock:
            if self._dirty:
                self._save_cache()

    def get_answer(self, prompt: str, options: list = None, q_type: str = "choice") -> Optional[Dict[str, Any]]:
        """Lay dap an da duoc cache neu co."""
        if not self._is_valid_prompt(prompt):
            return None
        key = self._make_key(prompt, options, q_type)
        with self._lock:
            item = self.memory_cache.get(key)
            if item:
                return item.get("answer")
        return None

    def store_answer(
        self,
        prompt: str,
        options: list,
        q_type: str,
        answer: Dict[str, Any],
        subject: str = "",
        score: float = 10.0,
        save: bool = True
    ):
        """Luu dap an vao bo nho cache (ho tro defer save khi chay batch)."""
        if not self._is_valid_prompt(prompt):
            return
        key = self._make_key(prompt, options, q_type)
        with self._lock:
            self.memory_cache[key] = {
                "key": key,
                "prompt": prompt,
                "q_type": q_type,
                "options": options,
                "answer": answer,
                "subject": subject,
                "score": score,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self._dirty = True
            if save:
                self._save_cache()

    def store_answers_batch(self, items: List[Dict[str, Any]], subject: str = ""):
        """Luu nhieu dap an cung luc va chi ghi file JSON 1 lan duy nhat."""
        if not items:
            return
        with self._lock:
            for it in items:
                self.store_answer(
                    prompt=it.get("prompt", ""),
                    options=it.get("options") or [],
                    q_type=it.get("q_type", "choice"),
                    answer=it.get("answer", {}),
                    subject=it.get("subject", subject),
                    save=False
                )
            self.flush()

    def get_stats(self) -> Dict[str, Any]:
        """Thong ke tong so cau hoi trong ngan hang de."""
        with self._lock:
            return {
                "total_questions": len(self.memory_cache),
                "cache_file": str(self.cache_path)
            }

    def clear(self):
        """Xoa toan bo cache."""
        with self._lock:
            self.memory_cache = {}
            self._save_cache()

