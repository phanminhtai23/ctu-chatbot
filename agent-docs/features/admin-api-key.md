# Feature: admin-api-key

- **Status:** planned
- **Scope:** FE, BE, DB

## What

Admin thêm/quản lý API key (ví dụ key Gemini) dùng cho hệ thống.

## Scope chi tiết

- FE: form thêm/xem API key (ẩn giá trị thật, chỉ hiện masked).
- BE: endpoint lưu/dùng API key, encrypt trước khi lưu DB.
- DB: bảng `api_keys` (key đã mã hoá, provider, created_at...).

## Notes

- Không bao giờ lưu API key plaintext trong DB hoặc log.
