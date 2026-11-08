# Feature: user-source-routes

- **Status:** done (FE + BE + DB)
- **Scope:** FE, BE, DB
- **Yêu cầu từ user (2026-11-08):** user cấu hình những "domain" muốn hỏi (như route trên admin) để chatbot chính xác và nhanh hơn; mặc định là tất cả.

## Quyết định
Mỗi **tài liệu** (tuyến `document` trong `vector-docs/routes.json`) là một domain; tìm kiếm web (tuyến `web`, nếu bật) cũng chọn được. Chào hỏi và ngoài phạm vi luôn mở.

## Implementation
- **DB:** cột `users.document_routes` (JSON, nullable; NULL = tất cả). Migration `f7a1d4e8b603`.
- **API:** `GET /api/v1/me` trả `document_routes`; `PATCH /me {document_routes: [...] | null}` (1-50 id hợp lệ, bỏ trùng; null = quay về tất cả). `GET /api/v1/documents/catalog/routes` (cần đăng nhập) liệt kê nguồn chọn được: tuyến tài liệu đã đồng bộ + web (nhãn, số quyết định, mô tả).
- **Chat:** `conversations.py` đọc `user.document_routes` và truyền qua `run_turn`/`stream_turn` → `_config` đặt `configurable.allowed_routes`. `graph.generate` (nhận `config: RunnableConfig`) lọc các tuyến `document`/`web` theo danh sách; tuyến khác giữ nguyên. Danh sách lỗi thời (mọi id đã bị xoá) thì bỏ qua, dùng tất cả. Câu trả lời lưu sẵn (cached) không đi qua lọc này.
- **FE:** tab **Nguồn hỏi** trong `ProfileDialog` (`components/SourcePicker.tsx`): thẻ chọn từng nguồn kèm số quyết định + mô tả, "Dùng tất cả", bắt buộc chọn ít nhất một, lưu qua `updateProfile`.
- **Test:** `tests/test_user_routes.py`.

## Notes
- Chọn bớt nguồn chỉ thu hẹp danh sách cho bước phân loại; các luật chạy trước LLM (chào hỏi, nhắc "Điều N") vẫn áp dụng như cũ.
- Nếu admin gỡ bớt tài liệu, lựa chọn đã lưu của user tự bỏ qua id không còn tồn tại.
