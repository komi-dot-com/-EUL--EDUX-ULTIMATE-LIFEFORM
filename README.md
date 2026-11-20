# EDUX ULTIMATE LIFEFORM (EUL) v0.7 — CMCU LMS

Hệ thống tự động hóa hỗ trợ giải bài tập trắc nghiệm, đúng/sai (4 mệnh đề con), tự luận và **chạy slide học liệu (100% Trợ giảng)** trên hệ thống EduX CMCU (`https://edux.cmcu.edu.vn`).

## ✨ Điểm mới ở phiên bản v0.7

1. **Không cần API Key**: Kết nối trực tiếp qua AI Coding CLI cài sẵn trên máy (**Google Antigravity `agy`**, **OpenAI Codex `codex`**, **Claude Code `claude`**, **OpenCode `opencode`**).
2. **Tự động nhận diện mô hình Antigravity mới**: Tự động quét danh sách model trực tiếp từ `agy models`, hỗ trợ đầy đủ **Gemini 4 Neon** (`gemini-4-neon-low/medium/high/xhigh`), **Gemini 4 Hydrogen** (`gemini-4-hydrogen-low/medium/high/xhigh`), **Gemini 4 Argon**, **Gemini 3.8 Flash**, **Claude Opus/Sonnet 5.5**, **GPT-OSS 120B**, **GPT-6 Luna**.
3. **Nhận diện chuẩn xác đề 25 / 50+ câu**: Cải thiện bộ đếm tiến độ và điều hướng tuần tự khi thanh phân trang bị rút gọn, tự động theo dõi số câu thực tế và rà soát 2 lớp trước khi nộp bài.
4. **Slide Engine CMCU-Vạn-Năng V3.2 FIX**: Tự động mở câu hỏi *"Trả lời trên lớp"*, dò Hint/Blacklist, tự qua câu và xác nhận 3/3 nhịp liên tiếp ở trang cuối để tránh dừng sớm.
5. **Đóng gói sẵn bộ cài cho Linux, Windows & macOS**: Có sẵn trong thư mục `dist/` (hoặc tự build lại bằng `./build_packages.sh`).

---

## 📦 Cài đặt từ gói đóng gói (`dist/`)

- **Linux (mọi distro — Fedora, Ubuntu, Arch...)**:
  ```bash
  chmod +x dist/edux-auto-solver-linux-installer.run
  ./dist/edux-auto-solver-linux-installer.run
  ```
  Sau khi cài, chạy lệnh `edux-solver` hoặc mở **Edux Auto-Solver** trong menu ứng dụng.
- **Fedora / RHEL (`.rpm`)**:
  ```bash
  sudo dnf install ./dist/edux-auto-solver-0.7.0-1.fc45.noarch.rpm
  ```
- **Ubuntu / Debian (`.deb`)**:
  ```bash
  sudo apt install ./dist/edux-auto-solver_0.7.0_all.deb
  ```
- **Windows (`.zip` kèm sẵn `python_embed`)**:
  Giải nén `dist/edux-auto-solver-windows.zip` và chạy `install_windows.bat` để cài đặt và tạo shortcut **Edux Auto-Solver** ngoài Desktop (hoặc chạy trực tiếp `run.bat`).
- **macOS (`.zip` kèm `.app` bundle)**:
  Giải nén `dist/edux-auto-solver-macos.zip` và chạy `Install_macOS.command` để cài **Edux Auto-Solver.app** vào thư mục `Applications`.

> Muốn tự đóng gói lại toàn bộ các file cài đặt sau khi sửa code, chạy: `./build_packages.sh`

---

## 🚀 Chạy trực tiếp từ mã nguồn

- **Linux**:
  ```bash
  ./run.sh
  ```
- **Windows**: Mở `run.bat` (hoặc `edux-auto-solver/run.bat`).
- **macOS**: Mở `edux-auto-solver/run(dành cho macbook).command` (hoặc chạy `bash "edux-auto-solver/run(dành cho macbook).sh"`).

### Các cờ chạy nhanh (CLI v0.7)
- Mở trực tiếp **Bảng điều khiển CLI** trên Terminal:
  ```bash
  ./run.sh --cli
  ```
- Mở **Web Dashboard** tại `http://127.0.0.1:8765`:
  ```bash
  ./run.sh --web
  ```
- Kích hoạt **CMCU-Vạn-Năng V3.2 FIX** cho bài giảng đang mở trên Chrome:
  ```bash
  ./run.sh --slide
  ```
- Giải ngay **Bài tập đang mở** bằng AI Coding CLI tùy chọn model:
  ```bash
  ./run.sh --solve --provider antigravity --model gemini-4-neon-medium
  ```

---

## 🎯 Các chức năng trong Menu CLI (v0.7)

- **`[1]` Quét môn học & Chạy tự động (Slide / Bài tập)**:
  - Quét toàn bộ Chương, % Trợ giảng, Slide, Bài tập AI, Bài tập thường.
  - Gõ **`S`**: Chạy **CMCU-Vạn-Năng V3.2 FIX** cho toàn bộ Slide chưa đạt 100%.
  - Gõ **`A`**: Giải hàng loạt tất cả **Bài tập AI**.
  - Gõ **`M`**: Giải hàng loạt tất cả **Bài tập thường**.
  - Gõ **STT** (VD: `1` hoặc `1,3,5`): Chạy các mục được chỉ định.
- **`[2]` Chạy CMCU-Vạn-Năng V3.2 FIX (Slide đang mở)**: Tự động hoàn thành 100% slide bài giảng đang mở.
- **`[3]` Giải Bài tập đang mở trên màn hình**: Tự động đọc đề, giải, rà soát 100% câu hỏi và nộp bài.
- **`[4]` Giải chỉ định từ câu X đến câu Y**: Giải một khoảng câu tùy chọn (không tự nộp bài).
- **`[5]` Dán trực tiếp Link bài tập (URL)**: Mở thẳng link bài tập và giải ngay.
- **`[6]` Cấu hình Công cụ AI Coding**: Chuyển đổi giữa `auto`, `antigravity` (`agy`), `codex`, `claude`, `opencode`, chọn model (tự động gợi ý các model mới quét từ `agy models`) và mức `effort` (`low` / `medium` / `high`).
- **`[7]` Quản lý Ngân hàng đề (Question Bank Cache)**: Xem thống kê, tìm kiếm hoặc xóa bộ nhớ đệm câu hỏi.
