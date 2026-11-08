# Hướng dẫn triển khai (deploy) CTU Chatbot

Quy trình production dùng GitHub Actions để kiểm tra code, build image `linux/arm64`, đẩy lên GitHub Container Registry (GHCR), rồi SSH vào một máy chủ ARM64 và cập nhật Docker Compose.

| Phần | Công nghệ | Chạy ở đâu |
|---|---|---|
| Backend (BE) | FastAPI + LangGraph + ChromaDB nhúng | Docker container trên server ARM64 |
| Database | PostgreSQL 16 | Docker container trên cùng server, chỉ trong mạng nội bộ |
| Frontend (FE) | React + Vite, Nginx Alpine | Docker container trên cùng server, cổng `8080` |

Ngoài ra cần: **API key Gemini** (LLM + embedding) và **OAuth Client ID của Google** (đăng nhập).

FE container phục vụ SPA và proxy `/api/` tới BE; sau này Nginx trên host chỉ cần reverse-proxy tới `127.0.0.1:8080`. Workflow deploy khi push vào `main`; PR chỉ chạy kiểm tra.

---

## 1. Điều cần biết trước khi deploy

1. **Chỉ chạy MỘT worker backend** (`uvicorn ... --workers 1`, không dùng `--workers N`, không chạy nhiều bản sao cùng lúc). Hàng đợi lượt chat, bộ đếm giới hạn tốc độ, tiến trình nạp tài liệu và ChromaDB nhúng đều nằm trong bộ nhớ / ổ đĩa của một process. Chạy nhiều worker thì mỗi worker đếm riêng và có thể hỏng dữ liệu vector.
2. **Cần ổ đĩa bền (Docker named volumes)**, nếu không dữ liệu sẽ mất khi xóa container:
   - `chroma_data` — kho vector ChromaDB.
   - `document_data` — dữ liệu của pipeline upload cũ (`DOCUMENT_INGEST_ENABLED=false` trong production). Workflow catalog hiện tại lưu PDF/OCR/clean text trong source `vector-docs/documents/` và được đóng gói vào image khi deploy.
   - `donate_data` — ảnh QR ủng hộ.
   - `postgres_data` — database và lịch sử chat.
   - (`chroma_db/` cũng chứa vector của "Kiến thức bổ sung" do admin nhập; nội dung các mục nằm trong Postgres. Mất `chroma_db/` thì vào trang quản trị bấm "Embedding lại tất cả".)
3. **Lịch sử chat nằm trong Postgres** (bảng checkpoint của LangGraph, tự tạo khi khởi động) nên phải sao lưu database.
4. Backend image đóng gói toàn bộ `vector-docs/`, gồm `routes.json` và các tài liệu/version đã commit trong `documents/`.
5. Lần khởi động đầu tiên, backend gọi API embedding để nhúng từng Điều của văn bản mặc định. Với tài liệu mới, sau khi deploy cần admin bấm **Sync catalog vào vector DB**; Chroma lưu ở `chroma_data` và được giữ qua các lần deploy.

---

## 2. Chuẩn bị bên ngoài

### 2.1. API key Gemini
- Lấy key ở Google AI Studio. Điền `GEMINI_API_KEY` (tuỳ chọn) và/hoặc `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, ...; không giới hạn số thứ tự key. Khi hết hạn mức, key được tạm nghỉ theo `retryDelay` Gemini trả về hoặc theo loại quota (giây/phút/giờ/ngày), rồi tự xoay sang key kế tiếp.
- Hạn mức Gemini tính theo **project**, không theo key: nhiều key cùng một project vẫn dùng chung một hạn mức. Muốn cộng dồn hạn mức, tạo mỗi key ở một project riêng.
- Ước tính sức chịu tải (chưa đo thực tế), với `gemini-3.5-flash-lite` mức 15 RPM / 500 RPD mỗi project và 6 project: tối đa khoảng 60 lượt hỏi/phút và khoảng 2.000 lượt/ngày. Cùng một project thì chia cho số key. Bật billing để tăng hạn mức nhiều lần.

### 2.2. Đăng nhập Google
1. Google Cloud Console → APIs & Services → Credentials → tạo **OAuth client ID** loại **Web application**.
2. Mục **Authorized JavaScript origins**: thêm `https://ctu-chatbot.io.vn` (và `http://ctu-chatbot.io.vn` nếu cần kiểm tra trước khi bật HTTPS).
3. Lấy **Client ID**, dùng cho cả backend (`GOOGLE_CLIENT_ID`) và frontend (`VITE_GOOGLE_CLIENT_ID`).

### 2.3. Cloudinary (lưu file người dùng)
- Tạo tài khoản Cloudinary (gói miễn phí đủ để thử), lấy Cloud name, API Key, API Secret ở Dashboard.
- Ảnh đại diện lưu công khai; PDF/ảnh tải lên lưu dạng `authenticated` (URL có chữ ký). Không cần cấu hình gì thêm trên Cloudinary.
- Ảnh đại diện mặc định ngẫu nhiên lấy từ DiceBear (`api.dicebear.com`), máy người dùng phải truy cập được tên miền này.

### 2.4. PostgreSQL
Trong production của hướng dẫn này, PostgreSQL chạy cùng stack Docker Compose và chỉ backend truy cập được; không mở cổng database ra Internet.
- Tạo database và user riêng, ví dụ `ctu_chatbot`.
- Chuỗi kết nối dạng `postgresql://USER:PASSWORD@HOST:5432/ctu_chatbot` (dịch vụ ngoài thường yêu cầu thêm `?sslmode=require`).
- Chạy thử cục bộ bằng `docker compose up -d db` (xem `docker-compose.yml`, cổng 5433). **Đừng dùng mật khẩu mẫu trong file đó ở production.**

---

## 3. CI/CD: triển khai tự động lên server ARM64

### 3.1. Chuẩn bị server
Dùng Ubuntu/Debian 64-bit trên ARM (`aarch64`/`arm64`), cài Docker Engine cùng Docker Compose v2 và `curl`. Server hiện có source tại `/home/opc/projects/ctu-chatbot`; workflow dùng thư mục này làm thư mục deploy. User SSH (thường là `opc`) cần quyền ghi thư mục đó và quyền chạy Docker (thường bằng cách thêm vào group `docker`). Database chạy trong Compose, không cần cài riêng và không publish cổng `5432`.

### 3.1.1. Trỏ domain
Trong trang quản lý DNS của nhà cung cấp domain, tạo:

| Type | Name | Value |
|---|---|---|
| `A` | `@` | Public IPv4 của server |
| `CNAME` | `www` | `ctu-chatbot.io.vn` (tuỳ chọn) |

Nếu server có IPv6 và đã cấu hình firewall/IPv6 đầy đủ, có thể thêm bản ghi `AAAA` tương ứng. Không tạo `AAAA` nếu server chưa nhận kết nối IPv6. Chờ DNS cập nhật rồi kiểm tra `ctu-chatbot.io.vn` phân giải về IP server.

```bash
cd /home/opc/projects/ctu-chatbot
nano ctu-chatbot-be/.env
chmod 600 ctu-chatbot-be/.env
```

Kiểm tra user SSH có quyền ghi file `docker-compose.prod.yml` trong thư mục trên và chạy Docker. File `.env` production đã có tại `ctu-chatbot-be/.env`; workflow kiểm tra và dùng đúng file này. **Không commit hoặc gửi file này lên GitHub**.

### 3.2. Cấu hình GitHub Actions
Trong repository → **Settings → Secrets and variables → Actions**, khai báo:

| Loại | Tên | Giá trị |
|---|---|---|
| Variable | `VITE_GOOGLE_CLIENT_ID` | OAuth Web Client ID để build FE |
| Secret | `DEPLOY_SSH_HOST` | IP hoặc hostname server |
| Secret | `DEPLOY_SSH_USER` | User SSH deploy |
| Secret | `DEPLOY_SSH_PORT` | Cổng SSH; bỏ trống dùng `22` |
| Secret | `DEPLOY_SSH_PRIVATE_KEY` | Private key tương ứng public key đã cài trên server |
| Secret | `DEPLOY_SSH_KNOWN_HOSTS` | Host key đã xác minh, định dạng `known_hosts` |

Lấy host key bằng `ssh-keyscan -p <port> <host>` và xác minh fingerprint qua kênh tin cậy trước khi lưu; workflow giữ bật xác minh host key. GitHub Actions tự cấp `GITHUB_TOKEN` để publish images.

Các thông tin kết nối server được lưu dưới dạng **Secrets** để GitHub che giá trị trong log và giới hạn việc đọc. `VITE_GOOGLE_CLIENT_ID` là public client ID được nhúng vào frontend lúc build, nên để ở Variables là phù hợp; không đặt API key Gemini hay bí mật backend ở Variables.

Đặt packages của GHCR ở chế độ **Public** để server pull image không cần credential. Nếu muốn package private, đăng nhập GHCR trên server một lần bằng PAT có `read:packages`; không truyền PAT trong workflow.

> Secret hóa IP chỉ giúp không phơi bày cấu hình trong repo/log; không phải biện pháp chống DDoS. Nếu server có public IP thì IP có thể bị tìm ra qua DNS, lịch sử DNS hoặc các nguồn khác. Dùng Cloudflare/proxy chống DDoS cho web, chỉ mở cổng 80/443 cho proxy, giới hạn SSH theo IP/VPN nếu làm được, và không mở port backend/Postgres. Không allowlist IP của GitHub-hosted runner vì dải IP thay đổi rộng.

### 3.3. Cấu hình `.env` trên server
Đảm bảo `/home/opc/projects/ctu-chatbot/ctu-chatbot-be/.env` có các biến tối thiểu sau:

```env
ENV=prod
SECRET_KEY=<chuỗi-ngẫu-nhiên-dài>
POSTGRES_USER=ctu
POSTGRES_PASSWORD=<mật-khẩu-mạnh>
POSTGRES_DB=ctu_chatbot
IMAGE_OWNER=phanminhtai23
IMAGE_NAME=ctu-chatbot
DATABASE_URL=postgresql://ctu:<mật-khẩu-url-encoded>@db:5432/ctu_chatbot
LLM_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY_1=<key>
GEMINI_API_KEY_2=<key-khác-nếu-có>
GOOGLE_CLIENT_ID=<client-id>.apps.googleusercontent.com
ADMIN_EMAILS=admin@ctu.edu.vn
ALLOWED_EMAIL_DOMAINS=["ctu.edu.vn","edu.ctu.vn"]
CHAT_RATE_LIMIT=10/5m,40/1d
CHAT_MAX_CONCURRENT=4
```

Đặt `IMAGE_OWNER` và `IMAGE_NAME` đúng owner/repository GHCR (giá trị trên đúng cho repo này); workflow sẽ truyền tag commit cụ thể khi deploy. Password trong `DATABASE_URL` phải percent-encode nếu có ký tự đặc biệt. Tạo `SECRET_KEY` bằng `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Có thể thêm `GEMINI_API_KEY_3`, `_4`, ... không giới hạn số thứ tự. Thêm Cloudinary variables nếu bật upload ảnh/PDF.

### 3.4. Chạy lần đầu và cập nhật
- Pull/merge vào `main` chạy lint/build FE và test BE offline (không gọi Gemini thật, tránh tốn quota). Chỉ khi kiểm tra pass, Actions build image ARM64 theo commit SHA, publish lên GHCR, gửi Compose manifest qua SSH, pull image và khởi động stack.
- Migration Alembic tự chạy khi BE container khởi động; bảng checkpoint LangGraph được tạo khi app khởi động.
- Deploy đóng gói nội dung Git trong `vector-docs/` vào image nhưng **không tự vector hóa tài liệu mới**. Sau deploy, admin vào `/admin/documents` và bấm **Sync catalog vào vector DB**; nút này chỉ đọc các `clean.md` đã commit và cập nhật Chroma.
- Chạy thủ công tại **Actions → CI and ARM64 deployment → Run workflow** trên branch `main`.
- Sau khi cấu hình DNS và Nginx host theo mục 5, trang sẽ ở `https://ctu-chatbot.io.vn`; API cũng dùng cùng origin qua proxy `/api/`. Domain này phải có trong Authorized JavaScript origins của Google OAuth client.

Lệnh vận hành trên server:
```bash
cd /home/opc/projects/ctu-chatbot
docker compose --env-file ctu-chatbot-be/.env -f docker-compose.prod.yml ps
docker compose --env-file ctu-chatbot-be/.env -f docker-compose.prod.yml logs -f backend
docker compose --env-file ctu-chatbot-be/.env -f docker-compose.prod.yml pull
docker compose --env-file ctu-chatbot-be/.env -f docker-compose.prod.yml up -d
```

---

## 4. Cấu hình backend

Các biến backend nằm trong `/home/opc/projects/ctu-chatbot/ctu-chatbot-be/.env` trên server. **Không commit file này.** Các biến production quan trọng:

| Biến | Ghi chú |
|---|---|
| `ENV` | Đặt **`prod`** (khác `dev`). Khi đó endpoint `/auth/dev-login` (đăng nhập không cần Google) bị tắt. |
| `SECRET_KEY` | **Bắt buộc đổi** thành chuỗi ngẫu nhiên dài: `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Đổi key này sẽ làm mọi người phải đăng nhập lại. |
| `DATABASE_URL` | Kết nối Postgres trong Compose qua hostname `db`, ví dụ `postgresql://ctu:<password>@db:5432/ctu_chatbot`. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Tạo role/database trong Postgres container ở lần chạy đầu. |
| `GEMINI_API_KEY`, `GEMINI_API_KEY_N` | Key Gemini; `N` là số thứ tự dương bất kỳ, không giới hạn. Cần ít nhất 1 key. |
| `LLM_MODEL` | Mặc định `gemini-3.5-flash-lite`. |
| `GOOGLE_CLIENT_ID` | Client ID ở 2.2. Để trống thì tắt đăng nhập Google. |
| `ADMIN_EMAILS` | Email quản trị viên, cách nhau bằng dấu phẩy. Đăng nhập bằng email này là có quyền admin (kể cả ngoài tên miền được phép). |
| `ALLOWED_EMAIL_DOMAINS` | Danh sách JSON, mặc định `["ctu.edu.vn","edu.ctu.vn"]`. Email sinh viên thật là `@student.ctu.edu.vn` nên khớp `ctu.edu.vn` (subdomain được chấp nhận). **Không đặt `[]` ở production** (cho mọi email đăng nhập). |
| `CORS_ORIGINS` | FE và API cùng origin qua Nginx nên thường không cần đổi. Nếu tách domain, khai báo origin FE dạng JSON. |
| `CHAT_RATE_LIMIT` | Giới hạn mỗi người dùng. Khuyến nghị `10/5m,40/1d` (xem mục 7). |
| `CHAT_MAX_CONCURRENT` | Số lượt chat chạy đồng thời, mặc định 4; tăng lên 8 nếu hạn mức Gemini đủ. |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `CLOUDINARY_FOLDER` | Nơi lưu ảnh đại diện và PDF/ảnh người dùng tải lên (Cloudinary Console → Dashboard → API Keys). Thiếu thì tính năng tải file trả 503. **API Secret là bí mật, chỉ để ở backend.** |
| `USER_STORAGE_QUOTA_MB`, `USER_UPLOAD_MAX_MB` | Dung lượng tối đa mỗi người dùng (mặc định 20) và mỗi lần tải (mặc định 5), tính bằng MB. |
| `KB_MIN_SCORE`, `KB_STRONG_SCORE` | Ngưỡng tra cứu "Kiến thức bổ sung" do admin nhập (mặc định 0,72 và 0,80; đo bằng embedding Gemini thật). Thường không cần đổi. |
| `VECTOR_DOCS_DIR` | Compose production đặt `/vector-docs`; đây là thư mục chỉ đọc được đóng gói từ source Git. |
| `DOCUMENT_INGEST_ENABLED` | Compose production đặt `false` để tắt upload pipeline cũ lưu trong volume runtime. |
| `DOCUMENT_CATALOG_EDIT_ENABLED` | Compose production đặt `false`; upload PDF và sửa route phải làm ở local, sau đó commit/push. |
| `DOCUMENT_CATALOG_SYNC_ENABLED` | Compose production đặt `true` để admin có thể sync catalog đã deploy vào Chroma. |
| `WEB_SEARCH_ENABLED` | `true` cho phép bot tìm web (DuckDuckGo) với câu hỏi ngoài quy chế. |

Ví dụ phần `.env` production (điền giá trị thật, không dán lại key mẫu):
```env
ENV=prod
SECRET_KEY=<chuỗi ngẫu nhiên>
POSTGRES_USER=ctu
POSTGRES_PASSWORD=<mật-khẩu-mạnh>
POSTGRES_DB=ctu_chatbot
DATABASE_URL=postgresql://ctu:<mật-khẩu-url-encoded>@db:5432/ctu_chatbot
LLM_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY_1=<key>
GEMINI_API_KEY_2=<key>
GOOGLE_CLIENT_ID=<client id>.apps.googleusercontent.com
ADMIN_EMAILS=admin@ctu.edu.vn
CHAT_RATE_LIMIT=10/5m,40/1d
CHAT_MAX_CONCURRENT=4
```


## 5. Nginx trên host và HTTPS (bước làm sau)

Trong stack hiện tại, Nginx bên trong FE container phục vụ SPA, proxy `/api/` tới BE và đã tắt buffering cho SSE, đặt timeout 600 giây và giới hạn upload 40 MB. Khi cài Nginx trên host để gắn domain/HTTPS, reverse-proxy toàn bộ request về FE container; không proxy trực tiếp sang BE:

```nginx
server {
    listen 80;
    server_name ctu-chatbot.io.vn www.ctu-chatbot.io.vn;
    client_max_body_size 40m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 600s;
    }
}
```
Port mapping đã bind `127.0.0.1:8080:80` để FE chỉ được truy cập từ máy chủ. Deploy thay đổi này, cài Nginx host rồi kiểm tra HTTP. Cấp TLS bằng Certbot (ví dụ Ubuntu: `sudo certbot --nginx -d ctu-chatbot.io.vn -d www.ctu-chatbot.io.vn`); sau khi xác nhận HTTPS hoạt động, có thể bật chuyển hướng HTTP → HTTPS. Chỉ mở cổng 80/443 công khai. Cập nhật Authorized JavaScript origins trong Google Cloud thành `https://ctu-chatbot.io.vn`; CORS không cần chỉnh vì trình duyệt gọi API cùng origin.

---

## 6. Frontend

FE được build thành image ARM64 trong CI. `VITE_API_BASE_URL` để rỗng để request dùng cùng origin; Nginx trong container chuyển `/api/` sang backend. Actions cần repository variable:

| Biến | Giá trị |
|---|---|
| `VITE_GOOGLE_CLIENT_ID` | Client ID Google ở mục 2.2; thay đổi biến này cần chạy deploy/build lại. |

FE và BE được deploy đồng bộ từ cùng một commit; không deploy FE tĩnh riêng cho stack Docker này.

---

## 7. Giới hạn tốc độ và sức chịu tải

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

## 8. Kiểm tra sau khi deploy

- [ ] `https://ctu-chatbot.io.vn/api/v1/health` trả 200 sau khi DNS, Nginx và TLS đã cấu hình.
- [ ] Mở trang frontend, đăng nhập bằng Google bằng một email CTU.
- [ ] Đăng nhập bằng email trong `ADMIN_EMAILS` thấy được khu vực quản trị (`/admin`).
- [ ] Hỏi một câu quy chế, câu trả lời hiện dần từng đoạn (nếu hiện một lần cả khối thì kiểm tra `proxy_buffering off`).
- [ ] Gửi thử tin chào ("xin chào") nhận câu trả lời có sẵn, và một tin chửi thề nhận hộp thoại cảnh báo.
- [ ] Trang `/admin/dashboard` hiện số liệu; tab "Phản hồi người dùng" hoạt động.
- [ ] `/api/v1/auth/dev-login` trả **404** (xác nhận `ENV=prod`).
- [ ] Sau khi có version mới trong `vector-docs`, vào `/admin/documents`, kiểm tra node tài liệu và bấm **Sync catalog vào vector DB**; hỏi thử nội dung của tài liệu mới.
- [ ] (Nếu dùng) tải ảnh QR ở tab ủng hộ, kiểm tra ảnh hiện trong hộp thoại thông tin cá nhân.
- [ ] Khởi động lại stack bằng `docker compose ... up -d`; lịch sử chat, ChromaDB, ảnh QR và tài liệu đã nạp vẫn còn.

---

## 9. Cập nhật phiên bản mới

Quy trình tài liệu mới:
1. Trên môi trường local có quyền sửa catalog, vào `/admin/documents` và upload PDF. Hệ thống giữ tên file gốc trong `vector-docs/documents/<YYYYMMDDHHMMSS-xxxxxx>/`, rồi hiển thị riêng tiến độ render, OCR, chuẩn hóa, chunk theo Điều, embedding và lưu route. Review OCR sau **Extract** và clean Markdown sau **Clean** trước khi tiếp tục.
2. **Sync version này vào vector DB** tạo embedding và đánh dấu route trong catalog local. Đây là thao tác có ghi vào Chroma đang cấu hình ở môi trường chạy; nếu chỉ kiểm tra nội dung thì dừng sau Clean. Route mới chỉ phục vụ chat sau khi đã Sync.
3. Commit/push thư mục timestamp và `vector-docs/routes.json`. Giữ các version cũ, không xóa nếu chưa chủ động dọn.
4. GitHub Actions build/deploy image từ commit. Sau deploy, đăng nhập admin trên production và bấm **Sync catalog vào vector DB** để cập nhật Chroma production từ các route/tài liệu đã commit. Thao tác production này không sửa source repo.

Push/merge commit đã kiểm tra vào `main`; GitHub Actions tự build và deploy. Workflow pin tag theo commit SHA và giữ tag `latest`. Nếu deployment lỗi, xem **Actions → workflow run** và logs service bằng lệnh ở mục 3.4. Migration chạy tự động trước khi backend bắt đầu phục vụ.

## 10. Sao lưu và bảo mật

- **Sao lưu:** Postgres và các named volumes `postgres_data`, `chroma_data`, `document_data`, `donate_data` cần nằm trên ổ đĩa bền; backup định kỳ và lưu bản sao ngoài server. Các version tài liệu nguồn được bảo vệ bằng Git; Chroma có thể dựng lại bằng nút sync sau khi khôi phục `vector-docs/`. Ví dụ dump database: `docker compose --env-file ctu-chatbot-be/.env -f docker-compose.prod.yml exec -T db pg_dump -U ctu ctu_chatbot > ctu_chatbot.sql`.
- Mất `chroma_data` thì phải dựng lại vector hoặc vào trang quản trị chọn "Embedding lại tất cả"; quá trình này tốn quota Gemini.
- **Bí mật:** không commit `.env`, key Gemini, `SECRET_KEY`. Nếu lộ key, thu hồi và tạo lại ở Google.
- **Phân quyền:** chỉ đưa email thật sự cần vào `ADMIN_EMAILS`; admin có quyền nạp tài liệu thay đổi nội dung chatbot trả lời.
- **Mạng:** trước khi có Nginx host, chỉ mở SSH và cổng 8080 cần thiết; sau khi cấu hình Nginx/TLS thì chỉ mở 80/443. BE và Postgres không publish host port.

## 11. Sự cố thường gặp

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| Trình duyệt báo lỗi CORS | FE và API phải cùng origin qua FE proxy; nếu tách domain thì thêm origin FE vào `CORS_ORIGINS`. |
| Đăng nhập Google lỗi `origin_mismatch` | Chưa thêm địa chỉ frontend vào Authorized JavaScript origins. |
| Đăng nhập xong báo email không được phép | Email không thuộc `ALLOWED_EMAIL_DOMAINS` và không có trong `ADMIN_EMAILS`. |
| Lỗi `column ... does not exist` | Xem log backend; migration Alembic chạy khi container khởi động. |
| Câu trả lời hiện một lần thay vì từng đoạn | Proxy đang buffer: `proxy_buffering off`. |
| Chat báo hết hạn mức / "đang bận" liên tục | Hết hạn mức Gemini (xem mục 7 và 2.1); thêm key ở project khác hoặc bật billing. |
| Bot trả lời không dựa trên quy chế, log có `Không dựng được RAG` | Thiếu hoặc sai key embedding, không có `vector-docs/documents/qd3266/current/clean.md`, hoặc không có mạng. |
| Mất ảnh QR / tài liệu đã nạp sau khi deploy lại | Kiểm tra named volumes và việc backup/restore. |
