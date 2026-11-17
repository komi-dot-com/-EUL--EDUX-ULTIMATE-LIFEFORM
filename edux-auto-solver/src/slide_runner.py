import time
from typing import Dict, Any, Optional, List
from playwright.sync_api import Page
from rich.panel import Panel

from src.utils import console
from src.ai_solver import AICodingSolver

# =============================================================================
# CÔNG CỤ CMCU-VẠN-NĂNG V3.2 FIX (DO NGƯỜI DÙNG PHÁT TRIỂN)
# Chạy trực tiếp trong lõi DOM Chrome (setInterval 80ms + MutationObserver)
# Đã sửa lỗi tự qua câu & lỗi dừng sớm (xác nhận trang cuối 3 nhịp liên tiếp)!
# =============================================================================
IN_BROWSER_SLIDE_ENGINE_JS = r"""
(function () {
    'use strict';

    console.log("%c⚡ [CMCU-Vạn-Năng-V3.2 FIX] Đã sửa lỗi tự qua câu & lỗi dừng sớm (3/3)!", "color: #00ffcc; font-weight: bold; font-size: 15px;");
    console.log("%c👉 Gõ lệnh: stop() và ấn Enter nếu muốn dừng thủ công.", "color: #ff9900; font-weight: bold;");

    if (window.cmcuGlobalLoopId) clearInterval(window.cmcuGlobalLoopId);
    if (window.cmcuObserver) window.cmcuObserver.disconnect();

    const questionMemory = window.cmcuQuestionMemory || new Map();
    window.cmcuQuestionMemory = questionMemory;

    window.cmcuStopped = false;
    window.cmcuFinished = false;
    window.cmcuQuestionsSolved = 0;
    window.cmcuCurrentPage = 0;
    window.cmcuTotalPage = 0;
    window.cmcuStopReason = "";

    let isBusy = false;
    let busyTimer = null;
    let endPageConfirmCount = 0; // Đếm xác nhận trang cuối liên tiếp để chống tắt nhầm

    function lock(ms = 120) {
        isBusy = true;
        clearTimeout(busyTimer);
        busyTimer = setTimeout(() => { isBusy = false; }, ms);
    }

    function norm(str) {
        return (str || '').replace(/\s+/g, ' ').trim().toLowerCase();
    }

    function isClickable(el) {
        if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0' || style.pointerEvents === 'none') return false;
        return el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0;
    }

    function clickChuotThat(element) {
        if (!element) return;
        const opts = { bubbles: true, cancelable: true, view: window };
        element.dispatchEvent(new PointerEvent('pointerdown', opts));
        element.dispatchEvent(new MouseEvent('mousedown', opts));
        element.dispatchEvent(new PointerEvent('pointerup', opts));
        element.dispatchEvent(new MouseEvent('mouseup', opts));
        element.dispatchEvent(new MouseEvent('click', opts));
    }

    function getQuestionState(khungCauHoi) {
        const dialog = khungCauHoi.closest('[role="dialog"], main, .bg-white, body');
        const headerEl = dialog ? dialog.querySelector('h1, h2, h3, h4, p, .font-semibold, .font-bold') : null;
        const headerText = headerEl ? norm(headerEl.textContent).slice(0, 80) : '';
        const optionsText = Array.from(khungCauHoi.children).map(el => norm(el.textContent)).join('|');
        const key = `${headerText}__${optionsText}` || 'default_key';

        if (!questionMemory.has(key)) {
            questionMemory.set(key, {
                blacklist: new Set(),
                lastPicked: null,
                hint: null
            });
        }
        return questionMemory.get(key);
    }

    function getOptionBoxes(khungCauHoi) {
        let boxes = Array.from(khungCauHoi.querySelectorAll('div[class*="border-2"], [data-slot="radio-group"] > div'));
        if (boxes.length === 0) {
            boxes = Array.from(khungCauHoi.children).filter(el => el.querySelector('button[role="radio"], input[type="radio"]'));
        }
        return boxes;
    }

    function updatePageCounterSnapshot() {
        try {
            const tatCaNut = Array.from(document.querySelectorAll('button, a, [role="button"]'));
            const nutTrangSauDOM = tatCaNut.find(el => norm(el.textContent).includes('trang sau'));
            const nutTrangTruocDOM = tatCaNut.find(el => norm(el.textContent).includes('trang trước'));
            const thanhDieuHuong = (nutTrangSauDOM && nutTrangSauDOM.parentElement) || (nutTrangTruocDOM && nutTrangTruocDOM.parentElement);
            if (thanhDieuHuong) {
                const navText = norm(thanhDieuHuong.textContent);
                const matchPage = navText.match(/\b(\d+)\s*\/\s*(\d+)\b/);
                if (matchPage && !navText.includes('câu')) {
                    window.cmcuCurrentPage = parseInt(matchPage[1], 10);
                    window.cmcuTotalPage = parseInt(matchPage[2], 10);
                    return;
                }
            }
            const pagePattern = /^(\d+)\s*\/\s*(\d+)$/;
            const elCounter = Array.from(document.querySelectorAll('span, p, div, output')).find(el => pagePattern.test(norm(el.textContent)));
            if (elCounter) {
                const m = norm(elCounter.textContent).match(pagePattern);
                if (m) {
                    window.cmcuCurrentPage = parseInt(m[1], 10);
                    window.cmcuTotalPage = parseInt(m[2], 10);
                }
            }
        } catch (e) {}
    }

    window.stop = function (reason = "Đã dừng thủ công.") {
        if (window.cmcuGlobalLoopId) {
            clearInterval(window.cmcuGlobalLoopId);
            window.cmcuGlobalLoopId = null;
        }
        if (window.cmcuObserver) {
            window.cmcuObserver.disconnect();
            window.cmcuObserver = null;
        }
        isBusy = false;
        window.cmcuStopped = true;
        window.cmcuStopReason = reason;
        if (reason.includes("Đã hoàn thành toàn bộ bài học")) {
            window.cmcuFinished = true;
        }
        console.log(`%c🛑 [CMCU-Vạn-Năng-V3.2] HỆ THỐNG ĐÃ TỰ TẮT: ${reason}`, "color: #00ff66; background: #112211; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 14px;");
    };

    window.cmcuStop = window.stop;

    window.cmcuGetProgress = function () {
        updatePageCounterSnapshot();
        return {
            current: window.cmcuCurrentPage || 0,
            total: window.cmcuTotalPage || 0,
            isFinished: Boolean(window.cmcuFinished),
            isStopped: Boolean(window.cmcuStopped),
            stopReason: window.cmcuStopReason || "",
            questionsSolved: window.cmcuQuestionsSolved || 0
        };
    };

    function coreProcessor() {
        if (isBusy) return;

        updatePageCounterSnapshot();

        const khungCauHoi = document.querySelector('[role="radiogroup"], [data-slot="radio-group"]');
        const popupContainer = khungCauHoi ? (khungCauHoi.closest('[role="dialog"]') || khungCauHoi.closest('.fixed') || document.body) : null;

        // =========================================================================
        // TRƯỜNG HỢP A: ĐANG MỞ BẢNG CÂU HỎI TRẮC NGHIỆM (XỬ LÝ GỌN TRONG POPUP)
        // =========================================================================
        if (khungCauHoi && popupContainer) {
            endPageConfirmCount = 0; // Đang làm câu hỏi thì không bao giờ tính là kết thúc trang
            const nutTrongPopup = Array.from(popupContainer.querySelectorAll('button, a, [role="button"]')).filter(isClickable);
            const popupText = popupContainer.textContent || '';

            const isWrong = popupText.includes('Chưa đúng') || popupText.includes('Đáp án đúng:');
            const isCorrect = popupText.includes('Chính xác!');

            // A1. NẾU ĐÃ TRẢ LỜI ĐÚNG ("Chính xác!") -> BẤM "CÂU TIẾP THEO" HOẶC "TRANG SAU" NGAY LẬP TỨC
            const nutQuaCauPopup = nutTrongPopup.find(el => {
                const txt = norm(el.textContent);
                return txt === 'câu tiếp theo' || txt === 'câu tiếp' || txt === 'tiếp theo' || txt === 'trang sau' || txt === 'hoàn thành' || txt === 'tiếp tục';
            });

            if (isCorrect || nutQuaCauPopup) {
                if (nutQuaCauPopup) {
                    window.cmcuQuestionsSolved = (window.cmcuQuestionsSolved || 0) + 1;
                    lock(150);
                    clickChuotThat(nutQuaCauPopup);
                    return;
                }
            }

            // A2. NẾU TRẢ LỜI SAI ("Chưa đúng") -> LƯU ĐÁP ÁN SAI VÀ BẤM "THỬ LẠI"
            if (isWrong) {
                const qState = getQuestionState(khungCauHoi);

                const matchHint = popupText.match(/Đáp án đúng:\s*([^\n\r]+)/i);
                if (matchHint && matchHint[1]) {
                    qState.hint = norm(matchHint[1]);
                }

                if (qState.lastPicked) {
                    qState.blacklist.add(qState.lastPicked);
                    qState.lastPicked = null;
                } else {
                    const boxes = getOptionBoxes(khungCauHoi);
                    for (const box of boxes) {
                        const radio = box.querySelector('button[role="radio"], input[type="radio"]');
                        if (radio && (radio.getAttribute('data-state') === 'checked' || radio.getAttribute('aria-checked') === 'true' || radio.checked)) {
                            qState.blacklist.add(norm(box.textContent));
                            break;
                        }
                    }
                }

                const nutThuLai = nutTrongPopup.find(el => norm(el.textContent) === 'thử lại');
                if (nutThuLai) {
                    lock(100);
                    clickChuotThat(nutThuLai);
                    return;
                }
            }

            // A3. CHỌN ĐÁP ÁN VÀ BẤM "KIỂM TRA"
            if (!isWrong && !isCorrect) {
                const qState = getQuestionState(khungCauHoi);
                const options = getOptionBoxes(khungCauHoi);

                let checkedBox = null;
                for (const box of options) {
                    const radio = box.querySelector('button[role="radio"], input[type="radio"]');
                    if (radio && (radio.getAttribute('data-state') === 'checked' || radio.getAttribute('aria-checked') === 'true' || radio.checked)) {
                        checkedBox = box;
                        break;
                    }
                }

                const nutKiemTra = nutTrongPopup.find(el => {
                    const txt = norm(el.textContent);
                    return txt === 'kiểm tra' || txt === 'xác nhận' || txt === 'nộp bài';
                });

                const isCheckedBlacklisted = checkedBox && qState.blacklist.has(norm(checkedBox.textContent));

                if ((!checkedBox || isCheckedBlacklisted) && options.length > 0) {
                    if (qState.blacklist.size >= options.length) {
                        qState.blacklist.clear();
                    }

                    let targetBox = null;
                    if (qState.hint) {
                        targetBox = options.find(box => {
                            const t = norm(box.textContent);
                            return t === qState.hint || t.includes(qState.hint) || qState.hint.includes(t);
                        });
                    }

                    if (!targetBox) {
                        targetBox = options.find(box => !qState.blacklist.has(norm(box.textContent)));
                    }

                    if (targetBox) {
                        qState.lastPicked = norm(targetBox.textContent);
                        const radioBtn = targetBox.querySelector('button[role="radio"], input[type="radio"]') || targetBox;
                        lock(90);
                        clickChuotThat(radioBtn);

                        setTimeout(() => {
                            const btnSubmit = Array.from(popupContainer.querySelectorAll('button, [role="button"]'))
                                .filter(isClickable)
                                .find(el => {
                                    const txt = norm(el.textContent);
                                    return txt === 'kiểm tra' || txt === 'xác nhận' || txt === 'nộp bài';
                                });
                            if (btnSubmit) clickChuotThat(btnSubmit);
                        }, 35);
                        return;
                    }
                }

                if (checkedBox && !isCheckedBlacklisted && nutKiemTra) {
                    qState.lastPicked = norm(checkedBox.textContent);
                    lock(100);
                    clickChuotThat(nutKiemTra);
                    return;
                }
            }
            return;
        }

        // =========================================================================
        // TRƯỜNG HỢP B: ĐANG Ở NGOÀI TRANG BÀI HỌC CHÍNH (KHÔNG CÓ POPUP CÂU HỎI)
        // =========================================================================
        const tatCaNut = Array.from(document.querySelectorAll('button, a, [role="button"]'));
        const danhSachNut = tatCaNut.filter(isClickable);

        // B1. NẾU CÓ NÚT MỞ CÂU HỎI ("Trả lời trên lớp" / "Làm bài tập") -> MỞ NGAY
        const nutMoCauHoi = danhSachNut.find(el => {
            const txt = norm(el.textContent);
            return txt.includes('trả lời trên lớp') || txt.includes('làm bài tập') || txt.includes('bắt đầu làm');
        });

        if (nutMoCauHoi) {
            endPageConfirmCount = 0;
            lock(180);
            clickChuotThat(nutMoCauHoi);
            return;
        }

        // B2. NẾU NÚT "TRANG SAU" ĐANG BẤM ĐƯỢC -> BẤM CHUYỂN TRANG
        const nutChuyenTrang = danhSachNut.find(el => {
            const txt = norm(el.textContent);
            if (txt.length > 30) return false;
            return txt.includes('trang sau') || txt.includes('bài sau') || txt === 'tiếp theo' || txt === 'next';
        });

        if (nutChuyenTrang) {
            endPageConfirmCount = 0;
            lock(250);
            clickChuotThat(nutChuyenTrang);
            return;
        }

        // B3. KIỂM TRA TRANG CUỐI CHÍNH XÁC (Chỉ đọc thanh điều hướng cạnh nút "Trang trước" / "Trang sau")
        const nutTrangSauDOM = tatCaNut.find(el => norm(el.textContent).includes('trang sau'));
        const nutTrangTruocDOM = tatCaNut.find(el => norm(el.textContent).includes('trang trước'));
        const thanhDieuHuong = (nutTrangSauDOM && nutTrangSauDOM.parentElement) || (nutTrangTruocDOM && nutTrangTruocDOM.parentElement);

        if (thanhDieuHuong && nutTrangSauDOM && !isClickable(nutTrangSauDOM)) {
            // Tách riêng văn bản trên thanh điều hướng trang (loại trừ hoàn toàn chữ "câu đúng")
            const navText = norm(thanhDieuHuong.textContent);
            const matchPage = navText.match(/\b(\d+)\s*\/\s*(\d+)\b/);

            if (matchPage && !navText.includes('câu')) {
                const curPage = parseInt(matchPage[1], 10);
                const maxPage = parseInt(matchPage[2], 10);

                if (curPage > 0 && curPage === maxPage) {
                    endPageConfirmCount++;
                    // Đợi xác nhận ổn định 3 nhịp liên tiếp (~300ms) để chắc chắn không phải lúc đang tải trang
                    if (endPageConfirmCount >= 3) {
                        window.stop(`Đã hoàn thành toàn bộ bài học tại trang cuối (${curPage}/${maxPage})!`);
                    }
                    return;
                }
            }
        } else {
            endPageConfirmCount = 0;
        }
    }

    let rafScheduled = false;
    window.cmcuObserver = new MutationObserver(() => {
        if (!rafScheduled && !isBusy) {
            rafScheduled = true;
            requestAnimationFrame(() => {
                rafScheduled = false;
                coreProcessor();
            });
        }
    });

    window.cmcuObserver.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['data-state', 'aria-checked', 'disabled', 'class']
    });

    window.cmcuGlobalLoopId = setInterval(coreProcessor, 80);
})();
"""


class SlideRunner:
    """
    Bộ điều khiển Slide bài giảng tự động 100% Trợ giảng.
    - Sử dụng trực tiếp công cụ CMCU-Vạn-Năng-V3.2 FIX do người dùng phát triển.
    - Hỗ trợ tự động chuyển sang Bài giảng AI tiếp theo liên hoàn cho đến khi hết toàn bộ môn học!
    """
    def __init__(
        self,
        page: Page,
        solver: Optional[AICodingSolver] = None,
        reading_delay: float = 0.25,
        context: Any = None
    ):
        self.page = page
        self.solver = solver
        self.reading_delay = reading_delay
        self.context = context or (page.context if page else None)
        self.running = False

    def _sync_active_edux_page(self) -> Page:
        """Đảm bảo luôn bám sát tab EduX đang mở (phòng trường hợp bấm nút Bài giảng AI mở tab mới)."""
        if not self.context:
            return self.page
        try:
            live_pages = [p for p in self.context.pages if not p.is_closed()]
            edux_pages = [p for p in live_pages if "edux.cmcu.edu.vn" in (p.url or "").lower()]
            for p in reversed(edux_pages):
                try:
                    if p.evaluate("() => document.visibilityState === 'visible' && !document.hidden"):
                        self.page = p
                        return p
                except Exception:
                    pass
            if edux_pages:
                self.page = edux_pages[-1]
        except Exception:
            pass
        return self.page

    def is_currently_inside_slide_viewer(self) -> bool:
        """Kiểm tra xem trang hiện tại có đang ở trong giao diện đọc Slide bài giảng AI hay không."""
        try:
            return bool(self.page.evaluate("""() => {
                const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const btns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                const hasNavBtn = btns.some(el => {
                    const t = norm(el.textContent);
                    return t.includes('trang sau') || t.includes('trang trước');
                });
                if (hasNavBtn) return true;
                const pagePattern = /^(\\d+)\\s*\\/\\s*(\\d+)$/;
                return Array.from(document.querySelectorAll('span, p, div, output')).some(el => pagePattern.test(norm(el.textContent)));
            }"""))
        except Exception:
            return False

    def get_current_slide_title(self) -> str:
        """Lấy tiêu đề bài giảng AI đang mở trên màn hình."""
        try:
            title = self.page.evaluate("""() => {
                const el = document.querySelector('h1, h2, h3, [class*="truncate"][class*="font-bold"], [class*="font-semibold"]');
                return el ? (el.innerText || '').trim() : '';
            }""")
            return title or "Bài giảng AI"
        except Exception:
            return "Bài giảng AI"

    def return_to_course_list(self, fallback_subject_url: Optional[str] = None) -> bool:
        """
        Tự động thoát khỏi màn hình Slide hiện tại để quay về danh sách chương của môn học (/subject)
        để tìm Bài giảng AI tiếp theo.
        """
        from src.automator import close_dialog_if_open

        for _ in range(3):
            try:
                close_dialog_if_open(self.page)
            except Exception:
                pass

            # Kiểm tra xem đã thấy các thẻ chương (div.bg-card có nút Bài giảng) chưa
            try:
                has_course_cards = self.page.evaluate("""() => {
                    const cards = Array.from(document.querySelectorAll('div.bg-card'));
                    return cards.some(c => {
                        const btns = Array.from(c.querySelectorAll('button')).map(b => (b.innerText || '').trim());
                        return btns.some(t => t.includes('Bài giảng') || t.includes('Bài tập'));
                    });
                }""")
                if has_course_cards:
                    return True
            except Exception:
                pass

            # 1. Thử bấm nút Quay lại / Đóng / Mũi tên thoát trên góc trái giao diện bài giảng
            try:
                clicked_back = self.page.evaluate("""() => {
                    const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const candidates = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                    const backBtn = candidates.find(el => {
                        const t = norm(el.textContent);
                        const aria = norm(el.getAttribute('aria-label') || el.getAttribute('title') || '');
                        if (t.includes('trang trước') || t.includes('câu trước')) return false;
                        return (
                            t === 'quay lại' ||
                            t === 'đóng' ||
                            t === 'thoát' ||
                            t.includes('quay lại môn') ||
                            t.includes('danh sách bài') ||
                            aria.includes('quay lại') ||
                            aria.includes('back') ||
                            aria.includes('close') ||
                            el.querySelector('svg.lucide-arrow-left, svg.lucide-chevron-left, svg.lucide-x')
                        );
                    });
                    if (backBtn) {
                        backBtn.click();
                        return true;
                    }
                    return false;
                }""")
                if clicked_back:
                    self.page.wait_for_timeout(1800)
                    self._sync_active_edux_page()
            except Exception:
                pass

            # Kiểm tra lại sau khi click nút Back trên UI
            try:
                has_course_cards = self.page.evaluate("""() => {
                    const cards = Array.from(document.querySelectorAll('div.bg-card'));
                    return cards.some(c => (c.innerText || '').includes('Bài giảng'));
                }""")
                if has_course_cards:
                    return True
            except Exception:
                pass

            # 2. Nếu có URL trang danh sách môn học đã lưu hoặc dùng go_back()
            try:
                if fallback_subject_url and "/subject" in fallback_subject_url:
                    self.page.goto(fallback_subject_url, wait_until="domcontentloaded", timeout=15000)
                else:
                    self.page.go_back(wait_until="domcontentloaded", timeout=10000)
                self.page.wait_for_timeout(2000)
            except Exception:
                pass

        return False

    def open_next_slide_from_course_page(self, visited_titles: Set[str]) -> Optional[str]:
        """
        Tìm và bấm mở Bài giảng AI tiếp theo trên trang môn học:
        - Ưu tiên 1: Các chương có tiến độ < 100% và chưa chạy trong lượt này.
        - Ưu tiên 2: Nếu tất cả đã 100%, chọn bài giảng tiếp theo theo thứ tự từ trên xuống chưa nằm trong visited_titles (nếu chỉ chạy các bài < 100% thì dừng ngay khi hết bài < 100%).
        Trả về tên chương vừa mở, hoặc None nếu đã hết sạch bài giảng!
        """
        try:
            visited_list = list(visited_titles)
            next_title = self.page.evaluate("""(visitedList) => {
                const visitedSet = new Set(visitedList.map(s => s.trim().toLowerCase()));
                const cards = Array.from(document.querySelectorAll('div.bg-card')).filter(c => {
                    const btns = Array.from(c.querySelectorAll('button')).map(b => (b.innerText || '').trim());
                    return btns.some(t => t.includes('Bài giảng AI') || t.includes('Bài giảng'));
                });

                for (const card of cards) {
                    const cardText = (card.innerText || '').trim();
                    const lines = cardText.split('\\n').map(l => l.trim()).filter(Boolean);

                    let title = '';
                    if (lines.length > 1 && !/^\\d+%$/.test(lines[1])) {
                        title = lines[1];
                    } else if (lines.length > 0) {
                        title = lines.find(l => !/^\\d+%$/.test(l) && !l.includes('Bài giảng') && !l.includes('Bài tập') && !l.includes('Tài liệu')) || 'Chương học';
                    }

                    const normTitle = title.trim().toLowerCase();
                    if (visitedSet.has(normTitle)) continue;

                    const mPct = cardText.match(/(\\d+)%/);
                    const pct = mPct ? parseInt(mPct[1], 10) : 0;

                    // Chỉ mở các bài giảng chưa đạt 100% (hoặc chưa hoàn thành)
                    if (pct < 100) {
                        const btn = Array.from(card.querySelectorAll('button')).find(b => {
                            const t = (b.innerText || '').trim();
                            return t.includes('Bài giảng AI') || t.includes('Bài giảng');
                        });
                        if (btn && !btn.disabled) {
                            btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            btn.click();
                            return title;
                        }
                    }
                }
                return null;
            }""", visited_list)
            return next_title
        except Exception:
            return None

    def count_remaining_uncompleted_slides(self, visited_titles: Set[str]) -> int:
        """Đếm số lượng Bài giảng AI có tiến độ < 100% còn lại trên trang môn học."""
        try:
            visited_list = list(visited_titles)
            return int(self.page.evaluate("""(visitedList) => {
                const visitedSet = new Set(visitedList.map(s => s.trim().toLowerCase()));
                const cards = Array.from(document.querySelectorAll('div.bg-card')).filter(c => {
                    const btns = Array.from(c.querySelectorAll('button')).map(b => (b.innerText || '').trim());
                    return btns.some(t => t.includes('Bài giảng AI') || t.includes('Bài giảng'));
                });
                let count = 0;
                for (const card of cards) {
                    const cardText = (card.innerText || '').trim();
                    const lines = cardText.split('\\n').map(l => l.trim()).filter(Boolean);
                    let title = '';
                    if (lines.length > 1 && !/^\\d+%$/.test(lines[1])) {
                        title = lines[1];
                    } else if (lines.length > 0) {
                        title = lines.find(l => !/^\\d+%$/.test(l) && !l.includes('Bài giảng') && !l.includes('Bài tập') && !l.includes('Tài liệu')) || 'Chương học';
                    }
                    if (visitedSet.has(title.trim().toLowerCase())) continue;
                    const mPct = cardText.match(/(\\d+)%/);
                    const pct = mPct ? parseInt(mPct[1], 10) : 0;
                    if (pct < 100) count++;
                }
                return count;
            }""", visited_list))
        except Exception:
            return 0

    def run_single_slide_deck(self, deck_label: str = "") -> bool:
        """
        Khởi chạy công cụ CMCU-Vạn-Năng-V3.2 FIX cho 1 bài giảng AI đang mở trên màn hình.
        """
        from src.web.server import state

        label_display = f" ({deck_label})" if deck_label else ""
        console.print(Panel(
            f"[bold cyan]KHỞI ĐỘNG CÔNG CỤ CMCU-VẠN-NĂNG V3.2 FIX{label_display}:[/bold cyan]\n"
            "- Kiến trúc: [bold green]CMCU-Vạn-Năng-V3.2 FIX (setInterval 80ms + MutationObserver)[/bold green]\n"
            "- Giải câu hỏi: [bold magenta]Tự động dò Hint + Blacklist & Tự qua câu tức thì[/bold magenta]\n"
            "- Chống dừng sớm: [bold yellow]Xác nhận ổn định 3 nhịp liên tiếp tại trang cuối (3/3)[/bold yellow]",
            title="[CMCU-VẠN-NĂNG V3.2 FIX]",
            border_style="cyan"
        ))

        state.broadcast_log(f"[CMCU-VẠN-NĂNG V3.2 FIX] Đang chạy bài giảng{label_display}...")

        try:
            self.page.evaluate(IN_BROWSER_SLIDE_ENGINE_JS)
        except Exception as e:
            state.broadcast_log(f"[X] Lỗi khởi động CMCU-Vạn-Năng-V3.2: {e}")
            return False

        last_logged_page = 0
        last_q_solved = 0

        try:
            while True:
                if state.stop_requested:
                    try:
                        self.page.evaluate("() => window.stop && window.stop('Người dùng yêu cầu dừng')")
                    except Exception:
                        pass
                    state.broadcast_log("[STOP] Đã dừng CMCU-Vạn-Năng-V3.2 theo yêu cầu!")
                    return False

                prog = None
                try:
                    prog = self.page.evaluate("() => window.cmcuGetProgress ? window.cmcuGetProgress() : null")
                except Exception:
                    pass

                if prog:
                    curr = prog.get("current", 0)
                    total = prog.get("total", 0)
                    is_fin = prog.get("isFinished", False)
                    is_stop = prog.get("isStopped", False)
                    stop_reason = prog.get("stopReason", "")
                    q_solved = prog.get("questionsSolved", 0)

                    if total > 0 and curr > 0:
                        state.progress_current = curr
                        state.progress_total = total
                        state.progress_percent = int((curr / total) * 100)
                        prefix = f"[{deck_label}] " if deck_label else "[CMCU V3.2] "
                        state.step_label = f"{prefix}Đang lướt slide {curr}/{total} ({state.progress_percent}%)"

                        if curr != last_logged_page:
                            last_logged_page = curr
                            state.broadcast_log(f"[SLIDE] {deck_label or 'Bài giảng'} - Trang {curr} / {total}")
                            console.print(
                                f"[bold cyan][CMCU-V3.2][/bold cyan] {deck_label} | Trang [bold yellow]{curr}[/bold yellow] / [bold green]{total}[/bold green]"
                            )

                    if q_solved > last_q_solved:
                        last_q_solved = q_solved
                        state.broadcast_log(f"[QUESTION] Đã giải & qua câu thành công ({q_solved} câu trên slide)!")

                    if is_fin or is_stop:
                        state.progress_percent = 100
                        msg_done = stop_reason or f"Đã hoàn thành bài học ({curr}/{total})!"
                        state.step_label = msg_done
                        state.broadcast_log(f"[OK] {deck_label}: {msg_done}")
                        console.print(f"[bold green]=== [HOÀN TẤT SLIDE] {deck_label}: {msg_done} ===[/bold green]")
                        break

                time.sleep(0.3)

        except Exception as err:
            state.broadcast_log(f"[X] Lỗi tiến trình slide: {err}")
            return False

        return True

    def run_current_slide_deck(self, max_slides: int = 150, auto_next_lesson: bool = True) -> bool:
        """
        Chạy Slide học liệu hiện tại và TỰ ĐỘNG CHUYỂN SANG BÀI GIẢNG AI TIẾP THEO
        cho đến khi hoàn thành hết toàn bộ các bài giảng trong môn học!
        """
        from src.web.server import state

        visited_titles: Set[str] = set()
        completed_decks = 0
        course_list_url: Optional[str] = None

        # Nếu ban đầu đang ở ngoài trang danh sách chương (/subject), lưu lại URL danh sách môn học
        if not self.is_currently_inside_slide_viewer() and "/subject" in (self.page.url or "").lower():
            course_list_url = self.page.url

        while True:
            if state.stop_requested:
                break

            self._sync_active_edux_page()

            # 1. Nếu đang ở ngoài trang danh sách môn học (/subject), tìm mở Bài giảng AI tiếp theo chưa xong (< 100%)
            if not self.is_currently_inside_slide_viewer():
                if "/subject" in (self.page.url or "").lower():
                    course_list_url = self.page.url

                next_title = self.open_next_slide_from_course_page(visited_titles)
                if not next_title:
                    if completed_decks == 0:
                        state.broadcast_log("[OK] Tất cả Bài giảng AI trong môn học này đều đã đạt 100%!")
                        console.print("[bold green][OK] Tất cả Bài giảng AI trong môn học này đều đã đạt 100%![/bold green]")
                    else:
                        state.broadcast_log(
                            f"[HOÀN TẤT CHUỖI SLIDE] Đã chạy xong liên hoàn {completed_decks} Bài giảng AI! Không còn bài giảng nào chưa hoàn thành."
                        )
                        console.print(Panel(
                            f"[bold green]ĐÃ HOÀN THÀNH TOÀN BỘ CHUỖI BÀI GIẢNG AI TRONG MÔN HỌC![/bold green]\n"
                            f"- Tổng số bài giảng đã hoàn thành trong phiên: [bold yellow]{completed_decks} bài[/bold yellow]\n"
                            f"- Trạng thái: [bold cyan]100% Trợ giảng toàn môn[/bold cyan]",
                            title="[HOÀN TẤT LIÊN HOÀN]",
                            border_style="green"
                        ))
                    break

                visited_titles.add(next_title.strip().lower())
                state.broadcast_log(f"[AUTO-NEXT] Đang mở Bài giảng AI: {next_title}...")
                console.print(f"\n[bold yellow]>>> [CHUYỂN BÀI GIẢNG AI TIẾP THEO]: {next_title} <<<[/bold yellow]")
                self.page.wait_for_timeout(2500)
                self._sync_active_edux_page()
                current_title = next_title
            else:
                current_title = self.get_current_slide_title()
                if current_title:
                    visited_titles.add(current_title.strip().lower())

            # 2. Chạy CMCU-Vạn-Năng V3.2 FIX cho bài giảng đang mở
            state.current_task = f"Slide AI: {current_title}"
            ok = self.run_single_slide_deck(deck_label=current_title)
            if not ok or state.stop_requested:
                break

            completed_decks += 1
            state.add_history(
                entry_type="slide",
                title=f"Slide: {current_title}",
                detail=f"Môn: {state.subject_name} ({state.progress_current}/{state.progress_total} trang)",
                score="100% Trợ giảng",
                status="Hoàn thành"
            )

            if not auto_next_lesson:
                break

            # 3. Sau khi xong 1 bài giảng, tự động quay ra trang danh sách chương để chuyển sang Bài giảng AI tiếp theo
            state.broadcast_log(
                f"[AUTO-NEXT] Đã xong '{current_title}', đang quay về danh sách môn học để tìm Bài giảng AI tiếp theo..."
            )
            console.print(
                f"[cyan][*] Đã xong '{current_title}', đang kiểm tra Bài giảng AI tiếp theo...[/cyan]"
            )
            self.page.wait_for_timeout(1200)

            returned = self.return_to_course_list(fallback_subject_url=course_list_url)
            if not returned:
                state.broadcast_log("[!] Không thể quay về danh sách chương tự động, dừng chuỗi tại đây.")
                break

            self.page.wait_for_timeout(1800)
            rem = self.count_remaining_uncompleted_slides(visited_titles)
            if rem > 0:
                state.broadcast_log(f"[AUTO-NEXT] Phát hiện còn {rem} Bài giảng AI chưa hoàn thành, tiếp tục chạy tự động...")
            else:
                state.broadcast_log(
                    f"[HOÀN TẤT CHUỖI SLIDE] Đã hoàn thành toàn bộ {completed_decks} Bài giảng AI trong môn học!"
                )
                console.print(Panel(
                    f"[bold green]ĐÃ HOÀN THÀNH TOÀN BỘ BÀI GIẢNG AI TRONG MÔN HỌC![/bold green]\n"
                    f"- Tổng số bài giảng vừa chạy xong: [bold yellow]{completed_decks} bài[/bold yellow]",
                    title="[100% BÀI GIẢNG AI]",
                    border_style="green"
                ))
                break

        return completed_decks > 0
