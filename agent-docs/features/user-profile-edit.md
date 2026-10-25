# Feature: user-profile-edit

- **Status:** in-progress (name/birthday + cài đặt đã xong FE+BE+DB; avatar chưa làm)
- **Scope:** FE, BE, DB

## What

User chỉnh sửa thông tin cá nhân: avatar, tên, ngày sinh.

## Scope chi tiết

- FE: form edit profile, upload avatar.
- BE: endpoint update profile, xử lý upload avatar (lưu ở đâu — cần quyết định: Supabase Storage?).
- DB: bảng `users` cần các cột: `avatar_url`, `name`, `birthday` (+ các cột từ `auth-google-login`: email, google_id...).

## Notes

- Trang FE `/profile`: email (chỉ đọc), họ tên, ngày sinh + **tuỳ chọn hiển thị lưu theo user**: ngôn ngữ (vi/en), giao diện (system/light/dark), múi giờ (IANA, mặc định `Asia/Ho_Chi_Minh`).
- BE: `GET /api/v1/me`, `PATCH /api/v1/me` (partial update; validate múi giờ IANA, ngày sinh không ở tương lai, tên <=100 ký tự). Bảng `users` (migration Alembic `create users and feedback`).
- Nút VI/EN và sáng/tối ở header cũng lưu vào tài khoản khi đã đăng nhập; mở trang trên máy khác sẽ lấy lại cài đặt từ DB.
- Múi giờ đang áp cho `useFormatDate` (hiện dùng ở trang admin feedback); các chỗ hiển thị thời gian khác (chat...) phải dùng hook này.
- **Chưa làm: upload avatar** (cột `users.avatar_url` đã có sẵn) — cần quyết định nơi lưu file (Supabase Storage?).

### 2026-10-18: chuyển sang hộp thoại
Trang `/profile` được thay bằng hộp thoại (`components/ProfileDialog.tsx`) mở từ nút bánh răng ở chân sidebar chat; `/profile` giờ chuyển hướng về `/chat`. Nút chuyển nhanh chat ↔ quản trị (chỉ admin) là một nút nhỏ ở đầu sidebar, bên trái nút thu gọn.

### 2026-10-18: ảnh đại diện và tệp
Đã làm: ảnh đại diện (tải ảnh riêng hoặc ảnh ngẫu nhiên mặc định) và lưu PDF/ảnh trên Cloudinary kèm hạn mức dung lượng. Chi tiết: `user-file-storage.md`.

### 2026-10-18: ngày sinh dd/mm/yyyy, về ảnh mặc định
- Ngày sinh nhập bằng ô chữ riêng (`components/DateField.tsx`, `lib/dates.ts`) LUÔN dạng dd/mm/yyyy (ô `type="date"` của trình duyệt hiện theo ngôn ngữ trình duyệt, có khi mm/dd/yyyy): gõ số tự chèn dấu "/", kiểm tra ngày có thật (31/02 báo lỗi) và khoảng 1900..hôm nay, nút lịch để chọn; nhập dở / sai thì chặn nút Lưu. Server vẫn nhận/trả ISO yyyy-mm-dd.
- Ảnh đại diện có 3 nút: "Tải ảnh", "Ngẫu nhiên" (quay ảnh mặc định mới), "Mặc định" (về ảnh mặc định của tài khoản: `DELETE /me/avatar?random=false`). Tài khoản mới có `avatar_url` để TRỐNG: ảnh mặc định (DiceBear `thumbs`) suy ra cố định từ id (`User.avatar`), nên "Mặc định" luôn về đúng ảnh lúc mới đăng ký.
