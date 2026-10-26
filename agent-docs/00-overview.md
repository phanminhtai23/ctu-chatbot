# Overview

## Mục tiêu

Chatbot hỗ trợ sinh viên CTU (Can Tho University) tra cứu và hỏi đáp về quy chế công tác học vụ — cách tính điểm, tín chỉ, các quy định theo học kỳ — dựa trên văn bản quy định chính thức (`QD3266_Quy_dinh_cong_tac_hoc_vu_danh_cho_sinh_vien_trinh_do_dai_hoc_hinh_thuc_chinh_quy_V3.pdf`).

## Tech stack

| Layer | Choice | Note |
|---|---|---|
| FE | React + Tailwind | CTU style, tham khảo gu thiết kế kiểu Claude |
| BE | FastAPI | |
| DB | PostgreSQL 16 | Docker Compose trên server ARM64 |
| LLM | Gemini (free tier) | orchestration qua LangGraph |
| Vector DB | ChromaDB nhúng | persistent Docker volume trên server |
| Test | pytest + npm | CI chạy backend offline tests và build/lint frontend |
| Deploy | GitHub Actions + GHCR | build image ARM64, deploy qua SSH và Docker Compose |

## Tech flow

1. User hỏi → FE gửi request → BE (FastAPI).
2. BE dùng LangGraph để định tuyến câu hỏi; tuyến tài liệu truy vấn ChromaDB và lấy các Điều liên quan.
3. BE gọi Gemini, kết hợp ngữ cảnh phù hợp rồi stream câu trả lời về FE.
4. Admin quản lý route và review tài liệu ở `/admin/documents`. Catalog hiện tại lưu các version trong `vector-docs/`; upload, Extract/OCR, Clean và Sync là các thao tác riêng.
5. GitHub Actions kiểm tra PR; khi commit được đưa vào `main`, build/push image `linux/arm64` lên GHCR rồi triển khai stack Docker Compose trên server.

> Chi tiết vận hành/deploy xem `DEPLOY.md`; cấu trúc và quy trình catalog tài liệu xem `vector-docs/README.md` và `features/admin-document-upload.md`.

## Cấu trúc code hiện tại

```
ctu-chatbot/
├── ctu-chatbot-fe/         Vite + React + TypeScript + Tailwind
│   └── src/                components, pages, hooks và lib
├── ctu-chatbot-be/         FastAPI + LangGraph + ChromaDB
│   └── app/
│       ├── api/v1/        Routers cho auth, chat, user và admin
│       ├── core/          config.py — settings đọc từ environment/.env
│       ├── db/            SQLAlchemy engine/session và migrations Alembic
│       ├── models/        SQLAlchemy models
│       ├── services/chat/ LangGraph, route catalog và phân loại
│       ├── services/ingest/ ingest legacy và staged document catalog
│       └── services/rag/  chunking, embeddings và ChromaDB
├── vector-docs/            route catalog và nguồn tài liệu version hóa
├── agent-docs/              feature notes và hướng dẫn phát triển
└── .github/workflows/       CI và deploy ARM64
```

- FE chạy: `cd ctu-chatbot-fe && npm ci && npm run dev` (copy `.env.example` → `.env` nếu cần đổi API base hoặc OAuth client ID).
- DB (dev): `docker compose up -d db` ở thư mục gốc → PostgreSQL 16, cổng host **5433**.
- BE chạy: tạo venv trong `ctu-chatbot-be/venv`, cài `requirements.txt`, copy `.env.example` → `.env`, chạy `alembic upgrade head`, rồi `uvicorn app.main:app --reload --port 8000`. Test offline: `pytest -q -m "not live"`.
- Migration: `alembic revision --autogenerate -m "..."` rồi `alembic upgrade head`.
- `agent-docs/` được version hóa trong repo để các contributor dùng chung feature notes và hướng dẫn.

## Danh sách feature

Xem chi tiết từng feature tại `agent-docs/features/`:

- User: `auth-google-login`, `chatbot-academic-qa`, `user-profile-edit`, `share-conversation`
- Admin: `admin-login` (role-based, không có trang login riêng), `admin-user-management`, `admin-api-key`, `admin-document-vectorization`, `admin-document-upload`

## Quyết định FE chung (2026-10-04)

- Routing: `react-router-dom`; routes `/`, `/login`, `/chat`, `/admin` (ẩn). `vercel.json` rewrite SPA.
- Dark mode: token màu trong `src/index.css` (`:root` / `.dark`), class `dark` trên `<html>`, lưu `localStorage` key `ctu-theme`, mặc định theo hệ điều hành. Component dùng token (`bg-surface`, `text-heading`...), brand navy/vàng giữ cố định.
- Chỉ có tiếng Việt (đã bỏ tiếng Anh 2026-10-18): mọi chữ trên giao diện nằm ở `src/i18n/vi.ts`, dùng qua `useI18n().t(key)` (không còn `lang`/`setLang`, không còn nút chuyển ngôn ngữ). Cột `users.language` ở BE vẫn còn nhưng FE không dùng.
- Nút đổi giao diện sáng/tối: `components/PrefToggles.tsx`.

## Quyết định chung FE+BE (2026-10-04)

- Auth: JWT Bearer. FE gắn `Authorization` trong `lib/api.ts`; BE trả 401 → FE tự xoá token và về `/login`.
- Cài đặt cá nhân (ngôn ngữ/theme/múi giờ) lưu ở bảng `users`; `localStorage` chỉ là cache để tránh nháy giao diện, nguồn đúng là DB.
- Phân quyền: cột `users.role` (`user` | `admin`); admin đăng nhập Google như mọi người, quyền cấp bằng SQL. Mọi endpoint `/api/v1/admin/*` dùng `require_admin`.

## Cấu hình Google login (tóm tắt)

1. Google Cloud Console → tạo project → *APIs & Services → OAuth consent screen* (User type: External; scope mặc định email/profile/openid là đủ).
2. *Credentials → Create credentials → OAuth client ID → Web application*; thêm `http://localhost:5173` khi phát triển và origin production (ví dụ `https://ctu-chatbot.io.vn`) khi deploy. Không cần redirect URI, không dùng client secret.
3. Đặt Client ID vào `VITE_GOOGLE_CLIENT_ID` (FE `.env`) và `GOOGLE_CLIENT_ID` (BE `.env`), khởi động lại cả hai.
4. Lưu ý consent screen đang ở *Testing* chỉ cho tối đa 100 *test users* đăng nhập; muốn mọi sinh viên dùng được phải chuyển sang *In production*.

## LLM / LangGraph (2026-10-04)

- Gemini gọi qua `langchain-google-genai`; model lấy từ `LLM_MODEL`, key từ `GEMINI_API_KEY` và/hoặc `GEMINI_API_KEY_N` (không giới hạn N) trong `.env` BE, tự xoay khi hết hạn mức.
- Lịch sử chat lưu bằng checkpointer Postgres của LangGraph (cùng database `ctu_chatbot`, bảng `checkpoint*` do `PostgresSaver.setup()` tự tạo lúc khởi động app, không qua Alembic).
- Test dùng `InMemorySaver` + LLM giả (không gọi Gemini thật, không cần Postgres) — đúng quy tắc test của dự án.

## Responsive (2026-10-04)

- Đã đo tự động ở 320 / 375 / 768 / 1024 / 1440px trên mọi trang + các hộp thoại (góp ý, chi tiết phản hồi): không tràn ngang, mọi nút/ô nhập >= 44px, hộp thoại nằm gọn trong màn hình. Khi thêm UI mới nên đo lại theo cách này.
- Điểm gãy chính là `md` (768px) cho bố cục sidebar và `lg` (1024px) cho các thanh tiêu đề: dưới `lg` thanh tiêu đề chat xếp 2 hàng (tiêu đề riêng, nút bên dưới).
- Thanh bên (chat/admin) mặc định **thu gọn dưới 1024px**, mở sẵn từ 1024px; lựa chọn của người dùng được nhớ (`ctu-chat-sidebar`, `ctu-admin-sidebar`). Trên điện thoại thu gọn = chỉ còn hàng logo + nút mở; chat có thêm nút `+` ở tiêu đề để tạo cuộc trò chuyện mới.
- Trang chat cao đúng bằng màn hình (`h-dvh`): chỉ vùng tin nhắn cuộn, ô nhập luôn ở đáy (quan trọng trên điện thoại).
- Chữ không có dấu cách (URL, mã...) phải `break-words`; bảng markdown trong câu trả lời cuộn ngang trong khung của nó.
- Trang đăng nhập: trên màn hình nhỏ phần giới thiệu gọn còn logo + tiêu đề để nút đăng nhập hiện ngay.

## Mã QR ủng hộ (2026-10-18)

- Admin tải ảnh QR ở tab "Mã QR ủng hộ" (`/admin/donate`), lưu thành file trên đĩa server (`DONATE_DIR`, mặc định `data/donate`); hiện trong hộp thoại thông tin cá nhân kèm GIF `donate_fee.gif`. Chi tiết: `features/donate-qr.md`.
