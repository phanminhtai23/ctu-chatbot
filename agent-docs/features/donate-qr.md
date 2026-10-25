# Feature: donate-qr

- **Status:** done (FE + BE; không cần DB). Đã kiểm tra giao diện bằng trình duyệt thật (2026-10-18).
- **Scope:** FE, BE
- **Nguồn:** user yêu cầu thêm ngày 2026-10-18 (không có trong brainstorm gốc).

## What

Admin có một tab để tải ảnh **mã QR ủng hộ** lên; ảnh lưu ở server. Ảnh hiện trong hộp thoại **thông tin cá nhân** của người dùng (không còn ở trang landing), kèm đoạn kêu gọi ủng hộ để admin có kinh phí duy trì máy chủ và LLM, và ảnh GIF `ctu-chatbot-fe/src/assets/donate_fee.gif` nhỏ, căn giữa, nằm phía trên QR.

## Scope chi tiết

- **BE** (`app/api/v1/donate.py`, `app/services/donate.py`):
  - `GET /api/v1/donate` (công khai) → `{has_qr, version}`.
  - `GET /api/v1/donate/qr` (công khai, vì thẻ `<img>` không gửi được Authorization) → ảnh; có `ETag` + trả `304` khi trùng, `Cache-Control: no-cache`, `X-Content-Type-Options: nosniff`; `404 NO_QR` nếu chưa có.
  - `PUT /api/v1/admin/donate/qr` (admin) — gửi nguyên file làm body (cùng cách tải PDF ở `admin/documents`, không dùng multipart nên không cần thêm thư viện). Lỗi: `413 IMAGE_TOO_LARGE`, `400 INVALID_IMAGE`.
  - `DELETE /api/v1/admin/donate/qr` (admin) → `204`, gọi lại khi không có ảnh cũng `204`.
- **Lưu trữ:** một file trên đĩa server `data/donate/qr.<png|jpg|webp>` (`DONATE_DIR`, mặc định `data/donate`, tương đối so với `ctu-chatbot-be`; đã thêm vào `.gitignore`). Ghi qua file tạm + `os.replace` nên không bao giờ có ảnh ghi dở; đổi định dạng thì file cũ bị xoá. `version` = mtime+size, FE đưa vào URL ảnh để không dùng ảnh cũ trong cache.
- **Kiểm tra ảnh (BE là nơi quyết định):** kiểu ảnh lấy từ **nội dung** bằng Pillow (không tin tên file/`Content-Type`), phải giải mã/`verify()` được, chỉ nhận PNG/JPEG/WebP (**không nhận SVG** vì có thể chứa script, cũng không nhận GIF), tối đa `DONATE_QR_MAX_MB` (mặc định 2 MB) và 4096 px mỗi cạnh. Tải lỗi thì ảnh đang dùng được giữ nguyên.
- **FE:**
  - Tab admin "Mã QR ủng hộ" (`/admin/donate`, `pages/admin/AdminDonate.tsx`): chọn hoặc kéo-thả ảnh, xem trước ảnh đã chọn rồi mới Lưu, thay ảnh, xoá (có hộp xác nhận), và cột "Người dùng sẽ thấy" xem trước đúng giao diện người dùng.
  - `components/DonateSection.tsx`: tiêu đề + lời kêu gọi + QR (nền trắng cố định để quét được cả ở dark mode) + GIF cạnh nhau (tự xuống dòng ở màn hình hẹp). Gắn vào cuối `ProfileDialog`. **Chưa có QR (hoặc ảnh hỏng) thì không hiện gì.**
  - `lib/donate.ts`: API + kiểm tra nhanh ở trình duyệt (kiểu/kích thước) để báo lỗi sớm.
- **Landing page:** `<DonateSection band />` đặt giữa khối CTA và footer của `pages/Landing.tsx`: dải toàn chiều ngang, thẻ rộng tối đa 760 px; chưa có QR thì cả dải biến mất (không để khoảng trống).
- Chữ ở `i18n/vi.ts` (`donate.*`, `admin.donate.*`, `admin.nav.donate`).

## Notes

- Test BE: `tests/test_donate.py` (11 test: quyền, xem công khai, ETag/304, đổi định dạng chỉ còn một file, kiểu lấy từ nội dung, từ chối SVG/GIF/rác/rỗng/cụt/quá lớn/quá rộng, lỗi không làm mất ảnh cũ, xoá idempotent). Toàn bộ test offline: 545 pass. Đã chạy API thật qua server (upload/xem không đăng nhập/304/từ chối/403/preflight CORS cho `PUT`/xoá).
- Ảnh QR nằm trên đĩa server như tài liệu quy định đã nạp: nếu chỗ chạy BE có đĩa tạm (deploy kiểu container không gắn volume) thì ảnh mất khi deploy lại — cần gắn volume cho `data/` hoặc đổi sang lưu DB/Supabase Storage.
- Lời kêu gọi ủng hộ là chữ cố định trong `vi.ts`, admin chưa sửa được qua giao diện.
- Đã thử bằng Playwright (2026-10-18): admin tải ảnh lên → xem trước → lưu → thấy ngay ở cột "Người dùng sẽ thấy", ở cuối landing (khi chưa đăng nhập cũng thấy) và trong hộp thoại thông tin cá nhân. Ảnh chụp: `e2e-report/screenshots/9x-*`.
- Server BE đang chạy phải khởi động lại mới có route mới (nếu không chạy với `--reload`).
