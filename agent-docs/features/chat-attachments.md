# Đính kèm PDF / ảnh khi chat với chatbot

## Mục tiêu
Người dùng đính kèm PDF hoặc ảnh ngay trong khung chat; chatbot (Gemini) đọc tệp cùng câu hỏi; tệp được lưu (tính vào hạn mức dung lượng), xem lại được và xoá được.

## Đã làm (2026-10-18)
- **Luồng:** chọn tệp bằng nút kẹp giấy (tối đa 3 tệp / tin, PDF/PNG/JPEG/WebP, ≤ 5 MB mỗi tệp, tổng 20 MB / người) → tải lên NGAY (`POST /me/files`, lưu Cloudinary, kiểm tra theo nội dung) và hiện chip tệp trong khung soạn → gửi tin kèm `attachment_ids`. Bỏ chip trước khi gửi thì tệp bị xoá luôn. Chỉ gửi tệp, không gõ chữ vẫn được (câu hỏi mặc định "Hãy đọc tệp đính kèm và tóm tắt nội dung chính giúp mình.").
- **BE** (`app/services/chat/attachments.py`, `conversations.py`, `graph.py`): `SendMessageIn.attachment_ids` (≤ 3, phải là tệp loại attachment của CHÍNH người gửi, không nhận ảnh đại diện; sai thì 422 `ATTACHMENT_NOT_FOUND`). Checkpoint chỉ lưu THAM CHIẾU (id, tên, loại, kích thước, URL) trong `additional_kwargs["attachments"]`; nội dung tệp được tải từ Cloudinary lúc gọi LLM và gửi dạng khối base64 (`file` cho PDF, `image` cho ảnh) trong tin của người dùng, KHÔNG lưu vào checkpoint. Chỉ 3 tin gần nhất có tệp mới gửi lại nội dung tệp (mỗi lượt gửi lại đều tốn token); tin cũ hơn chỉ còn ghi chú tên tệp. Có bộ nhớ đệm 32 MB nội dung tệp. Tệp không tải được (đã xoá...) thì ghi chú để chatbot nói rõ.
- **Prompt / tuyến:** tin có tệp luôn đi tuyến `regulation` (đọc tệp, đối chiếu quy chế nếu liên quan, không tìm web, không phân loại) và prompt có thêm đoạn `ATTACHMENT_INTRO`. Tin có tệp KHÔNG dùng câu trả lời có sẵn (chào hỏi / câu gợi ý) nhưng vẫn bị lọc chửi thề, vẫn qua hàng đợi và giới hạn tốc độ.
- **Giới hạn tải lên:** `UPLOAD_RATE_LIMIT` (mặc định `10/1m,60/1h`, cùng định dạng `CHAT_RATE_LIMIT`) chặn chuyện tải rồi xoá liên tục (429 `UPLOAD_RATE_LIMITED`).
- **FE:** `Composer` có nút kẹp giấy + chip tệp (đang tải / lỗi / kích thước / bỏ); tin của người dùng hiện tệp dạng liên kết, bấm MỞ TAB MỚI (trình duyệt tự xem trước PDF / ảnh); rê chuột (hoặc focus) vào tin nhắn hiện "Đã gửi lúc …" theo MÚI GIỜ người dùng đã cài (`useFormatDate`), áp cho cả tin của bot. Khách chat qua liên kết chia sẻ không có nút đính kèm. Tệp đã gửi xem / xoá bớt ở mục "Tệp của bạn" (bấm thanh dung lượng ở thanh bên).
- Đã thử THẬT: Gemini đọc đúng PDF (ngày 15/12, phòng A101) và ảnh, trả lời kèm Điều 27 của quy chế; giao diện thử bằng Chrome headless (chip, gửi, giờ gửi khi rê chuột, bấm tệp mở tab Cloudinary). Test: `tests/test_attachments.py` (13 test).

## Chưa làm / lưu ý
- PDF dài cũng gửi nguyên cho Gemini (đơn giản, đọc được hình/bảng nhưng tốn token); chưa có chế độ trích văn bản + RAG riêng cho tệp dài.
- Chưa nhận Word/Excel, chưa kéo-thả / dán ảnh vào khung chat.
- Xoá tệp ở "Tệp của bạn" thì liên kết trong tin cũ không mở được nữa (chatbot ghi chú "không đọc được tệp" nếu hỏi tiếp về tệp đó).
- URL tệp là URL có chữ ký (ai có URL thì mở được); người được chia sẻ cuộc trò chuyện xem được các tệp trong đó.
