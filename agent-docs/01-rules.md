# Rules

## Cách code

- Mỗi lần chỉ làm **1 feature**, triển khai đủ FE + BE + DB cho feature đó rồi mới sang feature tiếp theo. Không làm dở dang nhiều feature song song.
- Trước khi sửa code của 1 feature, đọc file tương ứng trong `agent-docs/features/` để biết scope và trạng thái hiện tại.
- Không thêm feature/scope ngoài những gì đã liệt kê trong `agent-docs/features/` mà không hỏi lại user.

## Cách test

- Dùng `pytest`.
- Với phần liên quan LLM, test bằng DeepSeek chat API chạy local (không gọi Gemini thật trong test để tránh phụ thuộc free-tier quota).

## Cách đọc/cập nhật memory (agent-docs)

- Trước khi bắt đầu việc gì liên quan 1 feature: đọc file `agent-docs/features/<feature>.md`.
- Sau khi hoàn thành/thay đổi: cập nhật `status` (`planned` → `in-progress` → `done`) và ghi chú lại quyết định/thay đổi quan trọng vào phần `Notes` của đúng file đó.
- Không gộp nhiều feature vào 1 file. Mỗi feature = 1 file riêng trong `agent-docs/features/`.
- Nếu phát sinh quyết định kiến trúc ảnh hưởng nhiều feature, ghi vào `agent-docs/00-overview.md`, không ghi lặp lại ở từng feature file.
