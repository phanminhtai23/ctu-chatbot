# Feature: admin-user-management

- **Status:** done (trừ activity log chi tiết)
- **Scope:** FE, BE, DB

## What

Admin quản lý user: xem thông tin, revoke account, xem activity log, xem request metrics.

## Scope chi tiết

- FE: trang danh sách user, chi tiết user, nút revoke, biểu đồ/bảng metrics.
- BE: endpoints list/get user, revoke account, ghi và truy vấn activity log, tính request metrics (ví dụ số request/user/ngày).
- DB: bảng `activity_logs` (user_id, action, timestamp...), có thể cần bảng/counter cho request metrics.

## Notes

- Phụ thuộc `auth-google-login` (cần bảng `users` tồn tại trước).
- "Revoke account": cần định nghĩa — xoá hẳn hay chỉ disable (`is_active=false`)?

### Đã làm — 2026-10-18: quản lý người dùng + dashboard thống kê
- **Ghi lượt dùng:** bảng `usage_events` (user, cuộc trò chuyện, có phải câu gợi ý không, thời gian; migration `c3d8a1f50b72`), ghi sau mỗi lượt hỏi-đáp thành công. Không lưu nội dung. Chỉ thống kê được từ lúc có bảng này.
- **Quản lý người dùng** (`/admin/users`): danh sách có tìm theo email/tên, lọc quyền/trạng thái, phân trang, số lượt hỏi + lần dùng gần nhất; xem chi tiết (biểu đồ 30 ngày); khoá/mở khoá (khoá thì đăng xuất ngay + thu hồi refresh token); đổi quyền user/admin. Chốt chặn: không tự khoá/hạ quyền mình, không bỏ admin hoạt động cuối cùng, admin khai báo trong `ADMIN_EMAILS` không hạ quyền được từ giao diện.
- **Dashboard** (`/admin/dashboard`): lọc thời gian (Hôm nay / 7 / 30 / 90 ngày / 6 tháng / 1 năm / tối đa 2 năm / khoảng ngày tuỳ chọn), gom theo ngày/tuần/tháng (tự động theo độ dài), so sánh kỳ liền trước (▲▼ %), bộ lọc nằm trên URL, xuất CSV. Thẻ chỉ số có sparkline: lượt hỏi, người dùng hoạt động, đăng ký mới, cuộc trò chuyện mới, lượt hỏi/người, tỉ lệ câu hỏi gợi ý. Biểu đồ: hoạt động theo thời gian, đăng ký mới theo kỳ, tổng người dùng tích lũy, đăng ký theo mốc 1 tuần/1 tháng/6 tháng/1 năm, câu hỏi gợi ý vs hỏi tự do, giờ cao điểm, theo thứ trong tuần (rê chuột xem chi tiết). DAU/WAU/MAU + độ gắn bó, top người dùng (bấm sang trang quản lý).
- Ngày/giờ tính theo giờ Việt Nam (UTC+7). API: `GET /admin/stats?days=|from=&to=&granularity=`, `/admin/stats/export.csv`, `/admin/users`. Test: `tests/test_admin_stats_users.py`.
- Chưa làm: activity log chi tiết từng hành động (chỉ có lượt hỏi); thống kê theo tuyến (quy chế / tìm web / lạc đề).

### 2026-10-18: dashboard nhớ bộ lọc
- Bộ lọc thời gian (khoảng, độ chi tiết, so sánh, ngày tuỳ chọn) được lưu vào `localStorage` (khoá `ctu-admin-dashboard-filters`). Vào lại `/admin/dashboard` mà URL không có bộ lọc thì tự khôi phục như lần trước; URL có bộ lọc (gửi link) thì dùng URL và ghi đè giá trị đã lưu. Code: `src/pages/admin/AdminDashboard.tsx`.

### 2026-10-18: dung lượng file mỗi người dùng
Danh sách người dùng có cột "Dung lượng" (đã dùng / hạn mức `USER_STORAGE_QUOTA_MB`), chi tiết người dùng có dòng dung lượng. Xem `user-file-storage.md`.
