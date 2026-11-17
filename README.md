# EDUX ULTIMATE LIFEFORM v3.0 - CMCU LMS (AI CODING CLI & CMCU-VẠN-NĂNG V3.2 FIX)

Hệ thống tự động hóa thông minh hỗ trợ giải bài tập trắc nghiệm, đúng/sai (4 mệnh đề con), tự luận và **chạy slide học liệu (100% Trợ giảng)** trên hệ thống EduX CMCU (`https://edux.cmcu.edu.vn`).

Phiên bản **v3.0** được viết lại toàn diện:
1. **Không cần Gemini API Key**: Kết nối trực tiếp vào các công cụ AI Coding CLI có sẵn trên máy (**Google Antigravity `agy`**, **OpenAI Codex `codex`**, **Claude Code `claude`**, **OpenCode `opencode`**).
2. **Công cụ chạy Slide CMCU-Vạn-Năng V3.2 FIX**: Tích hợp nguyên bản bộ engine **CMCU-Vạn-Năng-V3.2 FIX** do bạn phát triển (đã sửa lỗi tự qua câu & chống dừng sớm tại trang cuối với cơ chế xác nhận 3/3 nhịp liên tiếp).
3. **Công cụ CLI v3.0 mới & Script khởi chạy chuẩn cho Linux (`run.sh`)**: Hỗ trợ điều khiển trực tiếp qua Terminal CLI, cờ dòng lệnh (`--cli`, `--web`, `--slide`, `--solve`), hoặc giao diện Web Dashboard (`http://127.0.0.1:8765`).

---

## 🚀 HƯỚNG DẪN KHỞI CHẠY TRÊN LINUX (1 LỆNH DUY NHẤT)

Tại thư mục gốc hoặc thư mục `edux-auto-solver`, chạy:

```bash
./run.sh
```

Hoặc sử dụng các cờ chạy nhanh của **CLI v3.0**:
- Mở trực tiếp **Bảng điều khiển CLI v3.0** trên Terminal:
  ```bash
  ./run.sh --cli
  ```
- Mở **Web Dashboard** tại `http://127.0.0.1:8765`:
  ```bash
  ./run.sh --web
  ```
- Kích hoạt ngay **CMCU-Vạn-Năng V3.2 FIX** cho bài giảng đang mở trên Chrome:
  ```bash
  ./run.sh --slide
  ```
- Giải ngay **Bài tập đang mở** bằng AI Coding CLI (`agy` / `codex`):
  ```bash
  ./run.sh --solve --provider antigravity
  ```

---

## 🎯 CÁC CHỨC NĂNG TRONG CÔNG CỤ CLI MỚI (v3.0)

- **Phím `[1]` - Quét môn học & Chạy tự động (Slide / Bài tập)**:
  - Quét toàn bộ danh sách Chương, % Trợ giảng, Slide, Bài tập AI, Bài tập thường.
  - Nhập **`S`**: Tự động chạy **CMCU-Vạn-Năng V3.2 FIX** cho tất cả các Slide chưa đạt 100%.
  - Nhập **`A`**: Tự động giải hàng loạt tất cả **Bài tập AI**.
  - Nhập **`M`**: Tự động giải hàng loạt tất cả **Bài tập thường**.
  - Nhập **STT** (VD: `1` hoặc `1,3,5`): Chạy các mục được chỉ định.
- **Phím `[2]` - Chạy CMCU-Vạn-Năng V3.2 FIX (Slide đang mở)**:
  - Bơm trực tiếp script `CMCU-Vạn-Năng-V3.2 FIX` vào trình duyệt, tự động mở câu hỏi `"Trả lời trên lớp"`, dò Hint/Blacklist, tự qua câu và chỉ dừng khi xác nhận 3/3 nhịp ở trang cuối.
- **Phím `[3]` - Giải Bài tập đang mở trên màn hình**:
  - Giải bài tập hiện tại bằng Antigravity/Codex CLI, rà soát 100% câu hỏi và tự động nộp bài.
- **Phím `[4]` - Giải chỉ định từ câu X đến câu Y**:
  - Giải một khoảng câu tùy chọn (không tự nộp bài).
- **Phím `[5]` - Dán trực tiếp Link bài tập (URL)**:
  - Mở link bài tập và giải ngay.
- **Phím `[6]` - Cấu hình Công cụ AI Coding (`Antigravity` / `Codex` / `Claude`)**:
  - Chuyển đổi nóng giữa `auto`, `antigravity` (`agy`), `codex` (`codex exec`), `claude`, `opencode` và chọn Model suy luận (`gemini-3.8-flash-low`, `gemini-4-argon-medium`, `gpt-6-luna`...).
- **Phím `[7]` - Quản lý Ngân hàng đề (Question Bank Cache)**:
  - Xem thống kê hoặc xóa cache câu hỏi.
