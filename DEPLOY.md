# Hướng dẫn triển khai (deploy) CTU Chatbot

Tài liệu này mô tả cách đưa CTU Chatbot lên máy chủ thật. Hệ thống gồm 3 phần:

| Phần | Công nghệ | Chạy ở đâu |
|---|---|---|
| Backend (BE) | FastAPI + LangGraph + ChromaDB nhúng | 1 máy chủ / VPS / container (Python 3.10+) |
| Database | PostgreSQL 16 | cùng máy hoặc dịch vụ ngoài (Supabase, Neon, RDS...) |
| Frontend (FE) | React + Vite (file tĩnh sau khi build) | Vercel / Netlify / nginx / bất kỳ hosting tĩnh |

Ngoài ra cần: **API key Gemini** (LLM + embedding) và **OAuth Client ID của Google** (đăng nhập).

> Repo chưa có `Dockerfile` hay file cấu hình CI. Các ví dụ Docker / nginx / systemd bên dưới là mẫu để bạn chỉnh, **chưa được chạy thử trên máy chủ thật**.

---

## 1. Điều cần biết trước khi deploy

1. **Chỉ chạy MỘT worker backend** (`uvicorn ... --workers 1`, không dùng `--workers N`, không chạy nhiều bản sao cùng lúc). Hàng đợi lượt chat, bộ đếm giới hạn tốc độ, tiến trình nạp tài liệu và ChromaDB nhúng đều nằm trong bộ nhớ / ổ đĩa của một process. Chạy nhiều worker thì mỗi worker đếm riêng và có thể hỏng dữ liệu vector.
2. **Cần ổ đĩa bền (volume)** cho 3 thư mục của backend, nếu không sẽ mất dữ liệu khi build lại container:
   - `ctu-chatbot-be/chroma_db/` — kho vector ChromaDB.
   - `ctu-chatbot-be/data/documents/` — các phiên bản tài liệu admin đã nạp.
   - `ctu-chatbot-be/data/donate/` — ảnh QR ủng hộ.
   - (`chroma_db/` cũng chứa vector của "Kiến thức bổ sung" do admin nhập; nội dung các mục nằm trong Postgres. Mất `chroma_db/` thì vào trang quản trị bấm "Embedding lại tất cả".)
3. **Lịch sử chat nằm trong Postgres** (bảng checkpoint của LangGraph, tự tạo khi khởi động) nên phải sao lưu database.
4. Backend cần thấy file `vector-docs/qd3266-clean.md` (nằm ở thư mục gốc repo, cùng cấp `ctu-chatbot-be/`) để dựng kho vector lần đầu. Khi đóng gói riêng backend, nhớ copy file này hoặc đặt biến `RAG_SOURCE_PATH`.
5. Lần khởi động đầu tiên, backend gọi API embedding để nhúng từng Điều của văn bản. Cần key Gemini hợp lệ và có mạng; các lần sau dùng lại `chroma_db/`.

---

## 2. Chuẩn bị bên ngoài

### 2.1. API key Gemini
- Lấy key ở Google AI Studio. Điền 1–9 key vào `GEMINI_API_KEY_1..9`; hết hạn mức (429) thì tự xoay sang key kế tiếp.
- Hạn mức Gemini tính theo **project**, không theo key: nhiều key cùng một project vẫn dùng chung một hạn mức. Muốn cộng dồn hạn mức, tạo mỗi key ở một project riêng.
- Ước tính sức chịu tải (chưa đo thực tế), với `gemini-3.5-flash-lite` mức 15 RPM / 500 RPD mỗi project và 6 project: tối đa khoảng 60 lượt hỏi/phút và khoảng 2.000 lượt/ngày. Cùng một project thì chia cho số key. Bật billing để tăng hạn mức nhiều lần.

### 2.2. Đăng nhập Google
1. Google Cloud Console → APIs & Services → Credentials → tạo **OAuth client ID** loại **Web application**.
2. Mục **Authorized JavaScript origins**: thêm địa chỉ frontend (ví dụ `https://chatbot.example.edu.vn`).
3. Lấy **Client ID**, dùng cho cả backend (`GOOGLE_CLIENT_ID`) và frontend (`VITE_GOOGLE_CLIENT_ID`).

### 2.3. Cloudinary (lưu file người dùng)
- Tạo tài khoản Cloudinary (gói miễn phí đủ để thử), lấy Cloud name, API Key, API Secret ở Dashboard.
- Ảnh đại diện lưu công khai; PDF/ảnh tải lên lưu dạng `authenticated` (URL có chữ ký). Không cần cấu hình gì thêm trên Cloudinary.
- Ảnh đại diện mặc định ngẫu nhiên lấy từ DiceBear (`api.dicebear.com`), máy người dùng phải truy cập được tên miền này.

### 2.4. PostgreSQL
- Tạo database và user riêng, ví dụ `ctu_chatbot`.
- Chuỗi kết nối dạng `postgresql://USER:PASSWORD@HOST:5432/ctu_chatbot` (dịch vụ ngoài thường yêu cầu thêm `?sslmode=require`).
- Chạy thử cục bộ bằng `docker compose up -d db` (xem `docker-compose.yml`, cổng 5433). **Đừng dùng mật khẩu mẫu trong file đó ở production.**

---

## 3. Triển khai backend

### 3.1. Cài đặt
```bash
cd ctu-chatbot-be
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt     # có cả thư viện chạy test, không sao
```

### 3.2. Cấu hình `.env`
Sao chép `.env.example` thành `.env` rồi chỉnh. **Không commit file này.** Các biến quan trọng khi lên production:

| Biến | Ghi chú |
|---|---|
| `ENV` | Đặt **`prod`** (khác `dev`). Khi đó endpoint `/auth/dev-login` (đăng nhập không cần Google) bị tắt. |
| `SECRET_KEY` | **Bắt buộc đổi** thành chuỗi ngẫu nhiên dài: `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Đổi key này sẽ làm mọi người phải đăng nhập lại. |
| `DATABASE_URL` | Chuỗi kết nối Postgres ở 2.4. |
| `GEMINI_API_KEY_1..9` | Key Gemini (2.1). Cần ít nhất 1 key. |
| `LLM_MODEL` | Mặc định `gemini-3.5-flash-lite`. |
| `GOOGLE_CLIENT_ID` | Client ID ở 2.2. Để trống thì tắt đăng nhập Google. |
| `ADMIN_EMAILS` | Email quản trị viên, cách nhau bằng dấu phẩy. Đăng nhập bằng email này là có quyền admin (kể cả ngoài tên miền được phép). |
| `ALLOWED_EMAIL_DOMAINS` | Danh sách JSON, mặc định `["ctu.edu.vn","edu.ctu.vn"]`. Email sinh viên thật là `@student.ctu.edu.vn` nên khớp `ctu.edu.vn` (subdomain được chấp nhận). **Không đặt `[]` ở production** (cho mọi email đăng nhập). |
| `CORS_ORIGINS` | Danh sách JSON các địa chỉ frontend được gọi API, ví dụ `["https://chatbot.example.edu.vn"]`. Mặc định chỉ có localhost, quên chỉnh là trình duyệt sẽ báo lỗi CORS. |
| `CHAT_RATE_LIMIT` | Giới hạn mỗi người dùng. Khuyến nghị `10/5m,40/1d` (xem mục 6). |
| `CHAT_MAX_CONCURRENT` | Số lượt chat chạy đồng thời, mặc định 4; tăng lên 8 nếu hạn mức Gemini đủ. |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `CLOUDINARY_FOLDER` | Nơi lưu ảnh đại diện và PDF/ảnh người dùng tải lên (Cloudinary Console → Dashboard → API Keys). Thiếu thì tính năng tải file trả 503. **API Secret là bí mật, chỉ để ở backend.** |
| `USER_STORAGE_QUOTA_MB`, `USER_UPLOAD_MAX_MB` | Dung lượng tối đa mỗi người dùng (mặc định 20) và mỗi lần tải (mặc định 5), tính bằng MB. |
| `KB_MIN_SCORE`, `KB_STRONG_SCORE` | Ngưỡng tra cứu "Kiến thức bổ sung" do admin nhập (mặc định 0,72 và 0,80; đo bằng embedding Gemini thật). Thường không cần đổi. |
| `DOCUMENT_INGEST_ENABLED` | `true` để admin tải PDF mới lên và nạp (cần ổ đĩa bền); `false` tắt hẳn các endpoint này. |
| `WEB_SEARCH_ENABLED` | `true` cho phép bot tìm web (DuckDuckGo) với câu hỏi ngoài quy chế. |

Ví dụ phần `.env` production (điền giá trị thật, không dán lại key mẫu):
```env
ENV=prod
SECRET_KEY=<chuỗi ngẫu nhiên>
DATABASE_URL=postgresql://ctu:<mật khẩu>@<host>:5432/ctu_chatbot
LLM_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY_1=<key>
GEMINI_API_KEY_2=<key>
GOOGLE_CLIENT_ID=<client id>.apps.googleusercontent.com
ADMIN_EMAILS=admin@ctu.edu.vn
CORS_ORIGINS=["https://chatbot.example.edu.vn"]
CHAT_RATE_LIMIT=10/5m,40/1d
CHAT_MAX_CONCURRENT=4
```

### 3.3. Tạo bảng (migration)
```bash
cd ctu-chatbot-be
alembic upgrade head
```
Chạy lại lệnh này **mỗi lần cập nhật phiên bản mới** có migration (nếu quên, backend sẽ báo lỗi kiểu `column ... does not exist`). Bảng checkpoint của LangGraph thì backend tự tạo khi khởi động.

### 3.4. Chạy
```bash
cd ctu-chatbot-be
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```
Kiểm tra: `GET http://<host>:8000/api/v1/health` trả 200.

Nhật ký lần chạy đầu nên có dòng kiểu `RAG sẵn sàng: N Điều ...`. Nếu thấy `Không dựng được RAG` thì kiểm tra key embedding / mạng (chatbot vẫn chạy nhưng trả lời không có ngữ cảnh quy chế).

### 3.5. Chạy nền bằng systemd (Linux, ví dụ)
`/etc/systemd/system/ctu-chatbot.service`:
```ini
[Unit]
Description=CTU Chatbot API
After=network.target postgresql.service

[Service]
WorkingDirectory=/opt/ctu-chatbot/ctu-chatbot-be
ExecStart=/opt/ctu-chatbot/ctu-chatbot-be/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
User=ctu

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now ctu-chatbot
```

### 3.6. Docker (ví dụ, chưa chạy thử)
`ctu-chatbot-be/Dockerfile` (build từ thư mục gốc repo để copy được `vector-docs/`):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY ctu-chatbot-be/requirements.txt ctu-chatbot-be/requirements.txt
RUN pip install --no-cache-dir -r ctu-chatbot-be/requirements.txt
COPY ctu-chatbot-be ctu-chatbot-be
COPY vector-docs/qd3266-clean.md vector-docs/qd3266-clean.md
WORKDIR /app/ctu-chatbot-be
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
```
Chạy kèm 3 volume (mục 1) và biến môi trường từ file `.env`:
```bash
docker build -f ctu-chatbot-be/Dockerfile -t ctu-chatbot-be .
docker run -d --name ctu-chatbot-be --env-file ctu-chatbot-be/.env -p 8000:8000 \
  -v ctu_chroma:/app/ctu-chatbot-be/chroma_db \
  -v ctu_documents:/app/ctu-chatbot-be/data/documents \
  -v ctu_donate:/app/ctu-chatbot-be/data/donate \
  ctu-chatbot-be
```

---

## 4. Reverse proxy (nginx) và HTTPS

Đặt nginx (hoặc Caddy, Cloudflare...) phía trước backend để có HTTPS. Điểm bắt buộc: **tắt buffering cho kênh SSE** (câu trả lời được stream từng đoạn) và cho phép tải PDF lớn.

```nginx
server {
    listen 443 ssl http2;
    server_name api.chatbot.example.edu.vn;
    # ssl_certificate / ssl_certificate_key ...

    client_max_body_size 35m;        # PDF tối đa 30 MB (INGEST_MAX_PDF_MB) + dư

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;         # bắt buộc để stream câu trả lời
        proxy_read_timeout 300s;     # chờ hàng đợi + LLM có thể vài chục giây
    }
}
```
Giới hạn tốc độ của hệ thống tính theo **tài khoản người dùng**, không theo IP, nên không cần cấu hình `X-Forwarded-For` thêm cho việc đó.

---

## 5. Triển khai frontend

Biến môi trường được gắn vào lúc **build** (không đổi được sau khi build):

| Biến | Giá trị |
|---|---|
| `VITE_API_BASE_URL` | Địa chỉ công khai của backend, ví dụ `https://api.chatbot.example.edu.vn` (không có dấu `/` ở cuối). Mặc định là `http://localhost:8000`. |
| `VITE_GOOGLE_CLIENT_ID` | Client ID Google ở 2.2. |
| `VITE_DEV_LOGIN` | **Không đặt** (hoặc khác `true`) ở production. |

```bash
cd ctu-chatbot-fe
npm ci
VITE_API_BASE_URL=https://api.chatbot.example.edu.vn \
VITE_GOOGLE_CLIENT_ID=<client id>.apps.googleusercontent.com \
npm run build
```
Kết quả nằm ở `ctu-chatbot-fe/dist/`. Đưa thư mục này lên hosting tĩnh:
- **Vercel / Netlify:** đã có `vercel.json` (mọi đường dẫn về `index.html`). Đặt hai biến `VITE_*` trong phần Environment Variables của dự án rồi deploy.
- **nginx:** trỏ `root` tới `dist` và bật chuyển đường dẫn về trang chính cho ứng dụng một trang:
  ```nginx
  location / { try_files $uri /index.html; }
  ```

Địa chỉ frontend này phải khớp với `CORS_ORIGINS` (backend) và **Authorized JavaScript origins** (Google).

---

## 6. Giới hạn tốc độ và sức chịu tải

`CHAT_RATE_LIMIT` là giới hạn cho **mỗi người dùng**, hỗ trợ nhiều cửa sổ thời gian cách nhau bằng dấu phẩy: `<số tin>/<khoảng>` với đơn vị `s` (giây), `m` (phút), `h` (giờ), `d` (ngày). Tin chỉ được nhận khi **mọi** cửa sổ còn chỗ.

| Giá trị | Ý nghĩa |
|---|---|
| `10/5m` | 10 tin mỗi 5 phút |
| `10/5m,40/1d` | thêm trần 40 tin mỗi 24 giờ (khuyến nghị: bảo vệ hạn mức ngày của Gemini) |
| `off` | không giới hạn |

Lưu ý:
- Cửa sổ ngày là cửa sổ **trượt 24 giờ**, không phải theo ngày lịch.
- Bộ đếm nằm trong bộ nhớ: **khởi động lại backend thì đếm lại từ đầu**.
- Chào hỏi và tin chửi thề cũng tính vào giới hạn (tuy không tốn request Gemini); câu hỏi gợi ý thì không tính.
- Điểm nghẽn thật thường là số request mỗi ngày (RPD) của Gemini, không phải số request mỗi phút.

---

## 7. Kiểm tra sau khi deploy

- [ ] `GET /api/v1/health` trả 200.
- [ ] Mở trang frontend, đăng nhập bằng Google bằng một email CTU.
- [ ] Đăng nhập bằng email trong `ADMIN_EMAILS` thấy được khu vực quản trị (`/admin`).
- [ ] Hỏi một câu quy chế, câu trả lời hiện dần từng đoạn (nếu hiện một lần cả khối thì kiểm tra `proxy_buffering off`).
- [ ] Gửi thử tin chào ("xin chào") nhận câu trả lời có sẵn, và một tin chửi thề nhận hộp thoại cảnh báo.
- [ ] Trang `/admin/dashboard` hiện số liệu; tab "Phản hồi người dùng" hoạt động.
- [ ] `/api/v1/auth/dev-login` trả **404** (xác nhận `ENV=prod`).
- [ ] (Nếu dùng) tải ảnh QR ở tab ủng hộ, kiểm tra ảnh hiện trong hộp thoại thông tin cá nhân.
- [ ] Khởi động lại backend, dữ liệu (chat, ảnh QR, tài liệu đã nạp) vẫn còn: xác nhận volume hoạt động.

---

## 8. Cập nhật phiên bản mới

1. Lấy code mới (`git pull`).
2. Backend: `pip install -r requirements.txt` → `alembic upgrade head` → khởi động lại dịch vụ.
3. Frontend: build lại (`npm ci && npm run build`) và đưa `dist/` lên hosting.
4. Thay đổi cấu trúc DB cần chạy migration **trước** khi khởi động bản mới.

## 9. Sao lưu và bảo mật

- **Sao lưu:** `pg_dump` database định kỳ; sao lưu 3 thư mục `chroma_db/`, `data/documents/`, `data/donate/`. Kho vector có thể dựng lại từ văn bản nguồn nhưng tốn lượt gọi embedding.
- **Bí mật:** không commit `.env`, key Gemini, `SECRET_KEY`. Nếu lộ key, thu hồi và tạo lại ở Google.
- **Phân quyền:** chỉ đưa email thật sự cần vào `ADMIN_EMAILS`; admin có quyền nạp tài liệu thay đổi nội dung chatbot trả lời.
- **Mạng:** chỉ mở cổng 80/443 ra ngoài; cổng 8000 và Postgres chỉ cho nội bộ.

## 10. Sự cố thường gặp

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| Trình duyệt báo lỗi CORS | `CORS_ORIGINS` thiếu địa chỉ frontend (đúng giao thức và tên miền, không dấu `/` cuối). |
| Đăng nhập Google lỗi `origin_mismatch` | Chưa thêm địa chỉ frontend vào Authorized JavaScript origins. |
| Đăng nhập xong báo email không được phép | Email không thuộc `ALLOWED_EMAIL_DOMAINS` và không có trong `ADMIN_EMAILS`. |
| Lỗi `column ... does not exist` | Chưa chạy `alembic upgrade head`. |
| Câu trả lời hiện một lần thay vì từng đoạn | Proxy đang buffer: `proxy_buffering off`. |
| Chat báo hết hạn mức / "đang bận" liên tục | Hết hạn mức Gemini (xem mục 6 và 2.1); thêm key ở project khác hoặc bật billing. |
| Bot trả lời không dựa trên quy chế, log có `Không dựng được RAG` | Thiếu hoặc sai key embedding, không có `vector-docs/qd3266-clean.md`, hoặc không có mạng. |
| Mất ảnh QR / tài liệu đã nạp sau khi deploy lại | Chưa gắn volume cho `data/` và `chroma_db/`. |
