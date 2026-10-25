# Feature: share-conversation

- **Status:** done
- **Scope:** FE, BE, DB

## What

User chia sẻ 1 conversation (đoạn chat với bot) cho bạn bè.

## Scope chi tiết

- FE: nút "Share", hiển thị trang conversation ở chế độ chia sẻ (read-only) cho người nhận link.
- BE: endpoint tạo share link (token/slug), endpoint lấy conversation theo share link, kiểm tra quyền xem.
- DB: cần cột/bảng lưu trạng thái share (ví dụ `share_token`, `is_public`) gắn với conversation.

## Notes

- Phụ thuộc `chatbot-academic-qa` (cần có bảng conversation trước).
- Cần quyết định: share link có hết hạn không, người xem cần login hay không.

### Đã làm — 2026-10-18: chia sẻ cuộc trò chuyện (email + liên kết, xem / chat tiếp)
**Quy tắc:** chủ sở hữu có toàn quyền. Người được chia sẻ chỉ ĐỌC trừ khi có quyền `chat`. Muốn chat tiếp phải đăng nhập bằng email CTU (đăng nhập được = đã qua kiểm tra tên miền). Admin không tự xem được cuộc trò chuyện của người khác.
- **Theo email** (`conversation_shares.kind='email'`): Sau khi mời, hộp thoại hiện thêm liên kết tới cuộc trò chuyện (`/chat/<id>`) kèm nút Sao chép để gửi cho người được mời (họ đăng nhập bằng đúng email là vào được). ô tìm có gợi ý theo email/tên (`GET /shares/suggestions?q=`, ≥ 2 ký tự, tối đa 8, không gồm chính mình). Mời được cả email CTU chưa từng đăng nhập (lời mời có hiệu lực khi họ đăng nhập); email ngoài trường không đăng nhập được thì bị từ chối (`EMAIL_NOT_ALLOWED`). Quyền `view` (Chỉ xem) hoặc `chat` (Được chat tiếp), đổi/gỡ bất cứ lúc nào. Người nhận thấy mục "Được chia sẻ với tôi" ở sidebar.
- **Theo liên kết** (`kind='link'`, mỗi cuộc trò chuyện một liên kết, token ngẫu nhiên 43 ký tự): trang công khai `/s/<token>`, ai có liên kết cũng ĐỌC được, không cần đăng nhập, không lộ email chủ. Liên kết quyền `chat`: đăng nhập email CTU để chat tiếp (đăng nhập xong quay lại đúng trang). Tắt liên kết hoặc "Tạo liên kết mới" thì liên kết cũ hết hiệu lực.
- **Chat nhiều người trong một cuộc trò chuyện:** tin của người không phải chủ gắn tên người gửi (`author_name`); lượt dùng và giới hạn 10 tin/5 phút tính theo người GỬI; mỗi cuộc trò chuyện chỉ chạy một lượt một lúc (409 / sự kiện `CONVERSATION_BUSY`); giao diện tự tải lại tin mới của người khác mỗi 6 giây khi đang mở một cuộc trò chuyện có chia sẻ.
- **API:** chủ: `GET/POST/PATCH/DELETE /conversations/{id}/shares[/people/{share_id}]`, `PUT/DELETE /conversations/{id}/shares/link`; người nhận: `GET /shares/with-me`, `GET /conversations/{id}` (có `access`, `owner_name`, `shared`), gửi tin như bình thường; liên kết: `GET /shared-links/{token}` (đăng nhập hay không đều được), `POST /shared-links/{token}/messages/stream`.
- **Code:** BE `app/services/sharing.py`, `app/api/v1/shares.py`, `app/models/conversation_share.py`, migration `d4e9b2a7c611`; FE `components/ShareDialog.tsx`, `pages/SharedView.tsx`, `lib/shares.ts`. Test: `tests/test_sharing.py` (21 test).
- Chưa làm: hết hạn liên kết theo thời gian; thông báo cho người được mời (hiện chỉ thấy khi đăng nhập).
