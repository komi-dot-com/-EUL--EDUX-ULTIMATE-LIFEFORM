# EDUX ULTIMATE LIFEFORM (EUL) v0.7 — Core Solver

Thư mục lõi của công cụ tự động hóa **EduX CMCU** (`https://edux.cmcu.edu.vn`), hỗ trợ giải bài tập trắc nghiệm, đúng/sai (4 mệnh đề con), tự luận và chạy slide học liệu 100% Trợ giảng.

## ✨ Tính năng chính (v0.7)

- **Kết nối AI Coding CLI (Không cần API Key)**: Tự động dùng **Google Antigravity (`agy`)**, **OpenAI Codex (`codex`)**, **Claude Code (`claude`)** hoặc **OpenCode (`opencode`)**.
- **Tự động nhận diện model Antigravity mới**: Quét trực tiếp `agy models` để hỗ trợ **Gemini 4 Neon** (`gemini-4-neon-*`), **Gemini 4 Hydrogen** (`gemini-4-hydrogen-*`), **Gemini 4 Argon**, **Gemini 3.8 Flash**, **Claude Opus/Sonnet 5.5**, **GPT-OSS 120B**, **GPT-6 Luna**.
- **Hỗ trợ đề dài 25 / 50+ câu**: Tự động nhận diện tổng số câu kể cả khi thanh phân trang rút gọn, rà soát 2 lớp để không bỏ sót câu trước khi nộp.
- **Slide Engine CMCU-Vạn-Năng V3.2 FIX**: Tự mở câu hỏi *"Trả lời trên lớp"*, tự qua câu và xác nhận 3/3 nhịp ở trang cuối.
- **Giao diện kép**: Terminal CLI (`--cli`) và Web Dashboard tại `http://127.0.0.1:8765` (`--web`).

## 🚀 Khởi chạy nhanh

- **Linux**: `./run.sh` (hoặc `./run.sh --cli`, `./run.sh --web`, `./run.sh --slide`, `./run.sh --solve`)
- **Windows**: `run.bat` (dùng sẵn `python_embed` tích hợp)
- **macOS**: `run(dành cho macbook).command` hoặc `bash "run(dành cho macbook).sh"`

Xem hướng dẫn cài đặt từ gói đóng gói (`dist/`) và chi tiết các phím chức năng tại [README gốc](../README.md).
