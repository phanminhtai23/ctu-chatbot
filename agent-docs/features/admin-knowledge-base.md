# Admin: kiến thức bổ sung (hỏi - đáp) + embedding vào vector DB

## Mục tiêu
Admin nhập thêm cặp câu hỏi - câu trả lời (ký túc xá, giờ thư viện, thủ tục... ngoài quy chế), bấm Embedding để đưa vào vector DB; chatbot tra cứu cùng với văn bản quy chế và trả lời theo đó.

## Đã làm (2026-10-18)
- **Dữ liệu:** bảng `knowledge_entries` (migration `c4e8a1d7f203`): question, answer, `question_key` (băm câu hỏi đã chuẩn hoá, unique: chặn trùng không phân biệt hoa thường/khoảng trắng), `embedded_hash` + `embedded_at`, `created_by`. Trạng thái: `embedded` (đã embedding và nội dung chưa đổi) | `pending` (chưa embedding hoặc đã sửa sau lần embedding gần nhất). Giới hạn: câu hỏi ≤ 500, câu trả lời ≤ 4000 ký tự.
- **Vector DB:** collection riêng `knowledge-qa` trong cùng thư mục ChromaDB (`app/services/rag/knowledge.py`). Vector tạo từ CÂU HỎI (so khớp câu hỏi người dùng với câu hỏi đã nhập chính xác hơn nhúng cả câu trả lời); câu trả lời nằm trong metadata. `CachedQueryEmbedder` (`embeddings.py`) nhớ vector câu hỏi vừa nhúng nên một lượt chat chỉ tốn MỘT lần gọi embedding cho cả quy chế lẫn kiến thức bổ sung.
- **API admin** (`/api/v1/admin/knowledge`, `app/api/v1/admin_knowledge.py`): `GET` (tìm theo câu hỏi/trả lời, lọc trạng thái, kèm `stats` gồm tổng / đã embedding / chờ / `vector_count` thật trong Chroma), `POST` thêm (409 `DUPLICATE_QUESTION`), `PATCH /{id}` sửa (về `pending`), `DELETE /{id}` (gỡ cả vector), `POST /embed` (embedding các mục chờ; `?force=true` = xoá vector cũ rồi nhúng lại TẤT CẢ), `POST /{id}/embed`, `POST /test` (thử tra cứu: top 5 mục + độ giống + có đủ điểm / khớp rõ không). Embedding theo nhóm 16 mục, lưu trạng thái sau từng nhóm; API embedding lỗi thì 503 `EMBEDDING_UNAVAILABLE`, các nhóm xong trước đó vẫn giữ.
- **Chatbot:** `Retriever.retrieve_knowledge` + `graph.py`. Tra cứu theo CÂU HỎI MỚI NHẤT; mục có độ giống ≥ `KB_MIN_SCORE` (0,72), tối đa `KB_TOP_K` (3), được đưa vào prompt thành khối "KIẾN THỨC BỔ SUNG" (dặn LLM ưu tiên dùng, nói rõ là "thông tin bổ sung của hệ thống", không gán cho Điều nào). Có mục ≥ `KB_STRONG_SCORE` (0,80) thì ép tuyến `regulation` (khỏi phân loại / tìm web). Các tuyến khác (tìm web, lạc đề, xã giao) không nhận kiến thức bổ sung. Lỗi tra cứu thì bỏ qua, không làm hỏng lượt chat. Tin nhắn bot lưu thêm `knowledge` (id, câu hỏi, điểm) để gỡ lỗi.
- **Ngưỡng đo bằng Gemini embedding thật:** câu cùng ý 0,80-0,95; cùng chủ đề nhưng khác ý ~0,78 ("KTX có wifi không?" so với mục "KTX khu A có bao nhiêu phòng?"); quy chế/lạc đề 0,59-0,70.
- **Giao diện** `/admin/knowledge` (tab "Kiến thức bổ sung"): 3 ô thống kê, cảnh báo khi số vector lệch số mục "đã embedding", form thêm/sửa, "Thử tra cứu", danh sách có tìm kiếm + lọc, nút "Embedding N mục chờ", "Embedding lại tất cả" (có hỏi xác nhận), xoá có xác nhận.
- Đã thử thật: nhập 2 mục, embedding bằng Gemini, thử tra cứu (0,915 vs 0,644), hỏi chatbot thật "KTX khu A có mấy phòng vậy bạn?" → trả lời "Có 400 phòng... (theo thông tin bổ sung của hệ thống...)"; giao diện chụp bằng Chrome headless. Test: `tests/test_knowledge.py` (20 test).

## Chưa làm
- Mục chưa có chip "tham chiếu" riêng ở giao diện chat (chỉ có Điều của quy chế): bot nói bằng lời "theo thông tin bổ sung".
- Mỗi mục một câu hỏi: chưa có nhiều cách diễn đạt cho một câu trả lời (thêm mục khác với câu hỏi khác).
- Mục kiến thức chưa có nhập hàng loạt (CSV) hay phân loại/gắn thẻ.
