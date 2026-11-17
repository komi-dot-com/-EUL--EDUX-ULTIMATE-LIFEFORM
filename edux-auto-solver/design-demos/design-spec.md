# EDUX ULTIMATE LIFEFORM v3.0 — UI Redesign Design Spec

## 1. Product & Domain Context
- **Product Name**: EDUX ULTIMATE LIFEFORM v3.0 (`CMCU LMS Autonomous Agent`)
- **Target Platform**: Local Web Control Center served at `http://127.0.0.1:8765` by Python `ThreadingHTTPServer` (`edux-auto-solver/src/web/server.py`), controlling a real Chrome session on CDP port `9222` logged into `https://edux.cmcu.edu.vn`.
- **Users & Scenario**: CMCU university students using the desktop browser (`50–70cm` viewing distance, `1440×900` primary desktop viewport, responsive down to `1024px` and `375px` mobile) to monitor and run automated slide progression (`CMCU-Vạn-Năng V3.2 FIX`) and AI-assisted exercise solving via local AI Coding CLIs (`agy` Antigravity, `codex`, `claude`, `opencode` — zero API key required).
- **UI Language**: 100% Vietnamese (natural, concise, technical-academic tone; NO `Lorem ipsum`, NO placeholder English headings, NO emojis in buttons/selects/headers).

## 2. Form Deduction (5 Questions)
1. **Narrative Role**: Desktop-grade Academic Automation Control Workbench. The primary screen must immediately communicate browser/subject connection, active execution status + 4-stage pipeline, curriculum action matrix, and live terminal/history without marketing fluff.
2. **Viewer Distance**: Desktop `50–70cm` (`1440×900`). Typography uses readable `13px–14px` body/table copy (`>=14px` main content, `>=12px` captions/badges), `tabular-nums` for every numeric cell/timer/score, and clear `4.5:1+` contrast.
3. **Visual Temperature**: Defined by the assigned Logic direction (must avoid generic `#060913` + neon indigo-purple-cyan gradients).
4. **Capacity Budget**:
   - Connection & Subject Header + Global Actions (`Settings`, `Cache`)
   - Live Mission Progress + 4-Stage Pipeline (`1. Quét đề bài`, `2. AI Coding CLI`, `3. Tích chọn DOM`, `4. Rà soát & Nộp bài`) + `Dừng tác vụ`
   - Quick Execution Toolbar (`Giải bài đang mở`, `Chạy Slide`, Slide Speed Picker, `Quét lại môn`, plus Range `Từ câu X`–`Đến câu Y` and Direct URL input)
   - Main Curriculum Table (`Gọn theo Chương` default 1 row/chapter vs `Chi tiết từng mục`, filter by `Tất cả` / `Bài tập AI` / `Bài tập` / `Slide`, Search field)
   - Dual Telemetry: `Lịch sử hoạt động & Điểm số` + `Live Terminal Stream` (SSE logs + auto-scroll toggle + clear)
   - Modals/Sheets: `Cấu hình AI Coding CLI` (`provider`, `model`, `effort`) & `Ngân hàng câu hỏi Cache`
5. **Visual Motif (Form from Content)**:
   - **The 4-Stage Autonomous Pipeline & Chapter Action Matrix**: Every chapter row pairs `% Trợ giảng` progress with up to 3 semantic actions (`Slide bài giảng`, `Bài tập AI`, `Bài tập`) and highest saved score, synchronized with the 4-stage execution sequencer.

## 3. Complete Backend API Contract (Must Wire Identically)
Every prototype must be a self-contained single `.html` file (`<style>` + semantic HTML + `<script>`) with ZERO external JS/CSS CDN dependencies (no `cdn.tailwindcss.com`, no `unpkg.com/lucide` — use clean inline SVGs inspired by SF Symbols!). Google Fonts `<link>` is allowed for Vietnamese-capable fonts (`Newsreader`, `IBM Plex Sans`, `Be Vietnam Pro`, `Bricolage Grotesque`, `JetBrains Mono`) alongside `-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display"`.

Must preserve and connect all endpoints:
- `GET /api/status`: polls every 1500ms:
  `chrome_connected`, `subject_name`, `is_running`, `current_task`, `task_detail`, `cache_count`, `progress_current`, `progress_total`, `progress_percent`, `step_label`, `active_stage` (0..4), `elapsed_sec`, `ai_provider`, `ai_model`, `available_tools`, `last_score`, `history`, `chapter_scores`.
- `GET /api/logs`: `EventSource('/api/logs')` streaming SSE lines with syntax color cues (`[OK]`, `[X]`/`[Lỗi]`/`ERROR`, `[AI]`, `[SLIDE]`/`[TURBO]`, `[START]`/`[RA SOÁT]`, `[KẾT QUẢ]`/`[RESULT]`, `[CONFIG]`, `[CACHE]`, `[SCAN]`, `[STOP]`, `[READY]`).
- `POST /api/action/solve_current`
- `POST /api/action/slide` (`{ speed: number }`)
- `POST /api/action/solve_range` (`{ start_q: number, end_q: number }`)
- `POST /api/action/solve_url` (`{ url: string }`)
- `POST /api/action/scan_course` -> returns array of `{ stt, week, title, percent_tg, percent_val, type, target_type ('ai'|'manual'|'slide'), target_title, status, highest_score, highest_score_val }`.
- `POST /api/action/solve_specific` (`{ title: string, target_type: 'ai'|'manual'|'slide' }`)
- `POST /api/action/stop`
- `POST /api/config` (`{ provider: 'auto'|'antigravity'|'codex'|'claude'|'opencode', model: string, effort: 'low'|'medium'|'high' }`)
- `DELETE /api/cache`

### Offline / `file://` Demo Fallback Data (Must Work Visually & Interactively Offline)
When `window.location.protocol === 'file:'` or `fetch` fails/times out in standalone preview, automatically load realistic CMCU data (no silent empty spinners!):
- `subject_name`: `"Công nghệ phần mềm - K4"`
- `chrome_connected`: `true`, `cache_count`: `148`, `ai_provider`: `"antigravity"`, `ai_model`: `"gemini-3.8-flash-low"`, `available_tools`: `["antigravity", "codex", "claude"]`
- `is_running`: `false` initially (with realistic interactive simulation when user clicks actions offline! E.g. clicking `Giải AI` or `Chạy Slide` locally simulates progress bar + 4-stage pipeline + SSE log entries so the prototype is genuinely clickable!)
- **Sample Course Rows (8 chapters covering realistic mix of Slide + AI + Manual)**:
  1. `Tuần 1` — `Chapter 1: Software Products` (`100%`, Slide + AI + Manual, score `9.45/10`)
  2. `Tuần 2` — `Chapter 2: Agile Software Engineering` (`100%`, Slide + AI, score `9.20/10`)
  3. `Tuần 3` — `Agile Software Engineering Features, Scenarios and Stories` (`100%`, Slide + AI + Manual, score `9.2/10`)
  4. `Tuần 4` — `Chapter 3: Requirements Engineering` (`80%`, Slide + AI + Manual, score `-`)
  5. `Tuần 5` — `Chapter 4: Software Architecture & Design` (`45%`, Slide + AI, score `-`)
  6. `Tuần 6` — `Chapter 5: Cloud & Microservices Patterns` (`0%`, Slide + AI + Manual, score `-`)
  7. `Tuần 7` — `Chapter 6: Software Testing & Verification` (`0%`, Slide + AI + Manual, score `-`)
  8. `Tuần 8` — `Tổng ôn & Đánh giá hệ thống Agile` (`0%`, AI + Manual, score `-`)
- **Sample History Rows** (from real `activity_history.json`):
  - `16:28:38` · `ai` · `Agile Software Engineering Features, Scenarios and Stories` · `Công nghệ phần mềm - K4 (25/25 câu)` · `9.2/10` · `Đã nộp bài`
  - `16:13:46` · `ai` · `Chapter 2: Agile Software Engineering` · `Công nghệ phần mềm - K4 (30/30 câu)` · `9.20/10` · `Đã nộp bài`
  - `15:54:15` · `ai` · `Chapter 1: Software Products` · `Công nghệ phần mềm - K4 (30/30 câu)` · `9.45/10` · `Đã nộp bài`
  - `18:07:15` · `slide` · `Pháp lý và Đạo đức nghề nghiệp - Slide` · `CMCU V3.2 FIX (35/35 trang)` · `100% Trợ giảng` · `Hoàn thành`
  - `18:02:42` · `manual` · `Bài tập trên màn hình` · `Công nghệ phần mềm - K4 (20/20 câu)` · `8.8/10` · `Đã nộp bài`

## 4. Mandatory Apple Design Guide (HIG) Compliance Checklist
Every direction MUST follow these Apple HIG rules for *Selection & Input* controls:
1. **Segmented Controls**:
   - Used for View Mode (`Theo Chương` | `Chi tiết`) and/or Type Filter (`Tất cả` | `Bài tập AI` | `Bài tập` | `Slide`) and/or Effort (`Low` | `Medium` | `High`).
   - Max ≤5–7 segments; **pure text only** inside each segmented control (never mix icons and text in the same segmented control!); Title-style noun phrases; balanced widths; consistent single-select state.
2. **Toggles & Checkboxes / Radio Buttons (macOS Body-Only Rule)**:
   - Switches (`role="switch"`, sliding knob + track with clear visual morphology beyond color alone) and Radio buttons (2–5 mutually exclusive choices, e.g., AI CLI Provider in Settings!) belong ONLY inside **window body / inspector / grouped form cards / modal sheets** — NEVER in window frame or toolbar.
   - Any toggle inside a toolbar (e.g., `Tự cuộn` or `Tùy chọn phụ`) MUST be styled as an Apple HIG **Toggle Button** (active tinted pill background + icon state change, NOT a raw checkbox or iOS Switch!).
3. **Pickers**:
   - Slide speed (`0.25s · Nhanh (3/3)`, `0.50s · Cân bằng`, `1.00s · Chậm chắc`) and Model selector (`gemini-3.8-flash-low`, `gemini-3.8-flash-medium`, `gemini-4-argon-low`, `gemini-4-argon-medium`, `claude-sonnet-5-5-low`, `gpt-6-luna`) use clean Apple Pop-up / Pull-down controls without emojis.
4. **Steppers + TextFields + Sliders**:
   - Numeric range (`Từ câu` / `Đến câu`) MUST use **TextField + Stepper (`-` / `+`)** (and optionally Slider for wide range) with permanent external visible labels (since placeholders disappear on typing!), `tabular-nums`, and immediate inline validation (`>= 1`, `start <= end`).
5. **Text Fields (Search & URL)**:
   - Search input has leading magnifying glass icon + trailing Clear (`✕`) button visible when non-empty.
   - Direct URL input (`https://edux.cmcu.edu.vn/...`) has a permanent external label, trailing Clear button, and subtle inline domain validation.
   - Logical Tab order across all inputs.
6. **macOS Liquid Glass Rule (if used)**:
   - Translucent / Liquid Glass material (`backdrop-filter: blur(...)`) is ONLY for the **floating navigation/toolbar/sidebar/sheet layer**, NEVER applied to the content table/rows themselves.
7. **Anti-AI-Slop Guardrails**:
   - ZERO emojis (`⚡`, `🚀`, `🧠`, `✨`, `✅`, `⚠️`) in UI chrome, buttons, badges, or `<option>` text.
   - ZERO `#060913` background or purple-indigo-cyan rainbow gradients.
   - ZERO `border-left: 4px solid` colored-stripe cards.
   - ZERO `Inter` / `Plus Jakarta Sans` + glowing shadow blur cards.
   - All numeric badges, scores, timers, percentages use `font-variant-numeric: tabular-nums`.
   - Minimum body/table font size `13px–14px`, caption/micro labels `>= 12px` (readable `4.5:1+` contrast).
