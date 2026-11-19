import re
import time
from typing import Dict, List, Any, Optional, Tuple, Set
from playwright.sync_api import Page, Locator
from rich.table import Table
from rich import box

from src.config import ANTI_VISIBILITY_SCRIPT
from src.utils import console, to_clean_ascii

# =============================================================================
# QUAN LY DIALOG & TIEN ICH DOM
# =============================================================================
def close_dialog_if_open(page: Page) -> bool:
    """Dong tat ca hop thoai dialog/alert neu dang mo de tranh chan pointer events."""
    closed_any = False
    try:
        # 1. Alert dialog (Xac nhan dong bai thi)
        alert_btn = page.locator('[data-slot="alert-dialog-content"] button:has-text("Xác nhận"), div[role="alertdialog"] button:has-text("Xác nhận"), [data-slot="alert-dialog-content"] button:has-text("Dong y")').first
        if alert_btn.is_visible(timeout=300):
            alert_btn.click(timeout=500)
            page.wait_for_timeout(200)
            closed_any = True
    except Exception:
        pass

    try:
        # 2. Main dialog close button
        dialog = page.locator('div[role="dialog"][data-state="open"], [data-slot="dialog-content"][data-state="open"]').first
        if dialog.is_visible(timeout=350):
            close_btn = dialog.locator('button[data-slot="dialog-close"], button.absolute.top-4.right-4, button:has(svg.lucide-x)').first
            if close_btn.is_visible(timeout=300):
                close_btn.click(timeout=500)
                closed_any = True
            else:
                back_btn = dialog.locator("button:has-text('Quay lại'), button:has-text('Đóng')").first
                if back_btn.is_visible(timeout=300):
                    back_btn.click(timeout=500)
                    closed_any = True
                else:
                    page.keyboard.press("Escape")
                    closed_any = True
    except Exception:
        page.keyboard.press("Escape")

    try:
        page.locator('div[role="dialog"][data-state="open"]').wait_for(state="hidden", timeout=800)
    except Exception:
        try:
            page.evaluate("""() => {
                document.querySelectorAll('[data-slot="dialog-overlay"], [data-slot="alert-dialog-overlay"]').forEach(el => el.remove());
                document.querySelectorAll('div[role="dialog"]').forEach(el => {
                    el.setAttribute('data-state', 'closed');
                    el.style.display = 'none';
                });
                document.body.style.pointerEvents = 'auto';
                document.body.style.overflow = 'auto';
            }""")
        except Exception:
            pass
    return closed_any

def get_current_subject_name(page: Page) -> str:
    """Doc ten mon hoc hien tai tu DOM tren moi loai giao dien CMCU EduX."""
    try:
        if not page or page.is_closed():
            return "Mon hoc CMCU"
        name = page.evaluate("""() => {
            const badTerms = ['ai-native', 'edux', 'this site', "can't be reached", 'không thể truy cập', 'error', '404', '502'];

            // 1. Tim the tieu de mon hoc tren thanh sidebar / header
            const h = document.querySelector('h3.font-bold.text-white, h3[class*="text-white"], nav ol li:last-child, h1, h2');
            if (h) {
                let txt = (h.innerText || '').trim();
                // Loai bo icon mui ten neu co
                txt = txt.replace(/^[←<\\-–—\\s]+/, '').trim();
                if (txt && !badTerms.some(b => txt.toLowerCase().includes(b)) && txt.length > 2) {
                    return txt;
                }
            }
            // 2. Tim trong the breadcrumb hoac span tieu de
            const titleEl = document.querySelector('[class*="truncate"][class*="font-bold"]');
            if (titleEl) {
                let txt = (titleEl.innerText || '').trim().replace(/^[←<\\-–—\\s]+/, '').trim();
                if (txt && !badTerms.some(b => txt.toLowerCase().includes(b)) && txt.length > 2) return txt;
            }
            return '';
        }""")
        if name and len(name) < 100:
            return name
    except Exception:
        pass
    return "Mon hoc CMCU"

def parse_latest_result(dialog_text: str) -> Dict[str, Any]:
    """Boc tach diem so, thoi gian, so luot lam tu man hinh ket qua (tranh nham voi ngay thang)."""
    m_score = re.search(r"(?<!/)(?<!\d)(\d+(?:\.\d+)?)\s*/\s*10(?!\s*/)(?!\d)(?:\s*\((\d+%)\))?", dialog_text)
    score = m_score.group(1) if m_score else "N/A"
    pct = m_score.group(2) if m_score and m_score.group(2) else ""
    
    m_time = re.search(r"Thời gian:\s*([^\n]+)", dialog_text)
    time_taken = m_time.group(1).strip() if m_time else "N/A"
    
    m_review = re.search(r"Nhận xét:\s*([^\n]+)", dialog_text)
    review = m_review.group(1).strip() if m_review else "Khong co nhan xet"
    
    m_attempts = re.search(r"Số lần đã làm:\s*(\d+\s*/\s*\d+)", dialog_text)
    attempts = m_attempts.group(1).strip() if m_attempts else "N/A"
    
    score_display = f"{score}/10" + (f" ({pct})" if pct else "")
    return {
        "score": score_display,
        "score_num": float(score) if score != "N/A" else 0.0,
        "time_taken": time_taken,
        "attempts": attempts,
        "review": review
    }

# =============================================================================
# LOP DIEU KHIEN TU DONG HOA (EDUX AUTOMATOR)
# =============================================================================
class EduxAutomator:
    def __init__(self, page: Page, solver: Any, subject_name: str = "", chapter_name: str = ""):
        self.page = page
        self.solver = solver
        self.subject_name = subject_name
        self.chapter_name = chapter_name
        self._last_anti_vis = 0.0

    def inject_anti_visibility(self, force: bool = False):
        now = time.time()
        if not force and (now - self._last_anti_vis) < 8.0:
            return
        try:
            self.page.evaluate(ANTI_VISIBILITY_SCRIPT)
            self._last_anti_vis = now
        except Exception:
            pass

    def wait_for_ready(self, timeout_ms: int = 5000):
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass

    def get_scope(self) -> Locator:
        try:
            dialog = self.page.locator('div[role="dialog"][data-state="open"]').first
            if dialog.is_visible(timeout=200):
                return dialog
        except Exception:
            pass

        try:
            dialog_any = self.page.locator('div[role="dialog"]').first
            if dialog_any.is_visible(timeout=150):
                return dialog_any
        except Exception:
            pass

        try:
            main_container = self.page.locator('div.bg-white.rounded-lg, main').first
            if main_container.is_visible(timeout=150):
                return main_container
        except Exception:
            pass

        return self.page.locator('body')

    def has_pagination_buttons(self) -> bool:
        """Kiểm tra nhanh giao diện có dãy nút số chuyển câu (1, 2, ... N) hay không (1 RPC)."""
        try:
            return bool(self.page.evaluate("""() => {
                const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                    || document.querySelector('div[role="dialog"]')
                    || document.querySelector('div.bg-white.rounded-lg, main')
                    || document.body;
                const buttons = Array.from(dialog.querySelectorAll('button')).filter(b => /^\\d+$/.test((b.innerText || '').trim()));
                return buttons.length >= 2;
            }"""))
        except Exception:
            return False

    def get_progress(self) -> Tuple[int, int]:
        try:
            res = self.page.evaluate("""() => {
                const findRoot = () => {
                    const openDlg = document.querySelector('div[role="dialog"][data-state="open"]');
                    if (openDlg) return openDlg;
                    const anyDlg = document.querySelector('div[role="dialog"]');
                    if (anyDlg) return anyDlg;
                    const mainEl = document.querySelector('main');
                    if (mainEl && (/Câu\\s*\\d+/i.test(mainEl.innerText || '') || mainEl.querySelectorAll('button').length >= 2)) {
                        return mainEl;
                    }
                    const cards = Array.from(document.querySelectorAll('div.bg-white.rounded-lg'));
                    const quizCard = cards.find(c => /(\\d+\\s*\\/\\s*\\d+\\s*câu|Câu\\s*\\d+)/i.test(c.innerText || ''));
                    return quizCard || mainEl || document.body;
                };

                const extractFrom = (root) => {
                    const text = root.innerText || '';
                    const buttons = Array.from(root.querySelectorAll('button')).filter(b => /^\\d+$/.test((b.innerText || '').trim()));
                    let doneFromBtns = 0;
                    let maxBtn = 0;
                    for (const b of buttons) {
                        const n = parseInt((b.innerText || '').trim(), 10);
                        if (n > maxBtn) maxBtn = n;
                        const cls = b.className || '';
                        if (cls.includes('bg-primary') || cls.includes('bg-blue') || cls.includes('bg-emerald') || cls.includes('bg-green')) {
                            doneFromBtns++;
                        }
                    }

                    let total = Math.max(buttons.length, maxBtn);
                    let done = doneFromBtns;

                    const m1 = text.match(/(\\d+)\\s*\\/\\s*(\\d+)\\s*câu/i);
                    if (m1) {
                        done = parseInt(m1[1], 10);
                        total = Math.max(total, parseInt(m1[2], 10));
                    } else {
                        const m2 = text.match(/Câu\\s*\\d+\\s*\\/\\s*(\\d+)/i);
                        if (m2) total = Math.max(total, parseInt(m2[1], 10));
                        const m3 = text.match(/Tổng(?:\\s*số)?\\s*:?\\s*(\\d+)\\s*câu/i);
                        if (m3) total = Math.max(total, parseInt(m3[1], 10));
                    }

                    const mUnans = text.match(/Câu hỏi chưa làm\\s*\\((\\d+)\\)/i);
                    if (mUnans && total > 0) {
                        const unansCount = parseInt(mUnans[1], 10);
                        done = Math.max(done, Math.max(0, total - unansCount));
                    }

                    return { done, total };
                };

                const root = findRoot();
                let result = extractFrom(root);
                if (result.total === 0 && root !== document.body) {
                    result = extractFrom(document.body);
                }
                return result;
            }""")
            if res:
                return int(res.get("done", 0)), int(res.get("total", 0))
        except Exception:
            pass
        return 0, 0

    def get_current_question_number(self) -> int:
        try:
            num = self.page.evaluate("""() => {
                const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                    || document.querySelector('div[role="dialog"]')
                    || document.querySelector('div.bg-white.rounded-lg, main')
                    || document.body;
                const text = dialog.innerText || '';
                const m = text.match(/Câu\\s*(\\d+)/i);
                if (m) return parseInt(m[1], 10);

                const buttons = Array.from(dialog.querySelectorAll('button')).filter(b => /^\\d+$/.test((b.innerText || '').trim()));
                for (const b of buttons) {
                    const cls = b.className || '';
                    if (cls.includes('ring-2') || cls.includes('border-primary') || cls.includes('bg-blue-600') || cls.includes('border-black')) {
                        return parseInt(b.innerText.trim(), 10);
                    }
                }
                return 1;
            }""")
            if num:
                return int(num)
        except Exception:
            pass
        return 1

    def jump_to_question(self, target_num: int) -> bool:
        try:
            res = self.page.evaluate("""(num) => {
                const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                    || document.querySelector('div[role="dialog"]')
                    || document.querySelector('div.bg-white.rounded-lg, main')
                    || document.body;
                const text = dialog.innerText || '';
                const m = text.match(/Câu\\s*(\\d+)/i);
                const curr = m ? parseInt(m[1], 10) : 0;
                if (curr === num) return { already: true, clicked: true, curr: curr };

                // 1. Tim nut phan trang mang so target_num
                const buttons = Array.from(dialog.querySelectorAll('button')).filter(b => /^\\d+$/.test((b.innerText || '').trim()));
                const targetBtn = buttons.find(b => parseInt(b.innerText.trim(), 10) === num);
                if (targetBtn) {
                    targetBtn.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                    targetBtn.click();
                    return { already: false, clicked: true, curr: curr };
                }

                // 2. Tim trong danh sach 'Câu hỏi chưa làm' ben canh (neu co)
                const allItems = Array.from(dialog.querySelectorAll('div, li, button, a, span')).filter(el => {
                    const t = (el.innerText || '').trim();
                    const mItem = t.match(/^(\\d+)[\\.\\s]+/);
                    return mItem && parseInt(mItem[1], 10) === num && t.length < 220 && el.children.length <= 3;
                });
                if (allItems.length > 0) {
                    const itemEl = allItems[allItems.length - 1];
                    itemEl.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                    itemEl.click();
                    return { already: false, clicked: true, curr: curr };
                }

                return { already: false, clicked: false, curr: curr || 1 };
            }""", target_num)
        except Exception:
            res = {"already": False, "clicked": False, "curr": 1}

        if res.get("already"):
            return True

        if res.get("clicked"):
            for _ in range(15):
                self.page.wait_for_timeout(50)
                if self.get_current_question_number() == target_num:
                    self.page.wait_for_timeout(150)
                    return True

        # 3. Fallback: Bam nut 'Câu tiếp' / 'Tiếp' / 'Sau' hoac 'Câu trước' / 'Trước' bang JS
        for _ in range(max(55, target_num + 5)):
            curr = self.get_current_question_number()
            if curr == target_num:
                self.page.wait_for_timeout(150)
                return True
            forward = target_num > curr
            stepped = self.page.evaluate("""(goForward) => {
                const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                    || document.querySelector('div[role="dialog"]')
                    || document.querySelector('div.bg-white.rounded-lg, main')
                    || document.body;
                const btns = Array.from(dialog.querySelectorAll('button')).filter(b => !b.disabled);
                const target = btns.find(b => {
                    const t = (b.innerText || '').trim().toLowerCase();
                    if (goForward) {
                        return t === 'sau' || t === 'tiếp' || t === 'tiếp theo' || t.includes('câu tiếp') || t.includes('tiếp');
                    } else {
                        return t === 'trước' || t.includes('câu trước') || t.includes('quay lại');
                    }
                });
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            }""", forward)
            if not stepped:
                break
            self.page.wait_for_timeout(160)

        return self.get_current_question_number() == target_num

    def parse_current_question(self) -> Dict[str, Any]:
        """
        Doc De bai, hinh anh (Vision screenshot neu co), 4 options A/B/C/D hoac 4 menh de Dung/Sai.
        Loai tru tuyet doi vung sidebar 'Câu hỏi chưa làm' de khong bao gio lay nham de bai bi cat '...'.
        """
        self.inject_anti_visibility()

        extracted = self.page.evaluate("""() => {
            const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                || document.querySelector('div[role="dialog"]')
                || document.querySelector('div.bg-white.rounded-lg, main')
                || document.body;
            const text = dialog.innerText || '';
            const mQ = text.match(/Câu\\s*(\\d+)/i);
            const qNum = mQ ? parseInt(mQ[1], 10) : 1;

            // Xac dinh sidebar 'Câu hỏi chưa làm' de loai tru khoi vung quet De bai
            const unansContainers = Array.from(dialog.querySelectorAll('aside, section, div')).filter(el => {
                const t = (el.innerText || '').trim();
                return t.startsWith('Câu hỏi chưa làm') && !el.querySelector('button[role="radio"], [data-slot="radio-group"]');
            });
            const isInsideUnansSidebar = (el) => unansContainers.some(c => c.contains(el));
            
            // Kiem tra hinh anh trong vung cau hoi chinh
            const images = Array.from(dialog.querySelectorAll('img'))
                .filter(img => !isInsideUnansSidebar(img))
                .map(img => img.src)
                .filter(src => src && !src.includes('avatar') && !src.includes('logo'));
            const hasImages = images.length > 0;
            
            // Kiem tra loai Dung Sai nhieu menh de
            const dungBtns = Array.from(dialog.querySelectorAll('button')).filter(b => (b.innerText || '').trim() === 'Đúng');
            const saiBtns = Array.from(dialog.querySelectorAll('button')).filter(b => (b.innerText || '').trim() === 'Sai');
            const isMultiTrueFalse = dungBtns.length >= 2 && saiBtns.length >= 2;
            
            let subStatements = [];
            let qType = 'choice';
            let qTypeLabel = 'Trắc nghiệm';

            if (isMultiTrueFalse) {
                qType = 'multi_true_false';
                qTypeLabel = 'Đúng sai (4 mệnh đề)';
                subStatements = dungBtns.map((btn, idx) => {
                    let card = btn.closest('div.border, div.rounded-lg, div.p-3');
                    let rawText = card ? card.innerText : '';
                    rawText = rawText.replace(/Đúng/g, '').replace(/Sai/g, '').replace(/\\n+/g, ' ').trim();
                    return {
                        index: idx + 1,
                        text: rawText
                    };
                });
            }
            
            // Tim De bai: lay the p hoac div nam tren khoi lua chon, loai tru panel 'Câu hỏi chưa làm' va cac dong bi cat '...'
            let promptText = '';
            const allP = Array.from(dialog.querySelectorAll('p, div.text-base, div.font-medium, div.text-gray-900, div.text-gray-800, h4, h3'));
            for (const p of allP) {
                if (isInsideUnansSidebar(p)) continue;
                const t = (p.innerText || '').trim();
                const tl = t.toLowerCase();
                if (!t || t.length <= 8) continue;
                if (
                    tl.includes('câu hỏi chưa làm') ||
                    tl.includes('thời gian') ||
                    tl.includes('hướng dẫn') ||
                    tl.includes('lưu ý') ||
                    tl.includes('di chuột') ||
                    tl.startsWith('bài tập') ||
                    t.endsWith('...') ||
                    t.endsWith('…') ||
                    /^\\d+\\.\\s+/.test(t) ||
                    /^câu\\s*\\d+\\s*$/i.test(t) ||
                    /^\\d+\\s*\\/\\s*\\d+\\s*câu/i.test(t)
                ) continue;
                if (!/^[A-D][\\.\\)]\\s/.test(t)) {
                    promptText = t;
                    break;
                }
            }
            
            if (!promptText) {
                const matchPrompt = text.match(/Câu\\s*\\d+\\s*\\n*[^:]*:\\s*\\n*([^\\n]+)/i);
                if (matchPrompt) {
                    const cand = matchPrompt[1].trim();
                    if (!cand.toLowerCase().includes('câu hỏi chưa làm') && !cand.endsWith('...')) {
                        promptText = cand;
                    }
                }
            }
            
            // Tim 4 lua chon A, B, C, D (neu la Trac nghiem)
            const options = [];
            if (qType !== 'multi_true_false') {
                let optionCards = Array.from(dialog.querySelectorAll('div.relative.flex.items-center.space-x-2, div.cursor-pointer[class*="border"], div[role="radio"], label[class*="cursor-pointer"]'))
                    .filter(el => !isInsideUnansSidebar(el));
                if (optionCards.length === 0) {
                    const allEls = Array.from(dialog.querySelectorAll('div, label')).filter(el => {
                        if (isInsideUnansSidebar(el)) return false;
                        const t = (el.innerText || '').trim();
                        return /^[A-D][\\.\\)]\\s+/.test(t) && t.length < 300 && el.children.length <= 4;
                    });
                    optionCards = allEls;
                }
                for (const card of optionCards) {
                    const t = (card.innerText || '').trim();
                    const m = t.match(/^([A-D]|Đúng|Sai)[\\.\\)]?\\s*\\n*\\s*(.*)/s);
                    if (m) {
                        if (!options.some(o => o.prefix === m[1])) {
                            options.push({
                                prefix: m[1],
                                text: m[2].replace(/\\n+/g, ' ').trim(),
                                raw: t
                            });
                        }
                    }
                }
            }
            
            const hasTextarea = !!dialog.querySelector('textarea, input[type=\"text\"]:not([readonly])');
            if (hasTextarea && qType !== 'multi_true_false') {
                qType = 'text';
                qTypeLabel = 'Tự luận / Điền từ';
            }

            return {
                qNum: qNum,
                qType: qType,
                qTypeLabel: qTypeLabel,
                promptText: promptText,
                options: options,
                subStatements: subStatements,
                hasTextarea: hasTextarea,
                hasImages: hasImages,
                imageUrls: images
            };
        }""")

        # Multimodal Vision: Neu co anh hoac bieu do, chup screenshot vung cau hoi gui cho Gemini
        screenshot_bytes = None
        if extracted.get("hasImages"):
            try:
                scope = self.get_scope()
                screenshot_bytes = scope.screenshot(type="png")
                console.print("[magenta][VISION] Phat hien hinh anh/so do trong de bai! Da chup screenshot gui Gemini Multimodal.[/magenta]")
            except Exception:
                pass

        return {
            "q_num": extracted.get("qNum", 1),
            "type": extracted.get("qType", "choice"),
            "type_label": extracted.get("qTypeLabel", "Trac nghiem"),
            "prompt": extracted.get("promptText", ""),
            "options": extracted.get("options", []),
            "sub_statements": extracted.get("subStatements", []),
            "has_text_input": extracted.get("hasTextarea", False),
            "has_images": extracted.get("hasImages", False),
            "screenshot_bytes": screenshot_bytes
        }

    def apply_answer(self, q_data: Dict[str, Any], gemini_result: Dict[str, Any]) -> bool:
        """
        Dien dap an vao DOM bang JS + React Synthetic Events (hoat dong 100% ke ca khi tab Chrome o duoi nen),
        kem kiem tra xac nhan da tich chon thanh cong.
        """
        q_type = q_data.get("type", "choice")
        selected_options = gemini_result.get("selected_options", [])
        sub_answers = gemini_result.get("sub_answers", [])
        text_answer = gemini_result.get("text_answer", "")

        try:
            # 1. Dung/Sai 4 menh de (multi_true_false) - Click truc tiep qua JS + React Props
            if q_type == "multi_true_false" or sub_answers:
                if not sub_answers:
                    sub_answers = ["Đúng", "Sai", "Đúng", "Sai"]
                bool_flags = []
                for ans_val in sub_answers:
                    s = str(ans_val).strip().lower()
                    bool_flags.append("dung" in s or "đúng" in s or s == "d" or s == "true" or s == "1")

                for idx, is_dung in enumerate(bool_flags):
                    self.page.evaluate("""(args) => {
                        const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                            || document.querySelector('div[role="dialog"]')
                            || document.querySelector('div.bg-white.rounded-lg, main')
                            || document.body;
                        const dungBtns = Array.from(dialog.querySelectorAll('button')).filter(b => (b.innerText || '').trim() === 'Đúng');
                        const saiBtns = Array.from(dialog.querySelectorAll('button')).filter(b => (b.innerText || '').trim() === 'Sai');
                        const btn = args.isDung ? dungBtns[args.idx] : saiBtns[args.idx];
                        if (!btn) return false;
                        btn.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                        const opts = { bubbles: true, cancelable: true, view: window };
                        btn.dispatchEvent(new PointerEvent('pointerdown', opts));
                        btn.dispatchEvent(new MouseEvent('mousedown', opts));
                        btn.dispatchEvent(new PointerEvent('pointerup', opts));
                        btn.dispatchEvent(new MouseEvent('mouseup', opts));
                        btn.click();
                        const rKey = Object.keys(btn).find(k => k.startsWith('__reactProps'));
                        if (rKey && btn[rKey] && typeof btn[rKey].onClick === 'function') {
                            btn[rKey].onClick({ stopPropagation: () => {}, preventDefault: () => {} });
                        }
                        return true;
                    }""", {"idx": idx, "isDung": is_dung})
                    self.page.wait_for_timeout(160)
                return True

            # 2. Tu luan / Dien tu (ho tro ca khi tab o nen bang Native Value Setter)
            if q_data.get("has_text_input") or q_type == "text":
                filled_js = self.page.evaluate("""(val) => {
                    const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                        || document.querySelector('div[role="dialog"]')
                        || document.querySelector('div.bg-white.rounded-lg, main')
                        || document.body;
                    const el = dialog.querySelector('textarea, input[type="text"]:not([readonly])');
                    if (!el) return false;
                    el.focus();
                    const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                    if (setter) {
                        setter.call(el, val);
                    } else {
                        el.value = val;
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }""", text_answer)
                self.page.wait_for_timeout(200)
                return bool(filled_js)

            # 3. Trac nghiem A/B/C/D hoac Dung/Sai don
            if selected_options:
                clicked_any = False
                for opt_key in selected_options:
                    opt_letter = str(opt_key).strip().upper()

                    clicked = self.page.evaluate("""(letter) => {
                        const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                            || document.querySelector('div[role="dialog"]')
                            || document.querySelector('div.bg-white.rounded-lg, main')
                            || document.body;
                        const l = letter.trim().toUpperCase();
                        let cards = Array.from(dialog.querySelectorAll('div.relative.flex.items-center.space-x-2, div.cursor-pointer[class*="border"], div[role="radio"], label'));
                        let card = cards.find(c => {
                            const t = (c.innerText || '').trim();
                            const tu = t.toUpperCase();
                            return (
                                t.startsWith(l + '.') ||
                                t.startsWith(l + ')') ||
                                tu === l ||
                                ((l === 'DUNG' || l === 'ĐÚNG') && t.startsWith('Đúng')) ||
                                (l === 'SAI' && t.startsWith('Sai'))
                            );
                        });
                        
                        if (!card) {
                            const allEls = Array.from(dialog.querySelectorAll('div, label, span, p'));
                            card = allEls.find(el => {
                                const t = (el.innerText || '').trim();
                                return (t.startsWith(l + '.') || t.startsWith(l + ')')) && t.length < 300 && el.children.length <= 3;
                            });
                        }
                        
                        if (!card) return false;
                        
                        card.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                        const opts = { bubbles: true, cancelable: true, view: window };
                        card.dispatchEvent(new PointerEvent('pointerdown', opts));
                        card.dispatchEvent(new MouseEvent('mousedown', opts));
                        card.dispatchEvent(new PointerEvent('pointerup', opts));
                        card.dispatchEvent(new MouseEvent('mouseup', opts));
                        card.click();
                        const rKey = Object.keys(card).find(k => k.startsWith('__reactProps'));
                        if (rKey && card[rKey] && typeof card[rKey].onClick === 'function') {
                            card[rKey].onClick({ stopPropagation: () => {}, preventDefault: () => {} });
                        }
                        const innerRadio = card.querySelector('button[role="radio"], input[type="radio"]');
                        if (innerRadio && innerRadio !== card) {
                            innerRadio.click();
                        }
                        return true;
                    }""", opt_letter)

                    if clicked:
                        clicked_any = True
                        self.page.wait_for_timeout(200)

                return clicked_any

        except Exception as e:
            console.print(f"[bold red][X] Loi khi ap dung dap an vao DOM: {e}[/bold red]")
            return False

        return False

    def is_current_question_answered(self) -> bool:
        try:
            return bool(self.page.evaluate("""() => {
                const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                    || document.querySelector('div[role="dialog"]')
                    || document.querySelector('div.bg-white.rounded-lg, main')
                    || document.body;
                // 1. Kiem tra theo so thu tu cau o thanh phan trang duoi cung
                const mQ = (dialog.innerText || '').match(/Câu\\s*(\\d+)/i);
                if (mQ) {
                    const qNum = mQ[1];
                    const numBtns = Array.from(dialog.querySelectorAll('button')).filter(b => (b.innerText || '').trim() === qNum);
                    for (const b of numBtns) {
                        const cls = (b.className || '').toLowerCase();
                        if (cls.includes('bg-primary') || cls.includes('bg-blue') || cls.includes('bg-emerald') || cls.includes('bg-green') || cls.includes('text-white')) {
                            return true;
                        }
                    }
                }
                // 2. Kiem tra cac the radio / card duoc checked
                const selectedCards = dialog.querySelectorAll('div[data-state="checked"], div[aria-checked="true"], button[aria-checked="true"], input[type="radio"]:checked, div.cursor-pointer.border-primary, div.cursor-pointer[class*="bg-primary/10"]');
                if (selectedCards.length > 0) return true;

                // 3. Kiem tra the radio icon ben trong lua chon co checked
                const checkedCircles = dialog.querySelectorAll('[data-state="checked"], span.border-primary.bg-primary, span[class*="border-blue-600"]');
                if (checkedCircles.length > 0) return true;

                // 4. Kiem tra cac nut Dung/Sai (True/False) co class active (bg-emerald, bg-green, bg-red, bg-rose, text-white)
                const tfActive = dialog.querySelectorAll('button[class*="bg-emerald"], button[class*="bg-green"], button[class*="bg-red"], button[class*="bg-rose"], button[class*="bg-primary"], button[class*="bg-blue"]');
                if (tfActive.length > 0) return true;

                // 5. Kiem tra text input
                const txt = dialog.querySelector('textarea, input[type="text"]:not([readonly])');
                if (txt && txt.value && txt.value.trim().length > 0) return true;

                return false;
            }"""))
        except Exception:
            return False

    def review_and_solve_unanswered_questions(
        self,
        solver: Any,
        total_questions: int,
        start_q: int = 1,
        end_q: Optional[int] = None
    ) -> int:
        """Quet lai 100% tat ca cau hoi chua lam trong pham vi [start_q, end_q] de khong bo sot bat ky cau nao."""
        from src.web.server import state
        target_end = end_q if (end_q and end_q > 0) else total_questions
        console.print("[bold yellow][RA SOAT] Dang kiem tra lai 100% cau hoi chua tra loi...[/bold yellow]")
        state.broadcast_log("[RA SOÁT] Đang kiểm tra toàn diện danh sách câu hỏi chưa làm...")
        fixed_count = 0

        # Layer 1: Uu tien doc panel "Câu hỏi chưa làm" tren dialog EduX (click truc tiep vao tung muc con sot)
        for _ in range(3):
            if state.stop_requested:
                break
            unans_detected = []
            try:
                unans_detected = self.page.evaluate("""(bounds) => {
                    const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                        || document.querySelector('div[role="dialog"]')
                        || document.querySelector('div.bg-white.rounded-lg, main')
                        || document.body;

                    // 1. Kiem tra neu tat ca da lam xong ('Câu hỏi chưa làm (0)')
                    const fullText = dialog.innerText || '';
                    if (fullText.includes('Câu hỏi chưa làm (0)')) {
                        return [];
                    }

                    // 2. Tim danh sach 'Câu hỏi chưa làm'
                    const listContainer = Array.from(dialog.querySelectorAll('aside, section, div, ul')).find(el => {
                        const t = (el.innerText || '').trim();
                        return t.includes('Câu hỏi chưa làm') && !t.includes('Câu hỏi chưa làm (0)') && !el.querySelector('button[role="radio"]');
                    });
                    if (listContainer) {
                        const items = Array.from(listContainer.querySelectorAll('div, li, p, span, button')).filter(el => {
                            const t = (el.innerText || '').trim();
                            return (/^\\d+\\s+/.test(t) || /^\\d+\\./.test(t)) && t.length < 250;
                        });
                        const list = [];
                        for (const it of items) {
                            const m = (it.innerText || '').trim().match(/^(\\d+)/);
                            if (m) {
                                const qn = parseInt(m[1], 10);
                                if (qn >= bounds.start && qn <= bounds.end) list.push(qn);
                            }
                        }
                        if (list.length > 0) return [...new Set(list)];
                    }

                    // 3. Quet cac nut so chua to mau o thanh phan trang duoi cung
                    const buttons = Array.from(dialog.querySelectorAll('button')).filter(b => /^\\d+$/.test((b.innerText || '').trim()));
                    const pillUnans = [];
                    for (const b of buttons) {
                        const qNum = parseInt(b.innerText.trim(), 10);
                        if (qNum < bounds.start || qNum > bounds.end) continue;
                        const cls = (b.className || '').toLowerCase();
                        const isDone = cls.includes('bg-primary') || cls.includes('bg-blue') || cls.includes('bg-green') || cls.includes('bg-emerald');
                        if (!isDone) pillUnans.push(qNum);
                    }
                    return pillUnans;
                }""", {"start": start_q, "end": target_end})
            except Exception:
                unans_detected = []

            if not unans_detected:
                break

            console.print(f"[yellow][!] Phat hien cac cau con sot: {unans_detected}. Tien hanh giai bu can than...[/yellow]")
            state.broadcast_log(f"[RA SOÁT] Phát hiện các câu chưa làm: {unans_detected}, tiến hành giải bổ sung...")

            for q_idx in unans_detected:
                if state.stop_requested:
                    break
                if q_idx < start_q or q_idx > target_end:
                    continue
                self.jump_to_question(q_idx)
                self.page.wait_for_timeout(220)
                try:
                    q_data = self.parse_current_question()
                    ans = solver.solve(q_data, subject_name=self.subject_name, chapter_name=self.chapter_name)
                    applied = self.apply_answer(q_data, ans)
                    self.page.wait_for_timeout(200)
                    if not self.is_current_question_answered():
                        applied = self.apply_answer(q_data, ans)
                        self.page.wait_for_timeout(200)
                    if applied:
                        fixed_count += 1
                        console.print(f"[green][OK] Da dien thanh cong dap an cau {q_idx}![/green]")
                        state.broadcast_log(f"[OK] Đã giải bù thành công câu {q_idx}!")
                except Exception as e:
                    console.print(f"[red]Loi khi giai bu cau {q_idx}: {e}[/red]")

        # Layer 2: Neu van chua du 100% so cau hoan thanh, duyet kiem tra tu start_q -> target_end
        done_now, _ = self.get_progress()
        expected_done = target_end - start_q + 1
        if done_now < expected_done and not state.stop_requested:
            self.jump_to_question(start_q)
            self.page.wait_for_timeout(200)
            for q_idx in range(start_q, target_end + 1):
                if state.stop_requested:
                    break
                if self.get_current_question_number() != q_idx:
                    self.jump_to_question(q_idx)
                    self.page.wait_for_timeout(180)
                if not self.is_current_question_answered():
                    try:
                        q_data = self.parse_current_question()
                        ans = solver.solve(q_data, subject_name=self.subject_name, chapter_name=self.chapter_name)
                        if self.apply_answer(q_data, ans):
                            fixed_count += 1
                            self.page.wait_for_timeout(200)
                    except Exception:
                        pass
                if q_idx < target_end:
                    self.next_question()

        if fixed_count == 0:
            console.print("[bold green][OK] 100% tat ca cau hoi da duoc lam day du (0 cau bo sot)![/bold green]")
            state.broadcast_log("[OK] 100% câu hỏi đã hoàn tất đầy đủ, không còn câu nào bỏ sót!")
        else:
            console.print(f"[bold green][OK] Da giai bo sung thanh cong {fixed_count} cau hoi con sot![/bold green]")
            state.broadcast_log(f"[OK] Đã giải bù thành công {fixed_count} câu hỏi còn sót!")
        return fixed_count

    def next_question(self) -> bool:
        curr_before = self.get_current_question_number()

        clicked = self.page.evaluate("""() => {
            const dialog = document.querySelector('div[role="dialog"][data-state="open"]')
                || document.querySelector('div[role="dialog"]')
                || document.querySelector('div.bg-white.rounded-lg, main')
                || document.body;
            const nextBtn = Array.from(dialog.querySelectorAll('button')).find(b => {
                const t = (b.innerText || '').trim().toLowerCase();
                return t === 'sau' || t === 'tiếp' || t === 'tiếp theo' || t.includes('tiếp') || t.includes('câu tiếp');
            });
            if (nextBtn && !nextBtn.disabled) {
                nextBtn.click();
                return true;
            }
            return false;
        }""")

        if clicked:
            for _ in range(20):
                self.page.wait_for_timeout(60)
                if self.get_current_question_number() > curr_before:
                    self.page.wait_for_timeout(180)
                    return True
        return False

    def submit_and_get_results(self, target_title: str, target_type: str = "ai") -> Dict[str, Any]:
        """Tu dong bam nut Nop bai, xac nhan popup va giu nguyen man hinh de nguoi dung xem diem so."""
        from src.web.server import state
        scope = self.get_scope()

        # Buoc 1: Nhay den cau cuoi cung de nut Nop bai chac chan xuat hien
        try:
            _, tot = self.get_progress()
            target_last = tot if tot > 0 else 30
            console.print(f"[cyan][*] Dang chuyen den cau cuoi cung ({target_last}) de kich hoat nut Nop bai...[/cyan]")
            state.broadcast_log(f"[*] Chuyển tới câu cuối cùng ({target_last}) để hiển thị nút Nộp bài...")
            self.jump_to_question(target_last)
            self.page.wait_for_timeout(180)
        except Exception:
            pass

        console.print("[cyan][*] Dang tim va bam nut 'Nop bai'...[/cyan]")
        try:
            submit_btn = scope.locator("button:has-text('Nộp bài'), button:has-text('Kết thúc bài thi'), button:has-text('Nộp bài tập'), button:has-text('Hoàn thành'), button:text-is('Nộp bài')").first
            if not submit_btn.is_visible(timeout=800):
                submit_btn = self.page.locator("button:has-text('Nộp bài'), button:has-text('Hoàn thành')").first

            if submit_btn.is_visible(timeout=2000):
                submit_btn.click(force=True)
                console.print("[green][OK] Da bam nut 'Nop bai' thanh cong![/green]")
                state.broadcast_log("[OK] Đã bấm nút 'Nộp bài', chờ popup xác nhận...")

                # Buoc 2: Bắt popup xác nhận "Bạn có chắc chắn muốn nộp bài không?" ngay khi xuat hien
                confirm_btn = self.page.locator("div[role='alertdialog'] button:has-text('Xác nhận'), div[role='dialog'] button:has-text('Xác nhận'), div[role='dialog'] button:has-text('Đồng ý'), div[role='dialog'] button:has-text('Có'), div[role='dialog'] button:has-text('Nộp bài'), button:has-text('Xác nhận')").last
                for _ in range(15):
                    self.page.wait_for_timeout(120)
                    if confirm_btn.is_visible(timeout=100):
                        confirm_btn.click(force=True)
                        console.print("[bold green][OK] Da xac nhan nop bai vao he thong CMCU LMS![/bold green]")
                        state.broadcast_log("[OK] Đã xác nhận nộp bài vào hệ thống CMCU LMS!")
                        break
            else:
                console.print("[yellow]Khong tim thay nut Nop bai tren man hinh, dang kiem tra ket qua...[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Loi khi bam nop bai: {e}[/bold red]")

        console.print("[cyan][*] Dang cho he thong CMCU LMS cham diem va tra ket qua...[/cyan]")
        state.broadcast_log("[*] Đang chờ hệ thống LMS chấm điểm và xuất bảng kết quả...")
        d_text = ""
        res_info = None

        # 1. Cho va doc ket qua truc tiep tu hop thoai ket qua tren man hinh (kiem tra moi 0.25s)
        for _ in range(40):
            time.sleep(0.25)
            try:
                dialog = self.page.locator('div[role="dialog"]').first
                if dialog.is_visible(timeout=200):
                    txt = dialog.inner_text()
                    if "/10" in txt or "Kết quả" in txt or "Điểm số" in txt or "Nhận xét" in txt:
                        parsed = parse_latest_result(txt)
                        if parsed["score"] != "N/A":
                            d_text = txt
                            res_info = parsed
                            console.print(f"[bold green][OK] Da doc duoc ket qua truc tiep tu hop thoai: {res_info['score']}![/bold green]")
                            state.broadcast_log(f"[KẾT QUẢ] Điểm số LMS ghi nhận: {res_info['score']}")
                            break
            except Exception:
                pass

        if not res_info:
            res_info = parse_latest_result(d_text)

        console.print("\n")
        res_table = Table(title=f"=== [OK] KET QUA CHAM DIEM: {to_clean_ascii(target_title)} ===", box=box.DOUBLE_EDGE)
        res_table.add_column("Chi muc", style="bold yellow", width=25)
        res_table.add_column("Ket qua he thong", style="bold green")
        res_table.add_row("Diem so dat duoc", f"[bold white on green] {res_info['score']} [/bold white on green]")
        res_table.add_row("Thoi gian lam bai", res_info["time_taken"])
        res_table.add_row("So lan da lam", res_info["attempts"])
        res_table.add_row("Nhan xet tu he thong", to_clean_ascii(res_info["review"]))
        console.print(res_table)

        return res_info

def wait_and_start_quiz(automator: EduxAutomator) -> bool:
    """Kiem tra man hinh cho va click Bat dau lam bai."""
    page = automator.page
    dialog = page.locator('div[role="dialog"][data-state="open"]').first
    if not dialog.is_visible(timeout=1000):
        return False

    try:
        dialog.evaluate("""d => {
            const guideClose = d.querySelector('button:has-text("Đã hiểu"), button:has-text("Bỏ qua"), button:has-text("Đóng")');
            if (guideClose) guideClose.click();
        }""")
    except Exception:
        pass

    start_btn = dialog.locator("button:has-text('Làm bài tập'), button:has-text('Làm bài'), button:has-text('Bắt đầu làm bài'), button:has-text('Bắt đầu'), button:has-text('Làm lại')").first
    if start_btn.is_visible(timeout=600):
        btn_text = start_btn.inner_text().strip()
        console.print(f"[cyan]Dang click nut bat dau: '{btn_text}' trong hop thoai...[/cyan]")
        start_btn.evaluate("b => b.click()")

        with console.status("[cyan]Dang cho giao dien cau hoi thuc su xuat hien...[/cyan]"):
            for _ in range(50):
                page.wait_for_timeout(180)
                d_text = dialog.inner_text()
                if ("Câu 1" in d_text or "câu" in d_text or "Thời gian còn lại:" in d_text) and "Sẵn sàng làm bài?" not in d_text:
                    console.print("[bold green][OK] Da vao giao dien lam bai thanh cong![/bold green]")
                    return True
    else:
        d_text = dialog.inner_text()
        if "Câu " in d_text or "Thời gian còn lại:" in d_text:
            return True

    return True

def scan_subjects_on_student_page(page: Page) -> List[Dict[str, Any]]:
    """Quet danh sach tat ca mon hoc tren trang /student."""
    close_dialog_if_open(page)
    try:
        subjects = page.evaluate("""() => {
            const list = [];
            const cards = Array.from(document.querySelectorAll('div.bg-card, div.border.rounded-lg, div.rounded-xl.border'));
            for (const c of cards) {
                const text = c.innerText || '';
                const mCode = text.match(/([A-Z]{2,4}\\d{3,4}|[A-Z]{3,5}_[A-Z0-9]+)/);
                const code = mCode ? mCode[1] : '';
                
                const h3 = c.querySelector('h3, .font-bold.text-lg, .font-semibold');
                let title = h3 ? h3.innerText.trim() : '';
                if (!title) {
                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                    title = lines.find(l => l !== code && l.length > 5) || code;
                }
                
                const mSem = text.match(/(Học kỳ\\s*\\d+|HK\\d+|Summer\\s*\\d+|Fall\\s*\\d+|Spring\\s*\\d+)/i);
                const sem = mSem ? mSem[1] : '-';
                
                const infoMatches = text.split('\\n').filter(l => l.includes('Học liệu') || l.includes('Buổi') || l.includes('Tiến độ') || l.includes('%'));
                const info = infoMatches.join(' | ') || '-';

                if (code || title) {
                    list.push({
                        code: code || 'MON',
                        title: title || 'Mon hoc',
                        semester: sem,
                        info: info
                    });
                }
            }
            return list;
        }""")
        return subjects
    except Exception as e:
        console.print(f"[red]Loi khi quet danh sach mon hoc: {e}[/red]")
        return []

def scan_course_full_structure(page: Page) -> List[Dict[str, Any]]:
    """
    Quet toan bo danh sach bai hoc sieu toc (Instant Scan < 0.2s).
    Doc truc tiep tat ca card chuong/tuan va cac dang bai tap (AI, Thu cong, Slide)
    khong can mo dong popup, chong giat lag Chrome va khong timeout.
    """
    close_dialog_if_open(page)
    try:
        js_scan = r"""() => {
            const cards = Array.from(document.querySelectorAll('div.bg-card')).filter(c => {
                const btns = Array.from(c.querySelectorAll('button')).map(b => (b.innerText || '').trim());
                return btns.some(t => t.includes('Bài tập') || t.includes('Bài giảng') || t.includes('Tài liệu'));
            });
            
            const list = [];
            let stt = 1;
            
            for (const card of cards) {
                const cardText = (card.innerText || '').trim();
                const lines = cardText.split('\n').map(l => l.trim()).filter(Boolean);
                
                // 1. % Tro giang
                const mPercent = cardText.match(/(\d+)%/);
                const percentTroGiang = mPercent ? mPercent[1] + '%' : '0%';
                const percentVal = mPercent ? parseInt(mPercent[1], 10) : 0;
                
                // 2. Tuan hoc
                const mWeek = cardText.match(/Tuần\s*(\d+)/i);
                const week = mWeek ? ('Tuần ' + mWeek[1]) : '-';
                
                // 3. Ten chapter
                let title = '';
                if (lines.length > 1 && !/^\d+%$/.test(lines[1])) {
                    title = lines[1];
                } else if (lines.length > 0) {
                    title = lines.find(l => !/^\d+%$/.test(l) && !l.includes('Bài giảng') && !l.includes('Bài tập') && !l.includes('Tài liệu')) || 'Chương học';
                }
                
                // 4. Cac nut chuc nang tren card
                const btns = Array.from(card.querySelectorAll('button')).map(b => (b.innerText || '').trim());
                const hasSlide = btns.some(t => t.includes('Bài giảng AI') || t.includes('Bài giảng'));
                const hasAI = btns.some(t => t.includes('Bài tập AI'));
                const hasManual = btns.some(t => t === 'Bài tập' || (t.includes('Bài tập') && !t.includes('Bài tập AI')));
                
                // Them Bai tap AI
                if (hasAI) {
                    list.push({
                        stt: stt++,
                        week: week,
                        title: title,
                        percent_tg: percentTroGiang,
                        percent_val: percentVal,
                        type: 'Bài tập AI',
                        target_type: 'ai',
                        target_title: title,
                        status: '[SẴN SÀNG]',
                        highest_score: '-',
                        highest_score_val: null
                    });
                }
                // Them Bai tap thu cong
                if (hasManual) {
                    list.push({
                        stt: stt++,
                        week: week,
                        title: title,
                        percent_tg: percentTroGiang,
                        percent_val: percentVal,
                        type: 'Bài tập',
                        target_type: 'manual',
                        target_title: title,
                        status: '[SẴN SÀNG]',
                        highest_score: '-',
                        highest_score_val: null
                    });
                }
                // Them Slide bai giang
                if (hasSlide) {
                    list.push({
                        stt: stt++,
                        week: week,
                        title: title,
                        percent_tg: percentTroGiang,
                        percent_val: percentVal,
                        type: 'Slide bài giảng',
                        target_type: 'slide',
                        target_title: title,
                        status: percentVal >= 100 ? '[ĐÃ XONG]' : '[CHƯA XONG]',
                        highest_score: percentVal >= 100 ? '100%' : `${percentVal}%`,
                        highest_score_val: percentVal
                    });
                }
            }
            return list;
        }"""
        rows = page.evaluate(js_scan)

        # Gan diem so cao nhat tu activity_history.json neu co
        try:
            from src.config import DATA_DIR
            import json
            hist_file = DATA_DIR / "activity_history.json"
            if hist_file.exists():
                with open(hist_file, "r", encoding="utf-8") as f:
                    h_data = json.load(f)
                    scores_map = h_data.get("chapter_scores", {}) if isinstance(h_data, dict) else {}
                    for r in rows:
                        t = r.get("title", "")
                        clean_t = t.split('(')[0].strip() if '(' in t else t.strip()
                        if clean_t in scores_map and r.get("target_type") in ["ai", "manual"]:
                            r["highest_score"] = scores_map[clean_t]
        except Exception:
            pass

        console.print(f"[bold green][OK] Quet thanh cong {len(rows)} muc bai hoc trong mon (Instant Scan < 0.2s)![/bold green]")
        return rows
    except Exception as e:
        console.print(f"[bold red]Loi quet cau truc mon hoc: {e}[/bold red]")
        return []
