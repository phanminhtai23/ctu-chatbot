# Feature: user-feedback

- **Status:** done (gửi + admin xem/đổi trạng thái: FE+BE+DB; còn thiếu nội dung hội thoại đi kèm)
- **Scope:** FE, BE, DB
- **Nguồn:** user yêu cầu thêm ngày 2026-10-04 (không có trong brainstorm gốc).

## What

User gửi góp ý / báo lỗi, chủ yếu để báo **câu trả lời sai của LLM** (sai nội dung, trích dẫn sai, thông tin cũ), ngoài ra báo lỗi hệ thống và góp ý chung.

## Scope chi tiết

- FE (xong):
  - Nút "Báo câu trả lời sai" dưới mỗi câu trả lời của bot → mở modal, type `answer_issue`.
  - Nút "Góp ý" ở header trang chat → mở modal, type `general`.
  - Modal: chọn loại vấn đề (radio) + ô mô tả (tối đa 1000 ký tự; bắt buộc khi chọn "Khác"), có trạng thái đang gửi / thành công / lỗi.
  - Code: `components/FeedbackModal.tsx`, `lib/feedback.ts`.
- BE (xong): `POST /api/v1/feedback` (cần JWT user), validate type/category khớp nhau, `other` bắt buộc có mô tả, `answer_issue` bắt buộc `message_id`.
- DB (xong): bảng `feedback` (FK `users`, CHECK constraint type/category/status).
- Admin xem feedback (xong): trang `/admin/feedback` (lọc loại/trạng thái, xem chi tiết, đổi trạng thái new/reviewed/resolved). BE: `GET /api/v1/admin/feedback` (mới nhất trước, kèm `user_email`) và `PATCH /api/v1/admin/feedback/{id}` body `{status}`; cả hai yêu cầu role admin.

## API contract (FE đang gọi theo contract này)

`POST /api/v1/feedback`

```json
{
  "type": "answer_issue | general",
  "category": "wrong_answer | wrong_citation | outdated | bug | suggestion | other",
  "message": "string, tối đa 1000 ký tự, có thể rỗng trừ khi category = other",
  "conversation_id": "string | null",
  "message_id": "string | null   // bắt buộc khi type = answer_issue"
}
```

Response: `201` với `{ "id": "..." }`. Lỗi: `4xx/5xx` → FE hiện thông báo lỗi và cho gửi lại.

Gợi ý bảng `feedback`: `id, user_id, type, category, message, conversation_id, message_id, created_at, status (new/reviewed/resolved)`.

## Notes

- Đã bỏ toàn bộ mock; FE gọi BE thật cho cả phía user lẫn admin.
- Ngoài scope (hỏi user trước khi làm): rate limit gửi feedback, đính kèm ảnh.
- `conversation_id` = id cuộc trò chuyện, `message_id` = id tin nhắn của bot trong LangGraph (FE gửi giá trị thật từ `pages/Chat.tsx`). Vẫn là chuỗi tự do ở DB, chưa đặt FK (tin nhắn nằm trong checkpoint, không có bảng riêng).
- Nên snapshot câu hỏi + câu trả lời của bot ở BE theo `message_id` khi lưu, để admin xem đúng ngữ cảnh dù hội thoại bị xoá/sửa sau đó. Hiện `question`/`answer` luôn `null` vì chưa có bảng conversations/messages — làm khi có `chatbot-academic-qa`.

## Huy hiệu phản hồi chưa đọc (admin)
- `GET /api/v1/admin/feedback/unread-count` (chỉ admin) trả `{count}` = số phản hồi có `status = new`.
- Thanh điều hướng admin (`AdminLayout`) hiện huy hiệu đỏ trên tab "Phản hồi người dùng" (tối đa "99+"; sidebar thu nhỏ thì hiện chấm đỏ). Tự làm mới mỗi 30 giây và ngay khi đổi trạng thái trong trang phản hồi (sự kiện `ctu:feedback-changed`).

## Cập nhật: "chưa đọc", nội dung bị báo cáo, số liệu tổng
- "Chưa đọc" = phản hồi còn trạng thái `new`. Admin bấm mở một phản hồi `new` thì tự chuyển thành `reviewed` ("Đã xem") và huy hiệu giảm.
- Phản hồi loại `answer_issue` lưu kèm bản chụp `question`/`answer` (cột mới, migration `a1c7e4d9b3f6`) lấy từ checkpoint lúc gửi, nên admin vẫn xem được dù người dùng xoá cuộc trò chuyện. Phản hồi cũ chưa có bản chụp thì tra trực tiếp từ lịch sử nếu còn.
- Trang phản hồi hiện 2 ô: tổng số phản hồi và số chưa giải quyết (`status != resolved`).
