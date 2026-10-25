# Feature: admin-document-vectorization

- **Status:** implemented
- **Scope:** BE, Chroma, source-controlled `vector-docs/`

## What

Each committed document version has a clean Markdown source, a route node, and its own Chroma collection. Local admin Sync indexes a reviewed version; production admin Sync re-indexes the committed route catalog after deploy.

## Scope chi tiết

- BE: re-index only when the clean-text SHA-256 differs from the collection metadata.
- DB: persistent Chroma collections in `chroma_data`, one collection per document version.

## Notes

- Related staged upload/review steps are documented in `admin-document-upload.md`.
- Embeddings use the configured Gemini embedding model and are created only after an explicit Sync action.

### Historical implementation — 2026-10-10: chuẩn hóa text nguồn cho vector hóa

- `vector-docs/documents/qd3266/current/ocr.txt`: text OCR thô từ PDF gốc (chưa xử lý, giữ lại làm bản gốc đối chiếu).
- `vector-docs/documents/qd3266/current/clean.md`: bản đã chuẩn hóa, dùng file này để vector hóa (không dùng bản OCR thô). Đã xử lý:
  - Bỏ phần thủ tục ban hành (Quyết định, "Căn cứ...", chữ ký Hiệu trưởng) — chỉ giữ nội dung Quy định (Chương I–IV, Điều 1–36).
  - Bỏ `--- Trang N ---`, số trang rời, và các đoạn bị OCR lặp do ngắt trang; nối lại các câu bị cắt giữa chừng khi sang trang.
  - Định dạng lại 5 bảng (Điều 5, 19, 22, 30, 34) và công thức ĐTBCHK (Điều 24) thành Markdown table / LaTeX rõ ràng.
  - Đã đối chiếu trực tiếp với PDF gốc (`vector-docs/documents/qd3266/current/source.pdf`) cho 3 bảng/công thức phức tạp nhất (Điều 19, 24, 30) — khớp 100%, không phải đoán.
  - Sửa 1 lỗi chính tả OCR: "phân bố" → "phân bổ" (Điều 19).
- Việc còn lại: quyết định chiến lược chunk (theo Điều hay theo đoạn) và embedding model trước khi code pipeline vector hóa thật.

### Đã làm — 2026-10-11: pipeline vector hóa + ChromaDB (BE)

- **Quyết định:** vector DB = **ChromaDB nhúng** (`PersistentClient`, không cần server), lưu ở `ctu-chatbot-be/chroma_db/` (đã gitignore). Embedding = `models/gemini-embedding-2`, **768 chiều** (`EMBEDDING_DIM`), key lấy từ `EMBEDDING_MODEL_API_KEY` (rỗng thì dùng `GEMINI_API_KEY_1`).
- **Chunk theo Điều:** mỗi Điều là 1 chunk (36 chunk, lớn nhất ~3.400 ký tự), kèm metadata `article`, `title`, `chapter`. Bảng và công thức nằm nguyên trong chunk của Điều đó. Code: `app/services/rag/chunker.py`.
- **Lưu ý khi dùng `gemini-embedding-2`:** truyền list chuỗi vào `embed_content` sẽ chỉ trả về MỘT vector gộp; phải bọc từng text trong `types.Content(parts=[types.Part(text=...)])` để mỗi text một vector. Không dùng `task_type`; chỉ dẫn nằm trong nội dung (`task: question answering | query: ...`, `title: none | text: ...`).
- **Tự nạp:** `app/main.py` gọi `build_retriever()` lúc khởi động → `ensure_index()` so sánh SHA-256 của `documents/qd3266/current/clean.md` với giá trị lưu trong metadata collection; đổi file thì tự vector hóa lại, không đổi thì bỏ qua. Lỗi (thiếu key, mất mạng) chỉ log, chatbot vẫn chạy nhưng không có ngữ cảnh.
- **Nguồn:** mặc định `vector-docs/documents/qd3266/current/clean.md` (đặt `RAG_SOURCE_PATH` để đổi). Các file nguồn và phiên bản được sắp theo từng thư mục tài liệu.
- **Truy xuất** (`Retriever` trong `app/services/rag/store.py`): (1) Điều nêu thẳng trong câu hỏi ("Điều 24") lấy bằng id; (2) top-k (`RAG_TOP_K`=5) giống nhất theo cosine; (3) thêm tối đa 2 Điều có cụm từ trong tiêu đề trùng câu hỏi (cứu "học phí bao nhiêu" mà embedding xếp Điều 10 ngoài top 5). Câu hỏi nối tiếp được tra cùng tin người dùng ngay trước đó.
- **Test:** `tests/test_rag_offline.py` (không cần mạng), `tests/test_rag_live.py` (`pytest -m live`: embedding Gemini thật, kết quả 65/65 câu hỏi truy xuất đúng Điều trong top-5).
- Còn lại: endpoint admin trigger re-index (hiện chỉ tự chạy khi khởi động), nhiều worker cùng ghi Chroma chưa an toàn (chạy 1 worker).

### 2026-10-18: đã gộp vào `admin-document-upload`
Endpoint/UI re-index khi tài liệu đổi chính là quy trình nạp PDF mới của `admin-document-upload` (OCR → chuẩn hóa → chunk theo Điều →
embedding → test → áp dụng). Xem file đó.
