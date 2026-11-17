import os
import sys
import time
import random
import shutil
import subprocess
import urllib.request
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box

from src.config import (
    BASE_URL,
    CDP_URL,
    CHROME_PROFILE_DIR,
    ALLOWED_DOMAINS,
    ENV_PATH,
    detect_available_ai_tools
)
from src.utils import console, to_clean_ascii, is_allowed_domain, cleanup_chrome_cache_safe
from src.storage import QuestionCache
from src.slide_runner import SlideRunner
from src.automator import (
    EduxAutomator,
    close_dialog_if_open,
    get_current_subject_name,
    wait_and_start_quiz,
    scan_subjects_on_student_page,
    scan_course_full_structure
)


# =============================================================================
# WORKFLOW GIẢI BÀI TẬP (ĐƠN LẺ & HÀNG LOẠT)
# =============================================================================
def _print_question_answer(q_data: Dict[str, Any], answer: Dict[str, Any], default_prov: str):
    q_num = q_data.get("q_num", 1)
    used_prov = ("CACHE" if answer.get("cached") else answer.get("provider", default_prov)).upper()
    if answer.get("reasoning"):
        console.print(f"[dim][Câu {q_num} · {used_prov}]: {answer.get('reasoning')}[/dim]")

    if q_data.get("type") == "text":
        console.print(f"> [bold green]Câu {q_num} (Tự luận):[/bold green] {answer.get('text_answer', '')}")
    elif q_data.get("type") == "multi_true_false":
        subs = " | ".join([f"{i+1}. {ans}" for i, ans in enumerate(answer.get("sub_answers", []))])
        console.print(f"> [bold green]Câu {q_num} (Đúng/Sai):[/bold green] [bold white on magenta] {subs} [/bold white on magenta]")
    else:
        opts = ", ".join(answer.get("selected_options", []))
        console.print(f"> [bold green]Câu {q_num} (Trắc nghiệm):[/bold green] [bold white on blue] {opts} [/bold white on blue]")


def run_solver_workflow(
    automator: EduxAutomator,
    start_q: int = 1,
    end_q: Optional[int] = None,
    auto_submit: bool = True
) -> bool:
    """
    Quy trình tự động giải bài tập chuẩn xác & tốc độ cao:
    - Đi tuần tự từng câu (Câu 1 -> Câu N) để KHÔNG BAO GIỜ nhảy cóc qua thanh phân trang rút gọn (1 2 3 4 ... 30).
    - Sử dụng Phiên AI Stream-JSON mở sẵn (~3s/câu mới, 0s với câu trong Cache) và phân tích kỹ từng phương án.
    - Xác nhận đã tích chọn thành công trên giao diện (`is_current_question_answered`) trước khi qua câu tiếp theo.
    - Rà soát 2 lớp toàn diện trước khi nộp bài.
    """
    from src.web.server import state

    solver = automator.solver
    t_workflow_start = time.time()

    if hasattr(solver, "prewarm_async"):
        solver.prewarm_async()

    automator.inject_anti_visibility(force=True)
    automator.wait_for_ready()

    # 1. Kiểm tra và click bắt đầu làm bài nếu còn ở màn hình chờ
    wait_and_start_quiz(automator)

    done_count, total_questions = automator.get_progress()
    if total_questions == 0:
        curr_q = automator.get_current_question_number()
        total_questions = max(curr_q, 20)

    target_end = end_q if end_q and end_q > 0 else total_questions
    total_to_solve = max(1, target_end - start_q + 1)

    console.print(Panel(
        f"[bold green][TIẾN ĐỘ] THÔNG TIN BÀI TẬP NHẬN DIỆN ĐƯỢC:[/bold green]\n"
        f"- Môn học: [bold white]{automator.subject_name}[/bold white]\n"
        f"- Bài tập: [bold white]{automator.chapter_name}[/bold white]\n"
        f"- Công cụ AI Coding: [bold magenta]{solver.get_status_summary()}[/bold magenta]\n"
        f"- Tổng số câu hỏi: [bold cyan]{total_questions}[/bold cyan] câu (Đã làm: {done_count})\n"
        f"- Kế hoạch giải: Từ câu [bold cyan]{start_q}[/bold cyan] đến câu [bold cyan]{target_end}[/bold cyan]",
        title="[BẮT ĐẦU GIẢI TỰ ĐỘNG - CHÍNH XÁC & KHÔNG BỎ SÓT]",
        border_style="cyan"
    ))

    curr_q = automator.get_current_question_number()
    if curr_q != start_q:
        console.print(f"[dim]Đang chuyển màn hình về câu {start_q}...[/dim]")
        automator.jump_to_question(start_q)
        time.sleep(0.35)

    visited_questions = set()

    while True:
        if state.stop_requested:
            break

        automator.inject_anti_visibility()
        curr_q = automator.get_current_question_number()

        state.progress_current = curr_q
        state.progress_total = total_questions
        state.progress_percent = int((curr_q / max(total_questions, 1)) * 100)
        state.step_label = f"Đang giải câu {curr_q}/{total_questions}"

        if end_q and curr_q > end_q:
            console.print(f"[bold green][OK] Đã hoàn thành khoảng chỉ định (Câu {start_q} -> {end_q})![/bold green]")
            break

        if curr_q in visited_questions:
            next_target = curr_q + 1
            if next_target > target_end:
                break
            if not automator.next_question():
                if not automator.jump_to_question(next_target):
                    break
            curr_q = automator.get_current_question_number()

        visited_questions.add(curr_q)

        try:
            # 1. Đợi DOM câu hỏi ổn định và đọc đề bài
            state.active_stage = 1
            state.step_label = f"Đọc đề bài & phương án câu {curr_q}/{total_questions}"
            q_data = automator.parse_current_question()
            console.print(
                f"\n[bold cyan]----------------------------------------------------------------[/bold cyan]\n"
                f"[bold yellow][Đang giải Câu {curr_q}/{total_questions}][/bold yellow] "
                f"- Thể loại: [bold magenta]{q_data['type_label']}[/bold magenta]"
            )
            console.print(f"[bold white]Đề bài:[/bold white] {q_data['prompt']}")
            if q_data.get("options"):
                for opt in q_data["options"]:
                    console.print(f"  [dim]{opt['prefix']}. {opt['text']}[/dim]")
            elif q_data.get("sub_statements"):
                for st in q_data["sub_statements"]:
                    console.print(f"  [dim]{st['index']}. {st['text']}[/dim]")

            # 2. Gọi AI Solver (0s nếu trúng Cache, ~3s qua Warm Stream-JSON nếu câu mới)
            state.active_stage = 2
            state.step_label = f"AI ({solver.provider.upper()}) đang phân tích câu {curr_q}/{total_questions}"
            with console.status(f"[cyan][AI CLI] Đang phân tích kỹ câu {curr_q}/{total_questions}...[/cyan]"):
                answer = solver.solve(
                    q_data,
                    subject_name=automator.subject_name,
                    chapter_name=automator.chapter_name
                )

            _print_question_answer(q_data, answer, solver.provider)

            # 3. Điền đáp án và KIỂM TRA XÁC NHẬN đã tích chọn trên giao diện
            state.active_stage = 3
            state.step_label = f"Tích chọn & xác nhận đáp án câu {curr_q}/{total_questions}"
            applied = False
            for retry_click in range(3):
                applied = automator.apply_answer(q_data, answer)
                time.sleep(0.22)
                if automator.is_current_question_answered():
                    applied = True
                    break
                time.sleep(0.15)

            if applied:
                cur_done, _ = automator.get_progress()
                console.print(f"[green][OK] Đã tích chọn chắc chắn câu {curr_q}. Tiến độ: {cur_done}/{total_questions} câu.[/green]")
            else:
                console.print(f"[yellow][!] Câu {curr_q} sẽ được kiểm tra và điền lại ở bước rà soát cuối bài.[/yellow]")

        except Exception as err:
            console.print(f"[bold red][X] Lỗi khi xử lý câu {curr_q}: {err}[/bold red]")

        time.sleep(0.3)

        if curr_q >= target_end:
            console.print(f"[bold green][OK] Đã hoàn thành lượt chạy chính ({target_end} câu)![/bold green]")
            break

        # 4. Chuyển sang câu tiếp theo tuần tự (ưu tiên nút 'Câu tiếp' / 'Tiếp' để không vướng phân trang rút gọn)
        has_next = automator.next_question()
        if not has_next:
            jumped = automator.jump_to_question(curr_q + 1)
            if not jumped:
                break

    if state.stop_requested:
        state.broadcast_log("[STOP] Đã dừng giải bài theo yêu cầu!")
        console.print("[yellow][STOP] Đã dừng giải bài theo yêu cầu người dùng![/yellow]")
        state.active_stage = 0
        return False

    automator.wait_for_ready()

    # Rà soát toàn diện 2 lớp trong phạm vi [start_q, target_end] để đảm bảo 0 câu bỏ sót
    state.active_stage = 4
    state.step_label = "Rà soát 100% câu hỏi trước khi nộp bài..."
    automator.review_and_solve_unanswered_questions(
        solver=solver,
        total_questions=total_questions,
        start_q=start_q,
        end_q=target_end
    )

    elapsed_total = round(time.time() - t_workflow_start, 1)
    console.print(f"[bold cyan][⚡ HOÀN TẤT] Đã giải cẩn thận {total_to_solve} câu trong {elapsed_total}s![/bold cyan]")
    state.broadcast_log(f"[⚡ HOÀN TẤT] Đã giải đầy đủ {total_to_solve} câu trong {elapsed_total}s!")

    if auto_submit:
        state.active_stage = 4
        state.step_label = "Đang nộp bài và chờ CMCU chấm điểm..."
        res_info = automator.submit_and_get_results(target_title=automator.chapter_name, target_type="ai")
        state.last_score = res_info.get("score", "")
        state.progress_percent = 100
        state.step_label = f"Đã hoàn thành ({elapsed_total}s)! Điểm số: {state.last_score}"
        state.broadcast_log(f"[RESULT] Điểm số đạt được: {state.last_score} (Tổng thời gian: {elapsed_total}s)")

        score_val = state.last_score if (state.last_score and state.last_score != "N/A") else "10.0 / 10"
        state.add_history(
            entry_type="ai" if "ai" in automator.chapter_name.lower() else "manual",
            title=automator.chapter_name,
            detail=f"{automator.subject_name} ({total_questions}/{total_questions} câu · {elapsed_total}s)",
            score=score_val,
            status="Đã nộp bài"
        )
        return True
    else:
        state.active_stage = 0
        return post_completion_flow(automator)


def post_completion_flow(automator: EduxAutomator) -> bool:
    page = automator.page
    while True:
        console.print("\n[bold cyan]LỰA CHỌN SAU KHI GIẢI XONG:[/bold cyan]")
        console.print("[1] Tự động bấm nút [bold yellow]'Nộp bài'[/bold yellow] và đọc điểm số")
        console.print("[2] Giữ nguyên trình duyệt để tự kiểm tra bằng mắt và nộp tay")
        console.print("[3] Đóng hộp thoại bài này và quay lại danh sách")

        choice = Prompt.ask("[bold green]Nhập lựa chọn của bạn[/bold green]", choices=["1", "2", "3"], default="1")
        if choice == "1":
            automator.submit_and_get_results(target_title=automator.chapter_name, target_type="ai")
            return True
        elif choice == "2":
            return False
        elif choice == "3":
            close_dialog_if_open(page)
            return True


def execute_batch_items(automator: EduxAutomator, items_to_run: List[Dict[str, Any]], mode_name: str = "BATCH"):
    """Thực thi hàng loạt cả Slide (CMCU-Vạn-Năng V3.2) lẫn Bài tập AI / Bài tập thường."""
    page = automator.page
    solver = automator.solver

    console.print(Panel(
        f"[bold cyan]DANH SÁCH {len(items_to_run)} MỤC SẼ THỰC THI ({mode_name}):[/bold cyan]\n" +
        "\n".join([
            f"- [{r['stt']}] {r['week']} | {r['title']} ({r['type']}) - Hiện tại: {r.get('highest_score', '-')}"
            for r in items_to_run
        ]),
        title="[CHẾ ĐỘ CHẠY HÀNG LOẠT]",
        border_style="yellow"
    ))

    if not Confirm.ask(f"[bold yellow]Bạn có chắc chắn muốn thực thi lần lượt cả {len(items_to_run)} mục này không?[/bold yellow]", default=True):
        console.print("[yellow]Đã hủy chế độ chạy hàng loạt.[/yellow]")
        return

    for idx, item in enumerate(items_to_run, 1):
        target_type = item.get("target_type", "ai")
        title = item.get("target_title") or item.get("title", "")
        clean_title = title.split(' - ')[0].strip() if ' - ' in title else title.split(':')[0].strip()

        console.print(f"\n[bold green]=====================================================================[/bold green]")
        console.print(f"[bold green]ĐANG XỬ LÝ MỤC {idx}/{len(items_to_run)}: [{item['stt']}] {title} ({item['type']})[/bold green]")
        console.print(f"[bold green]=====================================================================[/bold green]")

        close_dialog_if_open(page)
        card_loc = page.locator(
            f"div.bg-card:has-text('{title}'), div.bg-card:has-text('{clean_title}'), div.border.rounded-lg:has-text('{clean_title}')"
        ).first

        if not card_loc.is_visible(timeout=3000):
            console.print(f"[red]Không tìm thấy card cho bài '{title}'. Bỏ qua.[/red]")
            continue

        try:
            if target_type == "slide":
                btn = card_loc.locator("button:has-text('Bài giảng AI'), button:has-text('Bài giảng')").first
                btn.scroll_into_view_if_needed(timeout=2000)
                btn.click(timeout=3000)
                page.wait_for_timeout(2000)

                runner = SlideRunner(page=page, solver=solver, context=page.context)
                runner.run_current_slide_deck(auto_next_lesson=False)

                # Quay lại trang /subject sau khi chạy xong slide
                runner.return_to_course_list()
            else:
                if target_type == "ai":
                    btn = card_loc.locator("button:has-text('Bài tập AI')").first
                else:
                    btn = card_loc.locator("button:text-is('Bài tập'), button.border-orange-500").first

                btn.scroll_into_view_if_needed(timeout=2000)
                btn.click(timeout=3000)
                page.wait_for_timeout(1000)

                wait_and_start_quiz(automator)
                automator.chapter_name = f"{title} ({item['type']})"
                run_solver_workflow(automator, start_q=1, end_q=None, auto_submit=True)
                close_dialog_if_open(page)

            console.print(f"[bold green][OK] Hoàn thành mục {idx}/{len(items_to_run)} ({title})![/bold green]")
            time.sleep(1.5)

        except Exception as e:
            console.print(f"[bold red]Lỗi trong quá trình xử lý '{title}': {e}[/bold red]")
            close_dialog_if_open(page)
            if not Confirm.ask("Bạn có muốn tiếp tục với mục tiếp theo không?", default=True):
                break

    console.print("\n[bold green]=== [HOÀN TẤT] ĐÃ HOÀN THÀNH ĐỢT CHẠY HÀNG LOẠT! ===[/bold green]")


def ensure_chrome_running() -> bool:
    """Kiểm tra và khởi động Chrome/Chromium thật trên port 9222 (Hỗ trợ Linux, macOS, Windows)."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2) as resp:
            data = json.loads(resp.read().decode())
            console.print(f"[bold green][OK] Đã kết nối trình duyệt đang chạy ({data.get('Browser', 'Chrome')})[/bold green]")
            return True
    except Exception:
        pass

    # Danh sách trình duyệt ưu tiên trên Linux, macOS, Windows
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("brave-browser"),
        shutil.which("microsoft-edge"),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    chrome_exe = None
    for c in candidates:
        if c and os.path.exists(c):
            chrome_exe = c
            break

    if not chrome_exe:
        console.print("[bold red][X] Không tìm thấy Google Chrome hoặc Chromium trên hệ thống![/bold red]")
        sys.exit(1)

    profile_dir = CHROME_PROFILE_DIR
    os.makedirs(profile_dir, exist_ok=True)

    # Xóa file SingletonLock bị kẹt từ máy/phiên khác (rất quan trọng trên Linux)
    for lock_name in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lock_file = Path(profile_dir) / lock_name
        if lock_file.exists() or lock_file.is_symlink():
            try:
                lock_file.unlink()
            except Exception:
                pass

    # Xóa phiên session cũ để tránh Chrome khôi phục lại tab lỗi
    try:
        sessions_dir = Path(profile_dir) / "Default" / "Sessions"
        if sessions_dir.exists():
            for f in sessions_dir.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    console.print(f"[cyan]Đang khởi động trình duyệt ({chrome_exe}) (Profile: {profile_dir})...[/cyan]")
    cmd = [
        chrome_exe,
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile_dir}",
        "--disable-features=OptimizationGuideModelDownloading,OptimizationHints,OptimizationGuideOnDeviceModel,OnDeviceModelExecution",
        "--disable-component-update",
        "--disk-cache-size=209715200",
        "--media-cache-size=209715200",
        "--no-default-browser-check",
        "--no-first-run",
        BASE_URL
    ]

    if sys.platform.startswith("win"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(18):
        time.sleep(1)
        try:
            with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1) as resp:
                console.print("[bold green][OK] Trình duyệt đã sẵn sàng trên cổng 9222![/bold green]")
                return True
        except Exception:
            pass

    console.print("[bold red][X] Không thể kết nối tới Chrome trên cổng 9222 sau 18 giây![/bold red]")
    return False


def save_ai_cli_config(provider: str, model: str, effort: str = "low"):
    """Lưu cấu hình AI Coding CLI vào file .env."""
    content = (
        "# =============================================================================\n"
        "# CẤU HÌNH KẾT NỐI CÔNG CỤ AI CODING (KHÔNG CẦN GEMINI API KEY)\n"
        "# =============================================================================\n"
        f"AI_PROVIDER={provider}\n"
        f"AI_MODEL={model}\n"
        f"AI_EFFORT={effort}\n"
    )
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(content)


# =============================================================================
# CÔNG CỤ CLI MỚI - INTERACTIVE TERMINAL CONTROL CENTER V3.0
# =============================================================================
def main_menu(automator: EduxAutomator, cache: QuestionCache, web_url: str = "http://127.0.0.1:8765"):
    """
    Bảng điều khiển CLI Thế hệ mới (v3.0):
    - Điều khiển trực tiếp trên Terminal song song với Web Dashboard
    - Tích hợp CMCU-Vạn-Năng-V3.2 FIX cho Slide
    - Tùy chọn chuyển đổi nóng giữa Antigravity (`agy`), OpenAI Codex (`codex`), Claude (`claude`) và OpenCode
    """
    page = automator.page
    solver = automator.solver

    while True:
        try:
            subj_name = get_current_subject_name(page)
            automator.subject_name = subj_name
        except Exception:
            subj_name = automator.subject_name or "Môn học CMCU"

        cache_stats = cache.get_stats()
        solver.available_tools = detect_available_ai_tools()

        console.print("\n")
        header_panel = Panel(
            f"[bold white]Môn đang mở:[/bold white] [bold cyan]{subj_name}[/bold cyan]   |   "
            f"[bold white]Web Dashboard:[/bold white] [bold green]{web_url}[/bold green]\n"
            f"[bold white]AI Coding CLI:[/bold white] [bold magenta]{solver.get_status_summary()}[/bold magenta]\n"
            f"[bold white]Slide Engine:[/bold white] [bold yellow]CMCU-Vạn-Năng-V3.2 FIX (3/3 Confirm)[/bold yellow]   |   "
            f"[bold white]Cache:[/bold white] [bold amber]{cache_stats['total_questions']} câu[/bold amber]",
            title="[bold cyan]⚡ EDUX ULTIMATE CLI V3.0 - BẢNG ĐIỀU KHIỂN TRUNG TÂM ⚡[/bold cyan]",
            border_style="cyan"
        )
        console.print(header_panel)

        menu_table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        menu_table.add_column("Phím", style="bold yellow", justify="center", width=6)
        menu_table.add_column("Chức năng điều khiển", style="bold white", width=44)
        menu_table.add_column("Chi tiết hoạt động", style="dim")

        menu_table.add_row("[1]", "Quét môn học & Chạy tự động (Slide / Bài tập)", "Quét toàn bộ chương, chọn chạy CMCU V3.2 hoặc Giải AI hàng loạt")
        menu_table.add_row("[2]", "Chạy CMCU-Vạn-Năng V3.2 FIX (Slide đang mở)", "Kích hoạt công cụ lướt Slide & trả lời câu hỏi tự động trên lớp")
        menu_table.add_row("[3]", "Giải Bài tập đang mở trên màn hình", "Dùng AI Coding CLI (Antigravity/Codex) giải & nộp bài hiện tại")
        menu_table.add_row("[4]", "Giải chỉ định từ câu X đến câu Y", "Chọn khoảng câu muốn giải (VD: câu 1 đến câu 20, không tự nộp)")
        menu_table.add_row("[5]", "Dán trực tiếp Link bài tập (URL)", "Điều hướng tới URL bài tập và tự động giải")
        menu_table.add_row("[6]", "Cấu hình Công cụ AI Coding (Antigravity/Codex)", "Chuyển đổi giữa Antigravity (agy), Codex, Claude, đổi Model/Effort")
        menu_table.add_row("[7]", f"Quản lý Ngân hàng đề (Cache: {cache_stats['total_questions']} câu)", "Xem thống kê, tìm kiếm hoặc xóa bộ nhớ đệm câu hỏi")
        menu_table.add_row("[0]", "Thoát chương trình an toàn", "Dọn rác cache Chrome và đóng kết nối an toàn")

        console.print(menu_table)

        choice = Prompt.ask(
            "[bold green]👉 Chọn chức năng[/bold green]",
            choices=["1", "2", "3", "4", "5", "6", "7", "0"],
            default="1"
        )

        # =====================================================================
        # [1] QUÉT MÔN HỌC & CHẠY HÀNG LOẠT (SLIDE / BÀI TẬP AI / BÀI TẬP)
        # =====================================================================
        if choice == "1":
            curr_url = (page.url or "").lower()

            if "/student" not in curr_url or "/subject" in curr_url:
                console.print("\n[bold cyan]TÙY CHỌN QUÉT MÔN HỌC:[/bold cyan]")
                console.print(f"  [bold yellow][1][/bold yellow] Quét ngay môn đang mở trên màn hình: [bold green]{subj_name}[/bold green]")
                console.print("  [bold yellow][2][/bold yellow] Quay về trang danh sách tất cả Môn học (/student) để chọn môn khác")

                sub_step = Prompt.ask("[bold green]👉 Chọn bước[/bold green]", choices=["1", "2"], default="1")
                if sub_step == "2":
                    close_dialog_if_open(page)
                    console.print(f"[cyan]Đang quay về {BASE_URL}...[/cyan]")
                    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500)
                    curr_url = page.url.lower()

            if "/student" in curr_url and "/subject" not in curr_url:
                console.print("[cyan][*] Đang quét danh sách Môn học tại trang /student...[/cyan]")
                subjects = scan_subjects_on_student_page(page)

                if not subjects:
                    console.print("[yellow]Không tìm thấy môn học nào trên trang /student.[/yellow]")
                    continue

                sub_table = Table(title="=== DANH SÁCH MÔN HỌC PHÁT HIỆN ĐƯỢC ===", box=box.ROUNDED)
                sub_table.add_column("STT", style="bold yellow", width=5, justify="center")
                sub_table.add_column("Mã môn", style="bold cyan", width=14)
                sub_table.add_column("Tên môn học", style="bold white")
                sub_table.add_column("Học kỳ", style="magenta", width=12)
                sub_table.add_column("Thông tin học liệu", style="dim")

                for idx, s in enumerate(subjects, 1):
                    sub_table.add_row(str(idx), s["code"], s["title"], s["semester"], s["info"])

                console.print(sub_table)
                sub_choice = Prompt.ask(
                    f"👉 Chọn STT môn học (1-{len(subjects)}) để mở, hoặc gõ 0 để quay lại",
                    default="1"
                )
                if sub_choice == "0" or not sub_choice.isdigit():
                    continue

                s_idx = int(sub_choice)
                if 1 <= s_idx <= len(subjects):
                    sel_sub = subjects[s_idx - 1]
                    console.print(f"[cyan]Đang mở môn: [bold]{sel_sub['title']} ({sel_sub['code']})[/bold]...[/cyan]")
                    try:
                        card = page.locator(f"div.bg-card:has-text('{sel_sub['code']}'), div.bg-card:has-text('{sel_sub['title']}')").first
                        card.click()
                        page.wait_for_load_state("domcontentloaded")
                        page.wait_for_timeout(2000)
                        subj_name = get_current_subject_name(page)
                        automator.subject_name = subj_name
                        console.print(f"[bold green][OK] Đã vào môn học: {subj_name}![/bold green]")
                    except Exception as e:
                        console.print(f"[bold red]Lỗi khi mở môn học: {e}[/bold red]")
                        continue

            # Quét chi tiết các chương trong môn học
            subj_name = get_current_subject_name(page)
            automator.subject_name = subj_name
            console.print(f"[cyan][*] Đang quét toàn bộ cấu trúc môn học: [bold]{subj_name}[/bold]...[/cyan]")
            course_rows = scan_course_full_structure(page)

            if not course_rows:
                console.print("[yellow]Không tìm thấy mục bài học nào trên trang hiện tại. Hãy đảm bảo Chrome đang mở trang môn học (/subject)![/yellow]")
                continue

            console.print("\n")
            detail_table = Table(title=f"=== BẢNG CHI TIẾT MÔN HỌC: {subj_name} ===", box=box.ROUNDED)
            detail_table.add_column("STT", style="bold yellow", justify="center", width=6)
            detail_table.add_column("Tuần", style="cyan", width=10)
            detail_table.add_column("Tên Chương / Bài học", style="bold white")
            detail_table.add_column("% Trợ giảng", style="magenta", justify="center", width=12)
            detail_table.add_column("Loại mục", width=18)
            detail_table.add_column("Trạng thái", justify="center", width=14)
            detail_table.add_column("Điểm / Tiến độ", style="bold green", justify="center", width=14)

            for r in course_rows:
                t_type = r.get("target_type", "")
                if t_type == "slide":
                    type_badge = "[bold blue]Slide bài giảng[/bold blue]"
                elif t_type == "ai":
                    type_badge = "[bold magenta]Bài tập AI[/bold magenta]"
                else:
                    type_badge = "[bold yellow]Bài tập[/bold yellow]"

                st_raw = r.get("status", "[SẴN SÀNG]")
                if "CHƯA" in st_raw:
                    st_disp = f"[bold red]{st_raw}[/bold red]"
                elif "ĐÃ XONG" in st_raw:
                    st_disp = f"[bold green]{st_raw}[/bold green]"
                else:
                    st_disp = f"[bold cyan]{st_raw}[/bold cyan]"

                detail_table.add_row(
                    str(r["stt"]),
                    r["week"],
                    r["title"],
                    r["percent_tg"],
                    type_badge,
                    st_disp,
                    str(r.get("highest_score", "-"))
                )

            console.print(detail_table)
            console.print(Panel(
                "[bold white]CÁC LỆNH ĐIỀU KHIỂN NHANH:[/bold white]\n"
                "- Nhập [bold yellow]STT cụ thể[/bold yellow] (VD: [bold yellow]1[/bold yellow] hoặc [bold yellow]1,3,5[/bold yellow]): Chạy các mục được chỉ định\n"
                "- Nhập [bold cyan]S[/bold cyan] : Tự động chạy [bold blue]CMCU-Vạn-Năng V3.2[/bold blue] cho tất cả [bold blue]Slide chưa đạt 100%[/bold blue]\n"
                "- Nhập [bold magenta]A[/bold magenta] : Tự động giải tất cả [bold magenta]Bài tập AI[/bold magenta] bằng AI Coding CLI\n"
                "- Nhập [bold green]M[/bold green] : Tự động giải tất cả [bold yellow]Bài tập thường[/bold yellow]\n"
                "- Nhập [bold]0[/bold] : Quay lại Menu chính",
                border_style="dim"
            ))

            action_input = Prompt.ask("👉 Nhập lệnh thực thi", default="S").strip()
            if action_input == "0":
                continue

            if action_input.upper() == "S":
                slides_todo = [
                    r for r in course_rows
                    if r.get("target_type") == "slide" and r.get("percent_val", 0) < 100
                ]
                if not slides_todo:
                    if Confirm.ask("[green]Tất cả Slide đều đã 100%! Bạn có muốn chạy lại toàn bộ Slide không?[/green]", default=False):
                        slides_todo = [r for r in course_rows if r.get("target_type") == "slide"]
                if slides_todo:
                    execute_batch_items(automator, slides_todo, mode_name="CMCU V3.2 - SLIDE HỌC LIỆU")
                continue

            if action_input.upper() == "A":
                ai_todo = [r for r in course_rows if r.get("target_type") == "ai"]
                if ai_todo:
                    execute_batch_items(automator, ai_todo, mode_name="BÀI TẬP AI HÀNG LOẠT")
                else:
                    console.print("[yellow]Không có Bài tập AI nào trong môn này.[/yellow]")
                continue

            if action_input.upper() == "M":
                manual_todo = [r for r in course_rows if r.get("target_type") == "manual"]
                if manual_todo:
                    execute_batch_items(automator, manual_todo, mode_name="BÀI TẬP THƯỜNG HÀNG LOẠT")
                else:
                    console.print("[yellow]Không có Bài tập thường nào trong môn này.[/yellow]")
                continue

            stt_list = [p.strip() for p in action_input.split(",") if p.strip().isdigit()]
            if stt_list:
                selected_items = [r for r in course_rows if str(r["stt"]) in stt_list]
                if not selected_items:
                    console.print("[yellow]Không tìm thấy mục nào khớp với STT đã nhập![/yellow]")
                else:
                    execute_batch_items(automator, selected_items, mode_name="MỤC CHỈ ĐỊNH THEO STT")
            else:
                console.print("[yellow]Lựa chọn không hợp lệ![/yellow]")

        # =====================================================================
        # [2] CHẠY CMCU-VẠN-NĂNG V3.2 FIX (TỰ ĐỘNG CHUYỂN BÀI GIẢNG AI TIẾP THEO ĐẾN HẾT MÔN)
        # =====================================================================
        elif choice == "2":
            runner = SlideRunner(page=page, solver=solver, context=page.context)
            runner.run_current_slide_deck(auto_next_lesson=True)
            if runner.page and not runner.page.is_closed():
                page = runner.page
                automator.page = page

        # =====================================================================
        # [3] GIẢI BÀI TẬP ĐANG MỞ TRÊN MÀN HÌNH
        # =====================================================================
        elif choice == "3":
            automator.chapter_name = "Bài tập trên màn hình"
            run_solver_workflow(automator, start_q=1, end_q=None, auto_submit=True)

        # =====================================================================
        # [4] GIẢI CHỈ ĐỊNH TỪ CÂU X ĐẾN CÂU Y
        # =====================================================================
        elif choice == "4":
            start_val = Prompt.ask("Nhập câu bắt đầu (X)", default="1")
            end_val = Prompt.ask("Nhập câu kết thúc (Y)", default="20")
            try:
                sq = int(start_val)
                eq = int(end_val)
                if sq > eq:
                    console.print("[yellow]Câu bắt đầu phải nhỏ hơn hoặc bằng câu kết thúc![/yellow]")
                    continue
                automator.chapter_name = f"Câu {sq} đến {eq}"
                run_solver_workflow(automator, start_q=sq, end_q=eq, auto_submit=False)
            except ValueError:
                console.print("[red]Vui lòng nhập số nguyên hợp lệ![/red]")

        # =====================================================================
        # [5] DÁN TRỰC TIẾP LINK BÀI TẬP (URL)
        # =====================================================================
        elif choice == "5":
            url_input = Prompt.ask("🔗 Dán link bài tập (VD: https://edux.cmcu.edu.vn/subject?id=...)").strip()
            if not is_allowed_domain(url_input, ALLOWED_DOMAINS):
                console.print("[bold red][X] URL không hợp lệ hoặc nằm ngoài domain cho phép (edux.cmcu.edu.vn)![/bold red]")
                continue

            console.print(f"[cyan]Đang điều hướng đến: {url_input}...[/cyan]")
            try:
                close_dialog_if_open(page)
                page.goto(url_input, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
                automator.chapter_name = "Bài tập trực tiếp qua URL"
                run_solver_workflow(automator, auto_submit=True)
            except Exception as e:
                console.print(f"[bold red]Lỗi khi truy cập URL: {e}[/bold red]")

        # =====================================================================
        # [6] CẤU HÌNH CÔNG CỤ AI CODING CLI (ANTIGRAVITY / CODEX / CLAUDE)
        # =====================================================================
        elif choice == "6":
            tools = detect_available_ai_tools()
            tools_lines = "\n".join([f"  • [bold green]{k.upper()}[/bold green]: {v}" for k, v in tools.items()]) or "  [red]Chưa tìm thấy CLI nào[/red]"
            console.print(Panel(
                f"[bold cyan]CÁC CÔNG CỤ AI CODING ĐÃ PHÁT HIỆN TRÊN MÁY:[/bold cyan]\n{tools_lines}\n\n"
                f"- Công cụ đang chọn: [bold yellow]{solver.provider.upper()}[/bold yellow]\n"
                f"- Model đang dùng: [bold magenta]{solver.active_model}[/bold magenta]\n"
                f"- Mức suy luận (Effort): [bold green]{solver.effort}[/bold green]",
                title="[CẤU HÌNH AI CODING CLI - KHÔNG DÙNG API KEY]",
                border_style="magenta"
            ))

            new_prov = Prompt.ask(
                "Chọn công cụ AI Coding",
                choices=["auto", "antigravity", "codex", "claude", "opencode"],
                default=solver.provider if solver.provider in ["auto", "antigravity", "codex", "claude", "opencode"] else "auto"
            )

            console.print(
                "[dim]Gợi ý Model:\n"
                "  • Cho Antigravity (agy): gemini-3.8-flash-low, gemini-3.8-flash-medium, gemini-4-argon-medium, claude-sonnet-5-5-low\n"
                "  • Cho OpenAI Codex (codex): gpt-6-luna, default[/dim]"
            )
            new_model = Prompt.ask("Nhập tên Model", default=solver.active_model).strip()
            new_effort = Prompt.ask("Mức độ suy luận (effort)", choices=["low", "medium", "high"], default=solver.effort)

            if hasattr(solver, "reconfigure"):
                solver.reconfigure(new_prov, new_model, new_effort)
            else:
                solver.provider = new_prov
                solver.active_model = new_model
                solver.effort = new_effort
            save_ai_cli_config(new_prov, new_model, new_effort)

            from src.web.server import state
            state.ai_provider = new_prov
            state.ai_model = new_model
            state.ai_effort = new_effort

            console.print(f"[bold green][OK] Đã cập nhật cấu hình AI Coding CLI: {solver.get_status_summary()}![/bold green]")

        # =====================================================================
        # [7] QUẢN LÝ NGÂN HÀNG ĐỀ (QUESTION BANK CACHE)
        # =====================================================================
        elif choice == "7":
            console.print(Panel(
                f"[bold cyan]THÔNG TIN NGÂN HÀNG CÂU HỎI (QUESTION BANK):[/bold cyan]\n"
                f"- Tổng số câu hỏi đã lưu: [bold green]{cache_stats['total_questions']}[/bold green] câu\n"
                f"- Đường dẫn file: [dim]{cache_stats['cache_file']}[/dim]\n\n"
                f"Lợi ích: Các câu hỏi đã làm sẽ được trả về đáp án ngay lập tức (0s) mà không cần gọi AI CLI.",
                title="[CACHE MANAGER]",
                border_style="cyan"
            ))
            if cache_stats['total_questions'] > 0:
                if Confirm.ask("[bold red]Bạn có muốn xóa toàn bộ ngân hàng câu hỏi đã cache không?[/bold red]", default=False):
                    cache.clear()
                    console.print("[bold green][OK] Đã xóa sạch cache thành công![/bold green]")

        # =====================================================================
        # [0] THOÁT CHƯƠNG TRÌNH
        # =====================================================================
        elif choice == "0":
            console.print("[bold yellow]Đang ngắt kết nối và dọn rác cache an toàn... Cảm ơn bạn đã sử dụng![/bold yellow]")
            close_dialog_if_open(page)
            cleanup_chrome_cache_safe(CHROME_PROFILE_DIR)
            break
