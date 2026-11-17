import sys
import unicodedata
from typing import Any
from urllib.parse import urlparse
from rich.console import Console

# Cau hinh bang ma UTF-8 cho Windows Console de tranh loi ky tu
if sys.platform.startswith("win"):
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console()

EMOJI_MAP = {
    '⚠️': '[!]',
    '⚠': '[!]',
    '❌': '[X]',
    '✔': '[OK]',
    '✅': '[OK]',
    '🔌': '[+]',
    '🔍': '[*]',
    '📋': '==',
    '📚': '==',
    '👉': '>',
    '🔗': 'Link:',
    '🎉': '[OK]',
    '🤖': '[AI]',
    '💡': '[Note]',
    '⏳': '[..]',
    '🏁': '[XONG]',
    '📤': '[1]',
    '👁️': '[2]',
    '🔙': '[3]',
    '🔐': '[AUTH]',
    '📊': '[INFO]',
    '🚀': '[START]',
    '📝': '[TASK]',
    '•': '-',
}

VIETNAMESE_MAP = {
    'à':'a','á':'a','ả':'a','ã':'a','ạ':'a','ă':'a','ằ':'a','ắ':'a','ẳ':'a','ẵ':'a','ặ':'a','â':'a','ầ':'a','ấ':'a','ẩ':'a','ẫ':'a','ậ':'a',
    'À':'A','Á':'A','Ả':'A','Ã':'A','Ạ':'A','Ă':'A','Ằ':'A','Ắ':'A','Ẳ':'A','Ẵ':'A','Ặ':'A','Â':'A','Ầ':'A','Ấ':'A','Ẩ':'A','Ẫ':'A','Ậ':'A',
    'è':'e','é':'e','ẻ':'e','ẽ':'e','ẹ':'e','ê':'e','ề':'e','ế':'e','ể':'e','ễ':'e','ệ':'e',
    'È':'E','É':'E','Ẻ':'E','Ẽ':'E','Ẹ':'E','Ê':'E','Ề':'E','Ế':'E','Ể':'E','Ễ':'E','Ệ':'E',
    'ì':'i','í':'i','ỉ':'i','ĩ':'i','ị':'i',
    'Ì':'I','Í':'I','Ỉ':'I','Ĩ':'I','Ị':'I',
    'ò':'o','ó':'o','ỏ':'o','õ':'o','ọ':'o','ô':'o','ồ':'o','ố':'o','ổ':'o','ỗ':'o','ộ':'o','ơ':'o','ờ':'o','ớ':'o','ở':'o','Ỡ':'o','ợ':'o',
    'Ò':'O','Ó':'O','Ỏ':'O','Õ':'O','Ọ':'O','Ô':'O','Ồ':'O','Ố':'O','Ổ':'O','Ỗ':'O','Ộ':'O','Ơ':'O','Ờ':'O','Ớ':'O','Ở':'O','Ỡ':'O','Ợ':'O',
    'ù':'u','ú':'u','ủ':'u','ũ':'u','ụ':'u','ư':'u','ừ':'u','ứ':'u','ử':'u','ữ':'u','ự':'u',
    'Ù':'U','Ú':'U','Ủ':'U','Ũ':'U','Ụ':'U','Ư':'U','Ừ':'U','Ứ':'U','Ử':'U','Ữ':'U','Ự':'U',
    'ỳ':'y','ý':'y','ỷ':'y','ỹ':'y','ỵ':'y',
    'Ỳ':'Y','Ý':'Y','Ỷ':'Y','Ỹ':'Y','Ỵ':'Y',
    'đ':'d','Đ':'D'
}

def to_clean_ascii(text: Any) -> str:
    """Chuyen chuoi tieng Viet co dau va emoji thanh ASCII sach de hien thi chuan tren PowerShell."""
    if text is None:
        return ""
    text = str(text)
    for emo, rep in EMOJI_MAP.items():
        text = text.replace(emo, rep)

    res = ''.join(VIETNAMESE_MAP.get(c, c) for c in text)
    res = unicodedata.normalize('NFKD', res)
    res = ''.join(c for c in res if unicodedata.category(c) != 'Mn')
    
    out = []
    for c in res:
        if ord(c) < 128:
            out.append(c)
        else:
            if c in ['“', '”']:
                out.append('"')
            elif c in ['‘', '’']:
                out.append("'")
            elif c in ['–', '—']:
                out.append('-')
            elif c == '…':
                out.append('...')
            elif c == '•':
                out.append('-')
            else:
                out.append(' ')
    return ''.join(out)

def is_allowed_domain(url: str, allowed_domains: list) -> bool:
    """Kiem tra xem URL co nam trong whitelist domain an toan hay khong."""
    if not url or url.startswith("about:") or url.startswith("chrome:"):
        return True
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not host:
            return True
        for domain in allowed_domains:
            if host == domain or host.endswith("." + domain):
                return True
        return False
    except Exception:
        return False

def cleanup_chrome_cache_safe(profile_dir: str):
    """
    Tu dong don sach cache web tam thoi va cac file rac cua Chrome khi thoat.
    Bao ton 100% Cookies, Local Storage va phien dang nhap truong CMCU.
    """
    import os
    import shutil
    from pathlib import Path

    p_path = Path(profile_dir)
    if not p_path.exists():
        return

    junk_relative_paths = [
        "OptGuideOnDeviceModel",
        "optimization_guide_model_store",
        "component_crx_cache",
        "WasmTtsEngine",
        "GrShaderCache",
        "BrowserMetrics",
        "OnDeviceHeadSuggestModel",
        "ActorSafetyLists",
        "hyphen-data",
        "ZxcvbnData",
        "OptimizationHints",
        "ShaderCache",
        os.path.join("Default", "Cache"),
        os.path.join("Default", "Code Cache"),
        os.path.join("Default", "GPUCache"),
        os.path.join("Default", "GrShaderCache"),
        os.path.join("Default", "DawnWebGPUCache"),
        os.path.join("Default", "DawnGraphiteCache"),
        os.path.join("Default", "Sessions"),
    ]

    for rel in junk_relative_paths:
        if rel in ["OptGuideOnDeviceModel", "OptGuidePredictionModels"]:
            continue
        target = p_path / rel
        if target.exists():
            try:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
            except Exception:
                pass

    # Duy tri vinh vien file khoa chan OptGuide khong cho Chrome tai model 4GB
    for block_name in ["OptGuideOnDeviceModel", "OptGuidePredictionModels"]:
        block_path = p_path / block_name
        if block_path.is_dir():
            shutil.rmtree(block_path, ignore_errors=True)
        if not block_path.exists():
            try:
                block_path.touch(exist_ok=True)
                os.chmod(block_path, 0o444)
            except Exception:
                pass
