# Overview

## Mục tiêu

Chatbot hỗ trợ sinh viên CTU (Can Tho University) tra cứu và hỏi đáp về quy chế công tác học vụ — cách tính điểm, tín chỉ, các quy định theo học kỳ — dựa trên văn bản quy định chính thức (`QD3266_Quy_dinh_cong_tac_hoc_vu_danh_cho_sinh_vien_trinh_do_dai_hoc_hinh_thuc_chinh_quy_V3.pdf`).

## Tech stack

| Layer | Choice | Note |
|---|---|---|
| FE | React + Tailwind | CTU style, tham khảo gu thiết kế kiểu Claude |
| BE | FastAPI | |
| DB | PostgreSQL | deploy trên Supabase |
| LLM | Gemini (free tier) | orchestration qua LangGraph |
| Test | pytest | dùng DeepSeek chat API (local) làm model test/judge |
| Deploy FE | Vercel | |
| Deploy DB | Supabase | |

## Tech flow (khi code xong sẽ cập nhật chi tiết)

1. User hỏi → FE gửi request → BE (FastAPI).
2. BE truy vấn vector DB (tài liệu quy chế đã được vectorize) để lấy context liên quan.
3. BE gọi Gemini qua LangGraph, kết hợp context, trả lời.
4. Admin có pipeline riêng để upload/update tài liệu → vectorization → lưu vectordb.

> Phần này là khung ban đầu, SẼ được cập nhật lại khi kiến trúc thật được implement — xem từng file feature trong `features/` để biết trạng thái thật.

## Cấu trúc code hiện tại

```
ctu-chatbot/
├── ctu-chatbot-fe/         Vite + React + TypeScript + Tailwind v4
│   └── src/
│       ├── components/    UI components dùng chung
│       ├── pages/         Các trang
│       ├── hooks/         Custom hooks
│       ├── lib/           api.ts — fetch wrapper gọi BE (VITE_API_BASE_URL)
│       ├── App.tsx
│       └── main.tsx
└── ctu-chatbot-be/         FastAPI
    └── app/
        ├── api/v1/        Routers (health.py là ví dụ, mount tại /api/v1)
        ├── core/          config.py — Settings đọc từ .env
        ├── db/            session.py (SQLAlchemy engine/session), base.py (Base)
        ├── models/        SQLAlchemy models — còn trống, chờ feature đầu tiên
        ├── schemas/       Pydantic schemas — còn trống
        ├── services/      business logic / LLM orchestration — còn trống
        └── main.py        FastAPI app, CORS cho localhost:5173
    tests/test_health.py   ví dụ test với pytest + TestClient
```

- FE chạy: `cd ctu-chatbot-fe && npm run dev` (copy `.env.example` → `.env` nếu cần đổi `VITE_API_BASE_URL`).
- DB (dev): `docker compose up -d db` ở thư mục gốc → Postgres 16 container `ctu-chatbot-db`, cổng host **5433** (user `ctu`, db `ctu_chatbot`).
- BE chạy: tạo venv trong `ctu-chatbot-be/venv`, `pip install -r requirements.txt`, copy `.env.example` → `.env`, `alembic upgrade head`, rồi `uvicorn app.main:app --reload --port 8000`. Test: `pytest -q` (dùng SQLite in-memory, không cần Docker).
- Migration: `alembic revision --autogenerate -m "..."` rồi `alembic upgrade head`.
- `models/` (User, Feedback, RefreshToken, Conversation), `schemas/`, `api/v1/` (auth, users, feedback, conversations, admin_feedback), `api/deps.py` (get_current_user, require_admin, get_chat_graph), `services/` (`llm/` Gemini + xoay key, `chat/` LangGraph, `auth_tokens.py`, `google_auth.py`).
- `agent-docs/` không được push lên git (xem `.gitignore` ở root) — chỉ tồn tại local để AI/dev đọc ngữ cảnh.

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
2. *Credentials → Create credentials → OAuth client ID → Web application*; thêm *Authorized JavaScript origins*: `http://localhost:5173`, `http://localhost:5174` (và domain Vercel khi deploy). Không cần redirect URI, không dùng client secret.
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
