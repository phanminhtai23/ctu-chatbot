# Lưu file người dùng (ảnh đại diện, PDF / ảnh tải lên) trên Cloudinary

## Mục tiêu
Người dùng đổi được ảnh đại diện và tải PDF / ảnh lên để lưu; có hạn mức dung lượng; người dùng tự xoá bớt; admin theo dõi dung lượng từng người.

## Đã làm (2026-10-18)
- **Nơi lưu:** Cloudinary qua REST API có ký (`app/services/storage.py`, chỉ dùng `requests`, không thêm thư viện). Cấu hình `.env`: `CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET/FOLDER`. Thiếu thì endpoint tải file trả 503 `STORAGE_NOT_CONFIGURED`.
  - Ảnh đại diện: `image` + `upload` (công khai), thư mục `<FOLDER>/avatars`; URL lưu kèm biến đổi `c_fill,g_auto,w_256,h_256,f_auto,q_auto` (Cloudinary cắt vuông 256px, nén gọn).
  - PDF / ảnh tải lên: `raw`/`image` + `authenticated`, thư mục `<FOLDER>/files/<user_id>`. URL có chữ ký, bỏ chữ ký thì 404 (đã thử thật). URL chỉ trả cho chính chủ. Lưu ý: sau khi xoá, URL có thể còn mở được vài phút do bộ nhớ đệm CDN (đã gửi `invalidate`).
- **Bảng `user_files`** (migration `b7d2f4a8c915`): id, user_id (xoá user thì xoá dòng), kind `avatar|attachment`, filename, content_type, size_bytes, public_id, resource_type, delivery_type, url. Dung lượng đã dùng = tổng `size_bytes` (ảnh đại diện cũng tính).
- **Hạn mức (`.env`):** `USER_STORAGE_QUOTA_MB=20` (tổng mỗi người), `USER_UPLOAD_MAX_MB=5` (mỗi lần tải). Mã lỗi: 413 `FILE_TOO_LARGE` / `QUOTA_EXCEEDED`, 415 `UNSUPPORTED_TYPE`, 400 `EMPTY_FILE`, 502 `STORAGE_ERROR`, 503 `STORAGE_NOT_CONFIGURED`.
- **Kiểm tra file theo NỘI DUNG** (không tin tên/đuôi): PDF phải bắt đầu `%PDF-`; ảnh chỉ nhận PNG/JPEG/WebP giải mã được (`donate.check_image`, không nhận SVG/GIF). Body đọc theo luồng và dừng ngay khi vượt giới hạn.
- **API** (`app/api/v1/files.py`, cùng kiểu gửi nguyên file làm body như tải ảnh QR, tên file ở `?name=`): `GET /me/files` (danh sách + used/quota/max), `POST /me/files` (PDF hoặc ảnh), `DELETE /me/files/{id}` (chỉ file của mình, chỉ loại attachment), `PUT /me/avatar` (đổi ảnh, ảnh cũ bị xoá), `DELETE /me/avatar` (bỏ ảnh riêng, đổi sang ảnh ngẫu nhiên MỚI; gọi lại để "quay" ảnh khác).
- **Ảnh đại diện mặc định ngẫu nhiên:** DiceBear kiểu `thumbs` (CC0, mặt ngố đáng yêu), URL `https://api.dicebear.com/9.x/thumbs/svg?seed=<ngẫu nhiên>` (`app/core/avatar.py`), không tốn dung lượng. Tài khoản MỚI nhận ảnh này (không dùng ảnh Google nữa); tài khoản cũ để trống thì nhận ảnh cố định theo id; tài khoản cũ đã có ảnh Google thì giữ nguyên.
- **Admin:** `/admin/users` có cột "Dung lượng" (đỏ khi ≥ 90% hạn mức) và dòng dung lượng trong hộp chi tiết; API `storage_bytes`, `storage_quota_bytes`.
- **Giao diện người dùng:** ảnh đại diện: hộp thoại thông tin cá nhân có "Tải ảnh lên" / "Đổi ảnh ngẫu nhiên". Dung lượng: thanh "đã dùng / tối đa" nằm ở THANH BÊN của trang chat, ngay phía trên tên người dùng (ẩn khi thu gọn thanh bên; cập nhật khi đóng hộp thoại hồ sơ). Hộp thoại hồ sơ có mục "Tệp của bạn": thanh dung lượng, danh sách tệp (mở xem, xoá 2 bước bấm). KHÔNG có nút tải tệp ở hồ sơ: tệp sẽ đến từ lúc người dùng đính kèm khi chat (chưa làm, xem dưới). Ảnh đại diện hiện ở thanh bên của chat và ở trang quản lý người dùng (component `Avatar`, có chữ cái đầu khi ảnh lỗi).
- Đã thử THẬT với tài khoản Cloudinary của dự án (tải, xem, chặn file quá 5 MB, chặn PDF giả, xoá, dọn sạch) và test offline `tests/test_user_files.py` (19 test, dùng kho giả).

## Chưa làm
- Nút đính kèm trong khung chat (`Đính kèm ảnh hoặc PDF`) vẫn bị tắt: chưa đưa file cho LLM đọc (xem phần bàn luận Gemini Files API / RAG riêng cho cuộc trò chuyện). Hiện file chỉ được lưu trữ.
- Chưa dọn file mồ côi trên Cloudinary nếu xoá thất bại do lỗi mạng; chưa có tác vụ định kỳ đối chiếu.

### 2026-10-18: ảnh Google gốc là ảnh mặc định
- Lỗi đã sửa: nút "Mặc định" trước đây đặt `avatar_url = NULL` và ảnh Google (lưu trong `avatar_url`) mất luôn. Nay cột `users.google_picture` (migration `d5f9b2c8a417`) giữ ảnh gốc của tài khoản Google, CẬP NHẬT mỗi lần đăng nhập Google (Google không gửi ảnh thì giữ ảnh đã biết). `User.default_avatar` = ảnh Google gốc nếu có, không thì ảnh DiceBear cố định theo id; `User.avatar` = ảnh đã chọn (`avatar_url`) hoặc ảnh mặc định.
- Nút "Mặc định" (`DELETE /me/avatar?random=false`) về ảnh mặc định ở trên; "Ngẫu nhiên" quay ảnh DiceBear mới; tải ảnh riêng thì dùng ảnh đó. Migration chép ảnh Google đang là `avatar_url` của các tài khoản hiện có sang `google_picture`. Tài khoản nào đã lỡ bấm "Mặc định" bản cũ (ảnh Google bị xoá) thì chỉ cần đăng nhập lại bằng Google một lần là có lại.
