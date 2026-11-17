#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 EDUX ULTIMATE LIFEFORM (EUL) v0.6 - CMCU LMS (WEB DASHBOARD & CLI CONTROL CENTER)
 Công nghệ: Python + Playwright CDP + AI Coding CLI (Antigravity & Codex)
 Slide Engine: CMCU-Vạn-Năng V3.2 FIX (3/3 Confirm)
=============================================================================
"""

import os
import sys
import time
import queue
import atexit
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright
from rich.panel import Panel
from rich.text import Text

# Thêm root folder vào sys.path để import các module trong src/
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    BASE_URL,
    CDP_URL,
    ENV_PATH,
    ALLOWED_DOMAINS,
    CHROME_PROFILE_DIR,
    AI_PROVIDER,
    AI_MODEL,
    AI_EFFORT
)
from src.utils import console, is_allowed_domain, cleanup_chrome_cache_safe
from src.storage import QuestionCache
from src.ai_solver import AICodingSolver
from src.automator import (
    EduxAutomator,
    get_current_subject_name,
    scan_course_full_structure,
    close_dialog_if_open,
    wait_and_start_quiz
)
from src.slide_runner import SlideRunner
from src.cli import ensure_chrome_running, run_solver_workflow, main_menu, save_ai_cli_config
from src.web import start_web_server, state


def get_active_edux_page(context, current_page=None):
    """
    Tự động tìm và duy trì tab edux.cmcu.edu.vn đang hoạt động (alive).
    TUYỆT ĐỐI không trả về tab đã đóng hoặc tab ngoài domain EduX.
    """
    try:
        live_pages = [p for p in context.pages if not p.is_closed()]
    except Exception:
        return None

    if not live_pages:
        return None

    edux_pages = []
    for p in live_pages:
        try:
            u = (p.url or "").lower()
            if "edux.cmcu.edu.vn" in u:
                edux_pages.append(p)
        except Exception:
            pass

    # 1. Ưu tiên tab EduX đang hiển thị trên màn hình (visible)
    for p in reversed(edux_pages):
        try:
            vis = p.evaluate("() => document.visibilityState === 'visible' && !document.hidden")
            if vis:
                return p
        except Exception:
            pass

    # 2. Ưu tiên tab EduX có URL /subject (trang môn học hoặc slide/bài tập)
    for p in reversed(edux_pages):
        try:
            if "/subject" in (p.url or "").lower():
                return p
        except Exception:
            pass

    # 3. Tab EduX bất kỳ
    if edux_pages:
        if current_page and not current_page.is_closed() and current_page in edux_pages:
            return current_page
        return edux_pages[-1]

    # 4. Nếu có current_page hợp lệ thuộc EduX
    if current_page and not current_page.is_closed():
        try:
            if "edux.cmcu.edu.vn" in (current_page.url or "").lower():
                return current_page
        except Exception:
            pass

    return None


def parse_args():
    parser = argparse.ArgumentParser(
        description="EDUX ULTIMATE LIFEFORM (EUL) v0.6 - AI Coding CLI (Antigravity & Codex) + CMCU-Vạn-Năng V3.2 FIX"
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Mở trực tiếp Bảng điều khiển CLI v0.6 trên Terminal"
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Chạy chế độ lắng nghe Web Dashboard (http://127.0.0.1:8765)"
    )
    parser.add_argument(
        "--slide",
        action="store_true",
        help="Chạy ngay công cụ CMCU-Vạn-Năng V3.2 FIX trên bài giảng đang mở"
    )
    parser.add_argument(
        "--solve",
        action="store_true",
        help="Giải ngay bài tập đang mở trên màn hình bằng AI Coding CLI"
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "antigravity", "codex", "claude", "opencode"],
        default=None,
        help="Chọn công cụ AI Coding CLI (mặc định: auto)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Tên model AI sử dụng (VD: gemini-3.8-flash-low, gemini-4-argon-medium, gpt-6-luna)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    atexit.register(cleanup_chrome_cache_safe, CHROME_PROFILE_DIR)
    console.clear()
    banner = """
    +--------------------------------------------------------------------------+
    |             EDUX ULTIMATE LIFEFORM (EUL) v0.6 - CMCU LMS AUTONOMOUS            |
    |       AI Coding CLI (Antigravity & Codex) - Không cần Gemini API Key     |
    |           Slide Engine: CMCU-Vạn-Năng V3.2 FIX (3/3 End Confirm)         |
    +--------------------------------------------------------------------------+
    """
    console.print(Panel(Text(banner, style="bold cyan"), border_style="cyan"))

    # Khởi tạo bộ nhớ cache câu hỏi
    cache = QuestionCache()

    # Khởi tạo AI Coding Solver (Kết nối trực tiếp Antigravity `agy` & OpenAI `codex`, không cần API Key!)
    try:
        solver = AICodingSolver(
            provider=args.provider or AI_PROVIDER,
            model=args.model or AI_MODEL,
            effort=AI_EFFORT,
            cache=cache
        )
        console.print(f"[bold green][OK] Đã kết nối Công cụ AI Coding: {solver.get_status_summary()}[/bold green]")
    except Exception as e:
        console.print(f"[bold red][X] Không thể khởi tạo AI Coding Solver: {e}[/bold red]")
        sys.exit(1)

    # Khởi động trình duyệt Google Chrome / Chromium thật
    ensure_chrome_running()

    with sync_playwright() as p:
        console.print("[cyan][+] Đang kết nối Playwright tới trình duyệt qua CDP (Port 9222)...[/cyan]")
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as cdp_err:
            console.print(f"[bold red][X] Lỗi kết nối CDP (Port 9222): {cdp_err}[/bold red]")
            sys.exit(1)

        context = browser.contexts[0]

        # Tự động dọn dẹp các tab rác nếu có từ phiên cũ
        for pg in list(context.pages):
            try:
                u = (pg.url or "").lower()
                if any(j in u for j in ["xn--", "http://tool", "http://của", "http://phúc", "http://hợp", "http://ultimate", "http://lifeform"]):
                    pg.close()
            except Exception:
                pass

        page = None
        for pg in context.pages:
            if "edux.cmcu.edu.vn" in pg.url:
                page = pg
                break

        if not page:
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
        else:
            try:
                page.bring_to_front()
            except Exception:
                pass

        console.print("[cyan][*] Đang kiểm tra trạng thái đăng nhập trên trình duyệt...[/cyan]")
        printed_prompt = False

        while True:
            curr_url = page.url.lower()
            is_login = "/login" in curr_url or "/auth" in curr_url

            has_student_ui = False
            try:
                page_text = page.evaluate("() => document.body ? document.body.innerText : ''")
                if "học phần" in page_text.lower() or "sinh viên" in page_text.lower() or "lớp học phần" in page_text.lower():
                    has_student_ui = True
            except Exception:
                pass

            if not is_login and ("/student" in curr_url or "/subject" in curr_url or has_student_ui):
                console.print("[bold green][OK] Đã nhận diện phiên đăng nhập thành công![/bold green]")
                break

            if not printed_prompt:
                console.print(Panel(
                    "[bold yellow][!] PHÁT HIỆN BẠN CHƯA ĐĂNG NHẬP![/bold yellow]\n\n"
                    "1. Cửa sổ trình duyệt đã được mở sẵn.\n"
                    "2. Vui lòng đăng nhập tài khoản trường CMCU trên cửa sổ đó.\n"
                    "3. [bold green]Hệ thống sẽ TỰ ĐỘNG nhận diện ngay khi bạn đăng nhập xong[/bold green].",
                    title="[ĐĂNG NHẬP] CHỜ ĐĂNG NHẬP",
                    border_style="yellow"
                ))
                printed_prompt = True

            page.wait_for_timeout(2000)

        subj_name = get_current_subject_name(page)
        automator = EduxAutomator(page=page, solver=solver, subject_name=subj_name)

        # =====================================================================
        # KHỞI ĐỘNG WEB DASHBOARD LOCALHOST (CHẠY SONG SONG)
        # =====================================================================
        web_port = 8765
        dashboard_url = f"http://127.0.0.1:{web_port}"
        try:
            start_web_server(port=web_port)
            console.print(Panel(
                f"[bold green]BẢNG ĐIỀU KHIỂN WEB DASHBOARD & CLI v0.6 ĐÃ SẴN SÀNG:[/bold green]\n"
                f"- Địa chỉ Web Dashboard: [bold cyan]{dashboard_url}[/bold cyan]\n"
                f"- AI Coding CLI: [bold magenta]{solver.get_status_summary()}[/bold magenta]\n"
                f"- Slide Engine: [bold yellow]CMCU-Vạn-Năng-V3.2 FIX (3/3 Confirm)[/bold yellow]",
                title="[EDUX ULTIMATE LIFEFORM (EUL) v0.6   ]",
                border_style="green"
            ))

            # Mở tab Web Dashboard nếu chưa mở và không chạy cờ --cli thuần
            if not args.cli and not args.slide and not args.solve:
                try:
                    has_dash = any(f"127.0.0.1:{web_port}" in (pg.url or "") for pg in context.pages)
                    if not has_dash:
                        dash_page = context.new_page()
                        dash_page.goto(dashboard_url, wait_until="domcontentloaded")
                        dash_page.bring_to_front()
                except Exception:
                    pass

        except Exception as web_err:
            console.print(f"[yellow][!] Không thể khởi động Web Server trên cổng {web_port}: {web_err}[/yellow]")

        # =====================================================================
        # XỬ LÝ CÁC CHẾ ĐỘ CHẠY TRỰC TIẾP QUA CLI FLAGS (--slide, --solve, --cli)
        # =====================================================================
        if args.slide:
            runner = SlideRunner(page=page, solver=solver)
            runner.run_current_slide_deck()
            return

        if args.solve:
            automator.chapter_name = "Bài tập trên màn hình"
            run_solver_workflow(automator, start_q=1, end_q=None, auto_submit=True)
            return

        if args.cli:
            main_menu(automator, cache, web_url=dashboard_url)
            return

        # =====================================================================
        # PLAYWRIGHT DISPATCH LOOP (WEB DASHBOARD + PHÍM TẮT MỞ CLI)
        # =====================================================================
        console.print(
            "[bold green][READY] Hệ thống đang lắng nghe Web Dashboard tại http://127.0.0.1:8765 ![/bold green]\n"
            "[dim]💡 Mẹo: Chạy `./run.sh --cli` hoặc `python main.py --cli` nếu bạn muốn dùng Menu CLI tương tác trực tiếp trên Terminal.[/dim]\n"
        )
        state.broadcast_log(f"[READY] Hệ thống sẵn sàng! AI CLI: {solver.get_status_summary()}")

        last_status_check = 0
        try:
            while True:
                now = time.time()
                if now - last_status_check >= 1.5:
                    last_status_check = now
                    try:
                        if not browser.is_connected():
                            state.chrome_connected = False
                            try:
                                browser = p.chromium.connect_over_cdp(CDP_URL)
                                context = browser.contexts[0]
                            except Exception:
                                pass

                        if browser.is_connected():
                            active_pg = get_active_edux_page(context, page)
                            if active_pg and not active_pg.is_closed():
                                page = active_pg
                                automator.page = page
                                new_subj = get_current_subject_name(page)
                                if new_subj and new_subj != "Mon hoc CMCU":
                                    state.subject_name = new_subj
                                    automator.subject_name = new_subj
                                elif not state.subject_name:
                                    state.subject_name = new_subj
                                state.chrome_connected = True
                                state.cache_count = cache.get_stats().get("total_questions", 0)
                            else:
                                state.chrome_connected = False
                        else:
                            state.chrome_connected = False
                    except Exception:
                        state.chrome_connected = False

                task = None
                try:
                    task = state.action_queue.get(timeout=0.15)
                except queue.Empty:
                    pass

                if not task:
                    continue

                action = task.get("action")
                state.stop_requested = False

                try:
                    if not browser.is_connected():
                        state.broadcast_log("[RECONNECT] Đang tự động kết nối lại trình duyệt...")
                        browser = p.chromium.connect_over_cdp(CDP_URL)
                        context = browser.contexts[0]
                except Exception as conn_err:
                    state.broadcast_log(f"[X] Không thể kết nối tới trình duyệt: {conn_err}")
                    state.is_running = False
                    continue

                active_pg = get_active_edux_page(context, page)
                if not active_pg or active_pg.is_closed():
                    state.broadcast_log("[+] Đang tự động mở/chuyển tới tab EduX...")
                    try:
                        active_pg = context.new_page()
                        active_pg.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
                    except Exception as pg_err:
                        state.broadcast_log(f"[X] Không thể điều hướng tới EduX: {pg_err}")
                        state.is_running = False
                        continue

                page = active_pg
                automator.page = page

                # 1. Giải bài tập đang mở
                if action == "solve_current":
                    state.is_running = True
                    state.task_start_time = time.time()
                    state.active_stage = 1
                    state.current_task = "Giải bài tập trên màn hình (AI CLI)"
                    state.broadcast_log(f"[START] Bắt đầu giải bài tập bằng {solver.get_status_summary()}...")
                    try:
                        has_dialog = False
                        try:
                            has_dialog = (
                                page.locator('div[role="dialog"][data-state="open"]').count() > 0 or
                                page.locator('div[role="dialog"]').count() > 0 or
                                "bài tập ai" in page.inner_text("body").lower()
                            )
                        except Exception:
                            pass

                        if not has_dialog and "/subject" in page.url:
                            state.broadcast_log("[!] Bạn đang ở trang môn học chứ chưa mở bài tập nào! Hãy bấm chọn bài trong Bảng danh sách chương bên dưới.")
                        else:
                            automator.chapter_name = "Bài tập trên màn hình"
                            run_solver_workflow(automator, start_q=1, end_q=None, auto_submit=True)
                            state.broadcast_log("[OK] Hoàn tất quá trình giải bài!")
                    except Exception as e:
                        state.broadcast_log(f"[X] Lỗi khi giải bài: {e}")
                    finally:
                        state.is_running = False
                        state.current_task = ""
                        state.active_stage = 0

                # 2. Chạy Slide học liệu liên hoàn (CMCU-Vạn-Năng V3.2 FIX + Auto-Next)
                elif action == "slide":
                    state.is_running = True
                    state.task_start_time = time.time()
                    state.active_stage = 1
                    state.current_task = "Chạy chuỗi Bài giảng AI (CMCU-Vạn-Năng V3.2 FIX)"
                    speed = task.get("speed", 0.25)
                    state.broadcast_log("[START] Kích hoạt CMCU-Vạn-Năng V3.2 FIX (Tự động chuyển Bài giảng AI tiếp theo cho đến hết môn)...")
                    try:
                        runner = SlideRunner(page=page, solver=solver, reading_delay=speed, context=context)
                        runner.run_current_slide_deck(auto_next_lesson=True)
                        if runner.page and not runner.page.is_closed():
                            page = runner.page
                            automator.page = page
                    except Exception as e:
                        state.broadcast_log(f"[X] Lỗi khi chạy slide: {e}")
                    finally:
                        state.is_running = False
                        state.current_task = ""
                        state.active_stage = 0

                # 3. Giải theo khoảng câu (X -> Y)
                elif action == "solve_range":
                    start_q = task.get("start_q", 1)
                    end_q = task.get("end_q", 20)
                    state.is_running = True
                    state.task_start_time = time.time()
                    state.active_stage = 1
                    state.current_task = f"Giải câu {start_q} đến {end_q}"
                    state.broadcast_log(f"[START] Bắt đầu giải từ câu {start_q} đến câu {end_q}...")
                    try:
                        automator.chapter_name = f"Câu {start_q} đến {end_q}"
                        run_solver_workflow(automator, start_q=start_q, end_q=end_q, auto_submit=False)
                        state.broadcast_log(f"[OK] Đã hoàn thành khoảng câu {start_q} đến {end_q}!")
                    except Exception as e:
                        state.broadcast_log(f"[X] Lỗi khi giải khoảng câu: {e}")
                    finally:
                        state.is_running = False
                        state.current_task = ""
                        state.active_stage = 0

                # 4. Giải theo URL
                elif action == "solve_url":
                    url = task.get("url", "").strip()
                    state.is_running = True
                    state.task_start_time = time.time()
                    state.active_stage = 1
                    state.current_task = "Giải bài theo URL"
                    state.broadcast_log(f"[NAVIGATE] Đang điều hướng tới {url}...")
                    try:
                        close_dialog_if_open(page)
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(2000)
                        automator.chapter_name = "Bài tập trực tiếp"
                        run_solver_workflow(automator, start_q=1, end_q=None, auto_submit=True)
                        state.broadcast_log("[OK] Đã hoàn thành giải bài theo URL!")
                    except Exception as e:
                        state.broadcast_log(f"[X] Lỗi khi giải theo URL: {e}")
                    finally:
                        state.is_running = False
                        state.current_task = ""
                        state.active_stage = 0

                # 5. Quét toàn bộ cấu trúc môn học
                elif action == "scan_course":
                    state.broadcast_log("[SCAN] Đang quét toàn bộ danh sách bài học trên trang...")
                    res_q = task.get("result_queue")
                    try:
                        rows = scan_course_full_structure(page)
                        state.broadcast_log(f"[SCAN] Đã quét thành công {len(rows)} mục bài học!")
                        if res_q:
                            res_q.put(rows)
                    except Exception as e:
                        state.broadcast_log(f"[X] Lỗi khi quét môn học: {e}")
                        if res_q:
                            res_q.put([])

                # 6. Giải bài chỉ định / Chạy slide chỉ định (và tự động nối tiếp các bài giảng sau đó)
                elif action == "solve_specific":
                    title = task.get("title", "")
                    target_type = task.get("target_type", "ai")
                    state.is_running = True
                    state.task_start_time = time.time()
                    state.active_stage = 1

                    type_label = "Slide (CMCU V3.2)" if target_type == "slide" else ("Bài tập AI" if target_type == "ai" else "Bài tập")
                    state.current_task = f"{type_label}: {title}"
                    state.broadcast_log(f"[START] Bắt đầu thực thi {type_label}: {title}...")

                    try:
                        close_dialog_if_open(page)
                        clean_title = title.split(' - ')[0].strip() if ' - ' in title else title.split(':')[0].strip()
                        card_loc = page.locator(f"div.bg-card:has-text('{title}'), div.bg-card:has-text('{clean_title}')").first

                        if not card_loc.is_visible(timeout=3000):
                            state.broadcast_log(f"[X] Không tìm thấy thẻ bài học trên màn hình: {title}")
                        else:
                            if target_type == "slide":
                                course_url_before = page.url if "/subject" in (page.url or "").lower() else None
                                btn = card_loc.locator("button:has-text('Bài giảng AI'), button:has-text('Bài giảng')").first
                                btn.evaluate("b => { b.scrollIntoView({ block: 'center' }); b.click(); }")
                                page.wait_for_timeout(2000)
                                active_pg = get_active_edux_page(context, page)
                                if active_pg:
                                    page = active_pg
                                    automator.page = page
                                state.broadcast_log(f"[SLIDE] Đã mở Slide của '{title}', kích hoạt CMCU-Vạn-Năng V3.2 FIX (Tự động chuyển bài tiếp theo)...")
                                runner = SlideRunner(page=page, solver=solver, context=context)
                                if course_url_before and not runner.is_currently_inside_slide_viewer():
                                    pass
                                runner.run_current_slide_deck(auto_next_lesson=True)
                                if runner.page and not runner.page.is_closed():
                                    page = runner.page
                                    automator.page = page
                            else:
                                if target_type == "ai":
                                    btn = card_loc.locator("button:has-text('Bài tập AI')").first
                                else:
                                    btn = card_loc.locator("button:text-is('Bài tập'), button.border-orange-500").first

                                btn.evaluate("b => { b.scrollIntoView({ block: 'center' }); b.click(); }")
                                page.wait_for_timeout(1200)

                                wait_and_start_quiz(automator)

                                automator.chapter_name = f"{title} ({target_type})"
                                run_solver_workflow(automator, start_q=1, end_q=None, auto_submit=True)
                                state.broadcast_log(f"[OK] Đã hoàn thành giải bài {title}!")
                    except Exception as e:
                        state.broadcast_log(f"[X] Lỗi khi thực thi bài {title}: {e}")
                    finally:
                        state.is_running = False
                        state.current_task = ""
                        state.active_stage = 0

                # 7. Cập nhật cấu hình AI Coding CLI
                elif action == "update_config":
                    new_provider = task.get("provider", solver.provider).strip().lower()
                    new_model = task.get("model", solver.active_model).strip()
                    new_effort = task.get("effort", solver.effort).strip().lower()

                    if hasattr(solver, "reconfigure"):
                        solver.reconfigure(new_provider, new_model, new_effort)
                    else:
                        solver.provider = new_provider
                        solver.active_model = new_model
                        solver.effort = new_effort
                    save_ai_cli_config(new_provider, new_model, new_effort)

                    state.ai_provider = new_provider
                    state.ai_model = new_model
                    state.ai_effort = new_effort
                    state.broadcast_log(f"[CONFIG] Đã lưu cấu hình AI CLI: {solver.get_status_summary()}")

                # 8. Xóa cache
                elif action == "clear_cache":
                    cache.clear()
                    state.cache_count = 0
                    state.broadcast_log("[CACHE] Đã xóa sạch toàn bộ ngân hàng câu hỏi!")

        except KeyboardInterrupt:
            console.print("\n[yellow]Người dùng đã dừng chương trình.[/yellow]")
        finally:
            try:
                browser.close()
            except Exception:
                pass
            cleanup_chrome_cache_safe(CHROME_PROFILE_DIR)


if __name__ == "__main__":
    main()
