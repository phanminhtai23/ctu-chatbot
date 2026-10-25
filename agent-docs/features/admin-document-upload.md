# Feature: admin-document-upload

- **Status:** implemented
- **Scope:** FE, BE, Chroma, source-controlled `vector-docs/`
- **Env:** local source editing; production reads committed versions and has a manual Chroma sync action

## Current staged workflow

The admin page `/admin/documents` separates source review from vectorization and shows a persisted, detailed progress flow:

1. **Upload** writes a version to `vector-docs/documents/<timestamp-id>/<original-filename>` and adds a disabled draft node to `vector-docs/routes.json`.
2. **Extract** reports PDF rendering and OCR separately, including page progress, metrics, warnings, and a reviewable OCR preview.
3. **Clean** reports normalization and per-article chunking separately, with cleanup metrics and a reviewable Markdown preview.
4. **Sync version** reports embedding progress and collection details, then promotes the draft route node. Each document route uses its own collection.
5. Commit/push the version directory and `vector-docs/routes.json`. The Docker image includes all of `vector-docs/`.
6. After production deploy, an admin manually presses **Sync catalog vào vector DB**. This rebuilds/updates the committed document collections in persistent Chroma; production does not write to the source tree.

The route canvas shows the classifier, web search, built-in regulation, and document nodes. Selecting a node exposes its route prompt; each router-to-route edge can be disabled. Route prompts and edge changes are saved to `vector-docs/routes.json`, so make them locally and commit/push them. Pending document nodes are visible but cannot receive chat traffic until sync promotes them.

Answers routed to a versioned document cite the matching article and link directly to that version's source PDF; the built-in regulation keeps its page-layout reference viewer.

Production Compose sets `DOCUMENT_CATALOG_EDIT_ENABLED=false`, `DOCUMENT_CATALOG_SYNC_ENABLED=true`, `DOCUMENT_INGEST_ENABLED=false`, and `VECTOR_DOCS_DIR=/vector-docs`. This leaves source edits local while allowing manual indexing after deployment.

**API:** `GET /admin/documents/catalog`, `POST /admin/documents/catalog/jobs`, stage actions under `/admin/documents/catalog/jobs/{slug}/{id}/{extract|clean|sync}`, `POST /admin/documents/catalog/sync`, `GET/PUT /admin/documents/catalog/routes`, and public `GET /documents/catalog/{slug}/{version}/source` for cited PDFs.

**Tests:** `tests/test_catalog.py`, `tests/test_graph_routing.py`, `tests/test_scope.py`, and `tests/test_ingest.py`.

The committed QĐ 3266 source is organized under `vector-docs/documents/qd3266/current/`; previous regulations are kept under their own document folder. Admin uploads use a timestamp-named folder directly under `vector-docs/documents/`, and keep the original PDF filename. See `vector-docs/README.md` for the layout and file roles.

### Historical implementation — 2026-10-18: server-side automatic ingest

The original flow automatically ran the full ingest pipeline and activated the resulting version. It is retained in the legacy `/admin/documents` endpoints and `app/services/ingest/manager.py`; the current UI uses the staged catalog API above.

Gộp cả `admin-document-upload` lẫn `admin-document-vectorization` (cùng một quy trình): admin upload một PDF → hệ thống TỰ
làm lại toàn bộ rồi kiểm thử; chỉ khi đạt mới áp dụng cho chatbot.

**Trang admin** `/admin/documents` (menu "Tài liệu quy định"): thẻ tài liệu đang dùng, vùng kéo thả PDF, luồng 8 bước (vòng tròn
trạng thái, thanh tiến độ, tóm tắt, bấm "Chi tiết" xem số liệu / danh sách dòng / đoạn xem trước), lịch sử các lần nạp. FE hỏi
trạng thái mỗi 1,5 giây khi đang chạy. Code: `ctu-chatbot-fe/src/pages/admin/AdminDocuments.tsx`, `components/admin/IngestFlow.tsx`.

**8 bước** (`app/services/ingest/pipeline.py`):
1. `render` — pypdfium2 (không cần poppler) tách ảnh trang; 2. `ocr` — Gemini (`INGEST_MODEL`), mỗi lần 5 trang; nếu Gemini từ
chối cả nhóm (lọc trích nguyên văn) thì đọc lại từng trang; 3. `normalize` — mã thuần (`normalize.py`, không gọi LLM): bỏ phần
Quyết định ban hành, số trang, dòng đầu/cuối trang lặp, nối câu bị ngắt giữa trang, đưa `Chương`/`Điều N.` về `##`/`###`;
4. `chunk` — mỗi Điều một chunk, số Điều phải liên tục (thiếu thì dừng, báo đúng Điều nào); 5. `embed` — vector hóa vào collection
Chroma RIÊNG của phiên bản (chưa đụng bản đang dùng); 6. `layout` — Gemini khoanh vị trí từng Điều trên ảnh trang (để bấm tham
chiếu mở đúng đoạn PDF); 7. `test` — kho khớp số Điều và đúng số chiều, mỗi Điều tự tìm lại được bằng tiêu đề trong top-5 (cần
≥ 90%), ≥ 50% Điều có vị trí trên trang, so sánh với bản đang dùng (thêm/bỏ/đổi Điều, cảnh báo câu hỏi gợi ý có sẵn bị ảnh hưởng);
8. `activate` — chỉ chạy khi test đạt: ghi `active.json`, đổi collection của retriever đang chạy (KHÔNG cần khởi động lại), xoá
cache layout, dọn phiên bản cũ (giữ bản mới + 1 bản trước).

**An toàn:** bước nào lỗi → dừng, các bước sau "bỏ qua", tài liệu cũ vẫn phục vụ chatbot. Test chưa đạt → trạng thái "bị từ chối".
Một lần nạp tại một thời điểm (409 `INGEST_BUSY`). Trạng thái ghi ở `versions/<id>/job.json` nên xem lại được sau khi tải lại trang;
server khởi động lại giữa chừng thì lần nạp đó hiện "lỗi, bị gián đoạn".

**Dữ liệu:** `ctu-chatbot-be/data/documents/` (gitignore): `active.json` + `versions/<id>/{source.pdf, ocr.txt, clean.md, layout.json,
pages/, job.json}`. Chưa nạp lần nào thì dùng dữ liệu cũ kèm repo (`app/data/qd3266`, `vector-docs/documents/qd3266/current/clean.md`). Khi khởi động,
`build_retriever` đọc `active.json` để dùng đúng collection. Cấu hình: `DOCUMENT_INGEST_ENABLED` (false = tắt; đặt false ở production
nếu chưa muốn cho nạp — brainstorm gốc ghi DEV only), `INGEST_MODEL`, `INGEST_OCR_PAGES_PER_CALL`, `INGEST_CALL_INTERVAL_SECONDS`,
`INGEST_MAX_PDF_MB`, `INGEST_MAX_PAGES`, `INGEST_MIN_RETRIEVAL_PASS`.

**API** (admin): `GET /admin/documents` (đang dùng + lịch sử), `POST /admin/documents?filename=` (body = file PDF, 202 + job),
`GET /admin/documents/jobs/{id}`.

**Chưa làm / lưu ý:** hoàn tác về bản trước (dữ liệu bản trước còn nhưng chưa có nút); system prompt của chatbot vẫn nhắc "QĐ
3266/QĐ-ĐHCT" và các câu hỏi gợi ý có sẵn soạn từ bản cũ — nạp tài liệu khác hẳn thì phải sửa tay; cần `pip install -r
requirements.txt` (thêm `pypdfium2`, `pillow`). Test: `tests/test_ingest.py` (offline, Gemini/embedding giả).

### Đã làm — 2026-10-18: lưu nhiều phiên bản trên server, chuyển qua lại
- Mỗi lần nạp lưu trọn vẹn ở `ctu-chatbot-be/data/documents/versions/<id>/` (PDF gốc `source.pdf`, `ocr.txt`, `clean.md`, `layout.json`, ảnh trang, `job.json`) + một collection Chroma riêng `qd3266-<id>`. Giữ tối đa `INGEST_KEEP_VERSIONS` (10) phiên bản gần nhất; bản đang dùng không bao giờ bị xoá.
- Bản từng qua kiểm thử (và còn đủ dữ liệu) có nút "Dùng bản này"; chatbot đổi ngay không cần restart (đổi collection của retriever + xoá cache layout). Bản bị từ chối kiểm thử không chuyển sang được. Nút "Quay về bản mặc định" đưa về tài liệu kèm repo. Có nút "Tải PDF gốc" cho từng lần nạp.
- API: `POST /admin/documents/versions/{id}/activate`, `POST /admin/documents/versions/default/activate`, `GET /admin/documents/jobs/{id}/source`; `GET /admin/documents` trả thêm `is_active`, `can_activate`, `default_available`. Không chuyển được khi đang có lần nạp chạy (409).
- Sửa lỗi: tên collection từng cắt 12 ký tự đầu của mã (trùng nếu hai lần nạp trong cùng một phút) — nay dùng đủ mã.
- Đã chạy thật với PDF QĐ 3266 (Gemini + embedding thật, 11 phút): 36/36 Điều, truy xuất 100%, 36/36 Điều có vị trí, tự áp dụng. Nội dung chuẩn hóa tự động khác bản chuẩn hóa tay ở 23 Điều (chủ yếu khác biệt nhỏ về cách ngắt dòng/bảng; Điều 19 và 36 khác nhiều nhất).

### Đã làm — 2026-10-18: bước "So sánh thay đổi" trong luồng
Thêm bước 5 `diff` (sau `chunk`, trước `embed`): so từng Điều của PDF mới với tài liệu đang dùng (hoặc bản mặc định nếu chưa nạp lần nào): Điều mới / bị bỏ / đổi nội dung / giữ nguyên. Điều đổi hiện diff theo dòng (đỏ `-` = cũ, xanh `+` = mới, tối đa 40 dòng mỗi Điều). Cảnh báo nếu câu hỏi gợi ý có sẵn dựa vào Điều đã đổi. Bước `test` không còn tự so sánh nữa. Luồng nay có 9 bước.
