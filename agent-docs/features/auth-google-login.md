# Feature: auth-google-login

- **Status:** in-progress (code xong, chờ Google Client ID để chạy thật)
- **Scope:** FE, BE

## What

Sinh viên đăng nhập bằng Google, chỉ cho phép email thuộc domain `.edu.ctu.vn` (sinh viên CTU).

## Scope chi tiết

- FE: nút "Login with Google", xử lý OAuth redirect/callback.
- BE: verify Google token, kiểm tra domain email, tạo/lấy session user.
- DB: không có DB riêng cho feature này (dùng chung bảng `users` — xem `user-profile-edit`).

## Notes

- Luồng: FE dùng Google Identity Services (`@react-oauth/google`, nút `GoogleLogin`) → nhận ID token (`credential`) → `POST /api/v1/auth/google` → BE verify bằng `google-auth` (chữ ký, hạn, `aud` = `GOOGLE_CLIENT_ID`, `email_verified`) → kiểm tra domain → tạo/lấy user → trả JWT. **Không cần client secret, không cần redirect URI.**
- Cấu hình: cùng một Client ID đặt ở `ctu-chatbot-fe/.env` (`VITE_GOOGLE_CLIENT_ID`) và `ctu-chatbot-be/.env` (`GOOGLE_CLIENT_ID`). Để trống = nút Google bị vô hiệu hoá, `/auth/google` trả 503.
- Tài khoản mới có `role='user'`. Nâng admin bằng SQL: `update users set role='admin' where email='...'`. Đăng nhập lại không đổi role/tên/cài đặt đã lưu.
- **Token (2 loại, đều được lưu):**
  - Access token: JWT (PyJWT HS256), sống **7 ngày** (`ACCESS_TOKEN_EXPIRE_MINUTES`), FE lưu `localStorage` key `ctu-token`, gửi qua `Authorization: Bearer`.
  - Refresh token: chuỗi ngẫu nhiên (không phải JWT), sống **30 ngày** (`REFRESH_TOKEN_EXPIRE_DAYS`), FE lưu `localStorage` key `ctu-refresh-token`. BE chỉ lưu **băm sha256** trong bảng `refresh_tokens` (`user_id`, `expires_at`, `revoked_at`).
  - Xoay vòng: `POST /api/v1/auth/refresh` đổi refresh token (dùng được 1 lần) lấy cặp access + refresh mới; mỗi lần làm mới, hạn refresh lại tính 30 ngày từ lúc đó (không dùng app >30 ngày mới phải đăng nhập lại).
  - Dùng lại refresh token cũ: trong 30 giây (hai tab đua nhau) chỉ bị từ chối; sau 30 giây coi là nghi bị đánh cắp → thu hồi mọi refresh token của user đó.
  - `POST /api/v1/auth/logout` (body `{refresh_token}`, 204) thu hồi refresh token ở server; FE gọi khi bấm Đăng xuất.
  - FE (`lib/api.ts`): gặp 401 thì tự gọi refresh một lần (gộp nhiều request), rồi thử lại request; refresh bị từ chối mới đăng xuất, mất mạng thì giữ phiên. Nếu tab khác vừa làm mới xong thì dùng token mới của tab đó.
  - Lưu ở `localStorage` (không phải cookie HttpOnly) cho đơn giản khi FE/BE khác domain; đánh đổi: script độc hại chạy trong trang (XSS) đọc được token. Nếu cần chặt hơn, chuyển refresh token sang cookie HttpOnly + SameSite.
  - Chưa làm: dọn định kỳ các refresh token đã hết hạn trong DB.
- `POST /api/v1/auth/dev-login` (404 khi `ENV != dev`) + form đăng nhập thử (`VITE_DEV_LOGIN=true`) chỉ để dev khi chưa có Client ID; tắt ở production.
- Domain email cho phép: `ALLOWED_EMAIL_DOMAINS` (mặc định `ctu.edu.vn`, `edu.ctu.vn`) — domain sinh viên thật quan sát được khi có người đăng nhập Google: `...@student.edu.ctu.vn` (khớp `edu.ctu.vn` theo kiểu subdomain, đúng như brainstorm). `ctu.edu.vn` giữ lại cho email giảng viên/nhân viên nếu có — chưa xác nhận, bỏ khỏi danh sách nếu không cần.
  - Đặt `ALLOWED_EMAIL_DOMAINS=[]` trong `.env` BE để cho MỌI email đăng nhập (chỉ khi test); xoá dòng đó để quay lại giới hạn.
  - **Tài khoản `role='admin'` được miễn giới hạn tên miền** (để admin dùng Gmail cá nhân). User thường: tài khoản mới phải đúng domain; tài khoản cũ sai domain bị chặn cả lúc đăng nhập lẫn với token đã cấp (`can_access` trong `app/core/access.py`, kiểm tra ở `get_current_user`).
- Điều hướng sau đăng nhập (`pages/Login.tsx`): admin luôn vào `/admin/feedback`; user thường quay lại trang đang định vào (nếu bị chặn giữa chừng) hoặc `/chat`. Tự bấm đăng xuất thì **không** nhớ trang cũ (`loggedOut` trong `AuthProvider`) — đã từng lỗi: đăng xuất ở `/profile` làm lần đăng nhập sau bị đưa thẳng vào `/profile`.
- Chưa test với Google thật (cần Client ID); đã test BE bằng cách mock verifier và FE kiểm tra nút Google render.
- Còn thiếu: không có refresh token / thu hồi token (revoke = `is_active=false`, kiểm tra mỗi request).
