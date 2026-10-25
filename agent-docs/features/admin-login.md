# Feature: admin-login

- **Status:** done (đổi hướng: không có trang login riêng cho admin)
- **Scope:** FE, BE, DB

## What

Admin đăng nhập bằng username/password (tạo mặc định sẵn — không phải Google OAuth như user thường).

## Scope chi tiết

- FE: form login riêng cho admin.
- BE: endpoint auth admin (username/password), session/token cho admin.
- DB: bảng `admins` (hoặc cột `role` trong `users`) + password hash.

## Notes

- **Quyết định (2026-10-04, theo user):** KHÔNG làm form username/password cho admin. Admin đăng nhập Google như user thường; quyền do cột `users.role` (`user` | `admin`). Chưa có UI cấp quyền: sửa trực tiếp DB (`update users set role='admin' where email='...'`).
- BE: `require_admin` (`app/api/deps.py`) → 403 nếu không phải admin; áp cho mọi endpoint `/api/v1/admin/*`.
- FE: `RequireAdmin` chặn `/admin/*` (user thường bị đẩy về `/chat`); link "Khu vực quản trị" chỉ hiện trong sidebar chat khi `role='admin'`; `/admin` redirect sang `/admin/feedback`. Đã xoá `AdminLogin.tsx`.
- Quyền thật nằm ở BE; chặn ở FE chỉ để giao diện gọn.
- Phần "password mặc định" trong brainstorm gốc không còn áp dụng.

### 2026-10-18: cấp quyền admin bằng `ADMIN_EMAILS` trong `.env`
- `ADMIN_EMAILS=a@gmail.com,b@ctu.edu.vn` (cách nhau bằng dấu phẩy/chấm phẩy/khoảng trắng, không phân biệt hoa thường). Đăng nhập thành công bằng email trong danh sách → có `role='admin'`: tài khoản chưa có thì được tạo luôn với quyền admin, tài khoản đã có thì được nâng quyền ở lần đăng nhập kế (không cần sửa DB tay).
- Thứ tự kiểm tra khi đăng nhập (Google và dev-login dùng chung `_login`): (1) email thuộc `ADMIN_EMAILS` hoặc user đã là admin → cho qua, miễn giới hạn tên miền; (2) không phải admin → phải thuộc `ALLOWED_EMAIL_DOMAINS` (đuôi ctu.edu.vn / edu.ctu.vn); (3) tài khoản bị vô hiệu hoá vẫn bị chặn kể cả là admin.
- Bỏ email khỏi `.env` KHÔNG tự hạ quyền (tránh tự khoá mình; muốn hạ thì sửa `users.role` trong DB). Test: `tests/test_admin_emails.py`.
