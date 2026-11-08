# Feature: chatbot-academic-qa

- **Status:** in-progress (FE + BE + DB: hội thoại, streaming, LangGraph, Gemini, checkpoint Postgres xong; RAG theo Điều, rate limit 10 tin/5 phút, tham chiếu bấm để xem PDF tô sáng xong; CHƯA có upload ảnh/PDF)
- **Scope:** FE, BE, DB

## What

Chatbot chính: user hỏi về quy chế công tác học vụ (tính điểm, tín chỉ, quy định...). User có thể upload ảnh/PDF để bổ sung thông tin cho câu hỏi. Có rate limit. Trả lời kèm thông tin trích dẫn/tham chiếu nguồn (info referral).

## Scope chi tiết

- FE: khung chat, upload file (img/pdf), hiển thị nguồn tham chiếu kèm câu trả lời.
- BE: endpoint chat (FastAPI), orchestration qua LangGraph gọi Gemini, xử lý file upload, rate limiting.
- DB: lưu lịch sử conversation, (có thể) lưu metadata file upload.

## Notes

- Phụ thuộc vào `admin-document-vectorization` / `admin-document-upload` để có vector DB chứa nội dung quy chế.
- Rate limit: chưa định nghĩa con số cụ thể — cần quyết định trước khi code.
- "Info referral": cần định nghĩa rõ format trả về (trích đoạn quy chế, số điều/khoản...).

## Đã làm (BE + DB) — 2026-10-04

- **LangGraph** (`app/services/chat/graph.py`): đồ thị 1 node `generate` (prompt hệ thống + `chat_history_window` tin gần nhất → Gemini), biên dịch với **checkpointer Postgres** (`PostgresSaver` + `ConnectionPool` dựng ở `lifespan` trong `app/main.py`, tự `setup()` tạo bảng `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`).
- **Lịch sử chat nằm trong checkpoint**, `thread_id = id cuộc trò chuyện`. Bảng `conversations` (Alembic) chỉ giữ chủ sở hữu, tiêu đề (cắt 60 ký tự từ câu đầu tiên), thời gian. Đã kiểm chứng thật: khởi động lại server vẫn nhớ nội dung các lượt trước.
- **Alembic bỏ qua** các bảng `checkpoint*` (`include_object` trong `alembic/env.py`) để autogenerate không đề xuất xoá chúng.
- **Gemini nhiều key** (`app/services/llm/`): đọc `GEMINI_API_KEY` và/hoặc `GEMINI_API_KEY_N` (N không giới hạn), model từ `LLM_MODEL`. Dùng một key cho tới khi gặp 429 thì cho key đó nghỉ theo `retryDelay` Gemini báo; nếu thiếu thì dựa vào metric (mặc định 60 giây cho phút, 1 giờ cho giờ, đến nửa đêm Pacific cho ngày; metric khác dùng `LLM_KEY_COOLDOWN_SECONDS`=60s), rồi chuyển key tiếp theo. Key sai/bị thu hồi: bỏ qua 1 giờ. Lỗi khác (500, nội dung bị chặn...) KHÔNG đổi key. Mọi key đều nghỉ → `503 LLM_RATE_LIMITED` + `Retry-After`; chưa có key → `503 LLM_NOT_CONFIGURED`; lỗi khác → `502 LLM_ERROR`.
- LLM lỗi thì tin của người dùng bị gỡ khỏi checkpoint (không để lại tin mồ côi, gửi lại không bị trùng).

### API (cần đăng nhập, mọi cuộc trò chuyện chỉ chủ sở hữu thấy — người khác nhận 404)

| Method | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/api/v1/conversations` | Tạo cuộc trò chuyện trống (201) |
| GET | `/api/v1/conversations` | Danh sách, hoạt động gần nhất trước |
| GET | `/api/v1/conversations/{id}` | Chi tiết + toàn bộ tin nhắn (đọc từ checkpoint) |
| PATCH | `/api/v1/conversations/{id}` | Đổi tên: body `{title}` (1–200 ký tự, khoảng trắng thừa được gọn lại) |
| POST | `/api/v1/conversations/{id}/messages` | Body `{content}` (1–4000 ký tự) → `{user_message, assistant_message, conversation}` (không stream) |
| POST | `/api/v1/conversations/{id}/messages/stream` | Như trên nhưng trả **Server-Sent Events** (xem dưới) — FE dùng endpoint này |
| DELETE | `/api/v1/conversations/{id}` | Xoá cuộc trò chuyện và lịch sử trong checkpoint (204) |

- Mỗi tin nhắn: `{id, role: "user"|"assistant", content, created_at, duration_seconds}`; `duration_seconds` chỉ có ở tin của bot (thời gian chờ chatbot trả lời, làm tròn 0,1s, do server đo và lưu cùng tin nhắn trong checkpoint nên mở lại cuộc trò chuyện vẫn hiện). `id` là id tin nhắn trong LangGraph — dùng làm `message_id` khi gửi feedback (`user-feedback`).

### Streaming (SSE)

`POST /conversations/{id}/messages/stream` — kiểm tra quyền sở hữu và nội dung TRƯỚC khi bắt đầu stream (lỗi đó vẫn là HTTP 404/422). Sự kiện:

- `start` `{user_message}` → nhiều `token` `{text}` → `done` `{assistant_message, conversation}`.
- Lỗi giữa chừng: `error` `{code, retry_after?}`, code = `LLM_RATE_LIMITED` | `LLM_NOT_CONFIGURED` | `LLM_ERROR` | `INTERNAL_ERROR`. Tin của người dùng bị gỡ khỏi checkpoint.
- Client ngắt kết nối (nút Dừng) cũng gỡ tin của người dùng. Đồ thị LangGraph phát token bằng `stream_mode="custom"` (`StreamWriter` trong node `generate`).
- Xoay key chỉ làm được khi lỗi xảy ra TRƯỚC đoạn đầu tiên; lỗi giữa chừng không đổi key được (đã lỡ gửi một phần).

### FE (`pages/Chat.tsx`, route `/chat/:conversationId?`)

- Sidebar: danh sách cuộc trò chuyện thật; **tạo** (nút "Cuộc trò chuyện mới", trên điện thoại có thêm nút `+` ở thanh tiêu đề), **đổi tên** tại chỗ (Enter lưu, Esc huỷ), **xoá** có hộp xác nhận (xoá cả lịch sử trong checkpoint). Bấm nút "Cuộc trò chuyện mới" gọi `POST /conversations` ngay, mở cuộc đó và đặt con trỏ vào ô nhập; nếu đã có sẵn một cuộc trống (chưa có tin nào) thì mở lại cuộc đó thay vì tạo thêm, để không đầy cuộc rỗng. Nếu vào `/chat` chưa có cuộc nào (lần đầu) thì gửi tin đầu tiên sẽ tự tạo; khi đó nếu tin lỗi/bị dừng thì cuộc vừa tạo bị xoá lại.
- Chat: câu trả lời hiện dần theo stream, render markdown (`react-markdown` + `remark-gfm`, không render HTML thô), nút Dừng, Enter gửi / Shift+Enter xuống dòng (không gửi khi đang gõ dấu bằng IME). Lỗi → banner, tin tạm bị gỡ và nội dung được trả lại ô nhập.
- **Thời gian chờ** hiển thị dưới mỗi tin của bot: tiếng Anh `10.9s`, tiếng Việt `10,9s` (`lib/format.ts`). Đang chờ thì đồng hồ chạy trực tiếp; xong thì hiện con số server đã đo và lưu.
- Nút "Báo câu trả lời sai" gửi `message_id` = id tin nhắn thật trong LangGraph (feature `user-feedback`).
- Cuộn tự theo tin mới trừ khi người dùng đang cuộn lên đọc. Đang chờ trả lời thì chưa cho chuyển/xoá cuộc trò chuyện khác.
- Nút Chia sẻ và Đính kèm đang bị vô hiệu hoá (chưa làm `share-conversation` / upload).

### Giới hạn hiện tại / việc còn lại

- **CHƯA có RAG:** bot chưa tra được văn bản quy chế (cần `admin-document-vectorization` / `admin-document-upload`). Prompt hệ thống buộc bot không bịa điều/khoản/con số và khuyên đối chiếu văn bản chính thức. Chưa trả `sources` (trích dẫn) — định dạng trích dẫn vẫn cần chốt.
- Chưa có: upload ảnh/PDF, rate limit theo user (chip "Còn [N] câu hỏi hôm nay" đã bỏ khỏi UI vì chưa có số liệu thật), khoá chống hai request song song trong cùng một cuộc trò chuyện, tự đặt tên cuộc trò chuyện bằng LLM (hiện lấy 60 ký tự đầu của câu hỏi đầu tiên).
- Chưa kiểm chứng với Gemini thật cho trường hợp 429 (chỉ test bằng lỗi giả); lỗi key sai thì đã thử thật.
- Thời gian chờ do server đo từ lúc bắt đầu chạy đồ thị đến khi Gemini trả xong, nên thấp hơn thời gian client thực chờ vài phần mười giây (chi phí mạng + đọc checkpoint). Khi test bằng script Python trên Windows nhớ dùng `127.0.0.1` thay vì `localhost` (IPv6 fallback thêm ~2s mỗi kết nối).

## Đã làm — 2026-10-11: RAG, giọng điệu, rate limit

- **RAG:** node `generate` gọi `Retriever` (xem `admin-document-vectorization.md`) rồi nhét các Điều liên quan vào prompt hệ thống dưới mục "NGỮ CẢNH". Tin trả lời lưu thêm `additional_kwargs["sources"] = [{article, title}]` (chưa lộ ra API/FE; dùng để test và làm trích dẫn sau này). Tra cứu lỗi thì chỉ log và vẫn trả lời (không ngữ cảnh).
- **Giọng điệu:** prompt yêu cầu xưng "mình"/"bạn", dễ thương, 1–3 emoji, giải thích dễ hiểu, tính từng bước khi có số liệu, công thức viết bằng chữ thường (KHÔNG LaTeX vì FE không render), không bịa khi NGỮ CẢNH không có, từ chối nhẹ nhàng việc ngoài học vụ, vẫn trả lời tiếng Anh nếu hỏi tiếng Anh.
- **Rate limit:** tối đa `CHAT_RATE_LIMIT_MAX`=10 tin / `CHAT_RATE_LIMIT_WINDOW_SECONDS`=300 giây cho MỖI user (cửa sổ trượt, tính chung mọi cuộc trò chuyện, cả endpoint thường và stream). Quá thì **HTTP 429** `{"detail":"RATE_LIMITED"}` + header `Retry-After`, tin không được lưu và không gọi LLM. Chỉ tính sau khi qua kiểm tra quyền sở hữu/nội dung (404/422 không tốn lượt); lượt bị LLM lỗi vẫn tính. Code: `app/services/rate_limit.py`, `_enforce_rate_limit` trong `app/api/v1/conversations.py`. Giới hạn: đếm trong bộ nhớ của process (1 worker); nhiều worker cần chuyển sang kho dùng chung.
- **FE:** nhận 429 → hiện câu thân thiện `chat.errTooManyMessages` (chưa hiện số giây còn lại vì `ApiError` chưa mang `Retry-After`).
- **Test live bằng Gemini thật** (`pytest -m live`, ~8–10 phút): `tests/test_rag_live.py` dùng đúng `GeminiClient` + `GeminiEmbedder` của production. Có 36 câu hỏi (mỗi Điều ≥1), 26 câu công thức/tính toán (Điều 5, 8, 18, 19, 22, 24, 25, 28, 30, 32, 34), 2 câu "không có trong văn bản", kiểm tra giọng điệu/ngôn ngữ/ngoài phạm vi. Kết quả 2026-10-11: 136/136 đạt (truy xuất 65/65 đúng Điều). Để không vượt quota free (`tests/live_gemini.py`): LLM giãn cách 7s (~8 RPM, trần free 15), embedding giãn cách 2s (~30 RPM, trần 100), trần 90 lần LLM + 120 lần embedding mỗi lượt và 250 lần LLM mỗi ngày (đếm trong `tests/.live_quota.json`), cache vector câu hỏi lên đĩa (`tests/.live_embed_cache.json`), 503 "high demand" thì chờ 20s thử lại ≤2 lần, 429 thì dừng (skip). Đã thử ds2api nhưng gặp `RISK_DEVICE_DETECTED` phía DeepSeek nên bỏ.

## Đã làm — 2026-10-11 (tiếp): tham chiếu bấm-để-xem-PDF, trả lời "có đạt được không", xoay key embedding

- **Tham chiếu (info referral):** mỗi tin của bot có `sources: [{article, title}]` = các Điều câu trả lời THỰC SỰ nhắc tới ("Điều 24"), giới hạn trong các Điều đã đưa cho LLM (`app/services/rag/citations.py`). `retrieved` (toàn bộ Điều làm ngữ cảnh) chỉ lưu trong checkpoint để test/gỡ lỗi. Prompt yêu cầu luôn ghi rõ "Điều N" bot dựa vào và không nhắc Điều không dùng. Mở lại cuộc trò chuyện (đọc từ checkpoint) vẫn còn tham chiếu.
- **API văn bản (công khai, không cần đăng nhập vì là tài liệu công khai và FE dùng thẻ img):** `GET /api/v1/documents/qd3266/layout` (số trang, kích thước ảnh, và với mỗi Điều: danh sách `{page, box:[trên,trái,dưới,phải]}` chuẩn hoá 0..1) và `GET /api/v1/documents/qd3266/pages/{n}.jpg` (ảnh từng trang, cache 1 ngày). Dữ liệu nằm trong `ctu-chatbot-be/app/data/qd3266/` (ảnh 110 dpi, ~3,6 MB, và `layout.json`) nên deploy không cần PDF gốc.
- **Vì sao dùng ảnh + khung toạ độ thay vì PDF.js:** PDF gốc là bản scan (không có lớp chữ) nên không tìm được chữ để tô. Script `scripts/build_pdf_layout.py` render từng trang ra JPEG rồi nhờ Gemini nhìn ảnh khoanh từng khối văn bản và cho biết khối thuộc Điều nào (chỉ trả toạ độ, không chép chữ nên không dính RECITATION). Dùng `gemini-3.5-flash`/`gemini-3.8-flash` vì `gemini-3.1-flash-lite` khoanh lệch ~8% ở một số trang. Phản hồi thô được cache ở `scripts/.layout_raw/` (gitignore). Chạy lại khi PDF đổi: `python scripts/build_pdf_layout.py --pdf <file>` (biến `LAYOUT_MODEL`, `LAYOUT_INTERVAL`; model free có hạn mức thấp, 5 RPM/20 RPD, script tự xoay key và dừng khi hết hạn mức).
- **FE:** dưới mỗi câu trả lời hiện chip "Tham chiếu: Điều 24. …" (`MessageBubble`). Bấm chip mở `ReferencePanel` bên phải (toàn màn hình trên điện thoại): ảnh trang PDF, tự cuộn tới đoạn đầu tiên được tô vàng (`scrollIntoView`), phóng to/thu nhỏ, Esc để đóng. Khung tô sáng dùng `mix-blend-multiply` nên chữ vẫn đọc được. Mức tô là từng khoản/đoạn của cả Điều (chưa tô riêng câu bot dựa vào).
- **Trả lời "có đạt được mục tiêu không":** prompt buộc tính mức tối đa trước, MỞ ĐẦU bằng "Có thể"/"Không thể" kèm con số (ví dụ "tối đa 3,47"), nêu cải thiện điểm là cách duy nhất khi không thể, và nhắc ĐTBCTL chỉ tính học phần đã tích lũy (bỏ F, học phần điều kiện). Có 2 ví dụ mẫu trong prompt (một có, một không) vì chỉ một ví dụ làm model nghiêng hẳn về "Không thể". Test: `FEASIBILITY_CASES` g01–g04 trong `tests/rag_cases.py`.
- **Embedding xoay key:** `GeminiEmbedder` dùng `KeyPool`: key hết hạn mức (429) hoặc bị từ chối thì nghỉ rồi chuyển key kế tiếp (thứ tự: `EMBEDDING_MODEL_API_KEY`, rồi `GEMINI_API_KEY_*`); 503 thì thử lại cùng key; mọi key cùng nghỉ thì báo lỗi, không gọi dồn dập. Test: `tests/test_embedding_rotation.py`.
- Còn lại: tô đúng câu/khoản bot dựa vào (cần bot trả về số khoản), highlight theo từ khoá, lưu `retrieved` vào API nếu admin cần xem.

## Đã làm — 2026-10-11 (tiếp 2): tính điểm bằng mã, panel tham chiếu xem được cả văn bản

Phản hồi từ thử nghiệm thật: (1) chip tham chiếu bị lặp hai lần và không biết chip nào ứng với đoạn nào, (2) tính ĐTBCTL phải dựa trên TC được tính điểm (loại học phần điều kiện), (3) mở PDF rồi không chuyển qua lại được.

- **Tính điểm bằng mã, LLM chỉ diễn giải.** Model lite hay tự chia sai (524/151 -> 3,33; 13/6 -> 2,33) và so sánh sai (3,60 >= 3,60 -> "không thể"); prompt không sửa được. Nên: `app/services/chat/gpa_assist.py` gọi LLM MỘT lần để trích số liệu thành JSON (chỉ khi tin nhắn có từ khoá điểm/TC và >= 2 con số), Python tính (`app/services/grades.py`, `app/services/grades_courses.py`), rồi chèn khối "KẾT QUẢ TÍNH SẴN" vào prompt hệ thống; bot được dặn dùng NGUYÊN các con số đó. Trích số liệu lỗi thì bỏ qua, bot vẫn trả lời.
  - Khả năng đạt mục tiêu: `C` = TC đã học được tính điểm, `T` = tổng TC chương trình được tính điểm (đều LOẠI học phần điều kiện và điểm M/W/I/F). `ĐTBCTL tối đa = (C x ĐTBCTL + (T - C) x 4) / T`; điểm cần đạt ở phần còn lại `= (mục tiêu x T - C x ĐTBCTL) / (T - C)`. Bảng cho cả 4 hạng. So sánh làm tròn 2 chữ số như bảng ở Điều 34.
  - Người dùng chưa nói số TC không tính điểm thì bot trả lời theo giả định "mọi TC đều tính", nói rõ giả định và HỎI đúng hai số: TC học phần điều kiện/điểm M đã học, và tổng TC học phần điều kiện của chương trình. Khi người dùng cho, tính lại ở lượt sau (đã có test nhiều lượt: 151/100/3,5 với 30 TC điều kiện -> 3,71, cần 3,74).
  - ĐTBCHK/ĐTBCTL từ danh sách môn: ĐTBCHK gồm cả F và học phần điều kiện trừ GDTC; ĐTBCTL bỏ F và mọi học phần điều kiện; M/I/W không tính; quy đổi thang 10 -> chữ theo Điều 22.
  - Tồn tại: `ĐTBCTL` hiện tại người dùng nói được coi là đúng (không kiểm tra lại); `Điều 22` điểm D+ ... đủ; làm tròn ĐTBCTL cuối cùng văn bản không nêu.
- **Tham chiếu:** chip nay hiện thành danh sách dọc ("Điều 34. Bằng tốt nghiệp...", nút Xem/Đang xem, chip đang mở được viền vàng). Chữ "Điều N" trong chính câu trả lời cũng thành nút bấm (gạch chân chấm, nền vàng nhạt), nên biết ngay câu nào dựa vào Điều nào. Đã sửa lỗi hiện chip hai lần do vá lặp.
- **Panel xem văn bản (`ReferencePanel`):** hiện TOÀN BỘ 21 trang (ảnh lazy-load, giữ tỉ lệ nên cuộn mượt), tự cuộn tới đoạn tô vàng; thanh lật trang ‹ Trang N/21 ›; nút "Về đoạn tham chiếu"; nếu câu trả lời có nhiều tham chiếu thì có tab chuyển qua lại ngay trong panel; phóng to/thu nhỏ; Esc để đóng.

## Sửa lỗi — học bổng khuyến khích học tập (Điều 9)

- **Lỗi người dùng báo:** hỏi "GPA 3,8 ĐRL 89 so với GPA 3,6 ĐRL 90, ai được học bổng?" bot trả lời người GPA 3,8, sai. Nguyên nhân: Điều 9 khoản 1 chia học bổng thành các MỨC, mỗi mức đòi hỏi CẢ ĐTBCHK lẫn ĐRL (xuất sắc = ĐTBCHK xuất sắc VÀ ĐRL xuất sắc; giỏi = ĐTBCHK từ giỏi VÀ ĐRL từ tốt...). Học bổng cấp từ mức cao xuống thấp, chỉ khi cùng mức mới so ĐTBCHK rồi mới đến ĐRL. Bot chỉ đọc câu "ưu tiên theo ĐTBCHK" và bỏ qua bước xếp mức. Người GPA 3,8/ĐRL 89 chỉ đủ mức giỏi (ĐRL 89 là "tốt"), người GPA 3,6/ĐRL 90 đủ mức xuất sắc, nên người thứ hai được xét trước.
- **Cách sửa:** thêm vào prompt hệ thống quy trình 3 bước (xếp mức, cấp từ mức cao xuống, rồi mới so ĐTBCHK/ĐRL) kèm một ví dụ mẫu số liệu khác.
- **Kiến thức ngoài văn bản:** bảng xếp loại ĐRL KHÔNG có trong QĐ 3266 mà ở Thông tư 16/2015/TT-BGDĐT (được QĐ viện dẫn): 90–100 xuất sắc, 80 đến dưới 90 tốt. Chỉ hai ngưỡng này đã đối chiếu với nguồn thứ cấp (hoatieu.vn); các ngưỡng thấp hơn chưa đưa vào prompt vì chưa kiểm chứng. Nên đối chiếu thêm với quy định rèn luyện của Trường ĐHCT.
- **Test:** `tests/rag_cases_scholarship.py` (h01 đúng câu người dùng, h02 cùng mức thì so ĐTBCHK, h03 cùng ĐTBCHK thì so ĐRL), chạy qua `test_scholarship_ranking_follows_level_then_gpa_then_conduct`; 3/3 đạt với `gemini-3.5-flash-lite`.

## Độ chính xác khi tính toán và áp dụng luật có ngưỡng (2026-10-18)

Bộ 62 câu hỏi khó (`tests/rag_cases_hard.py`) lộ ba loại lỗi của model nhỏ: viết kết luận ở câu đầu TRƯỚC khi áp dụng hết các bước, nhầm mốc "đúng bằng ngưỡng" (8/16 TC = 50% không phải "vượt quá 50%"), và chồng điều kiện (F > 5% cộng cảnh cáo vẫn chỉ giảm MỘT mức). Prompt không sửa được, nên đã chuyển sang mã:

- **Bộ luật bằng mã** (`app/services/rules.py`), chạy sau bước trích số liệu (`app/services/chat/gpa_assist.py`, một lần gọi LLM, chỉ khi tin nhắn có từ khoá và con số):
  - Hạng tốt nghiệp (Điều 34): chỉ xuất sắc/giỏi bị giảm, tối đa MỘT mức; F phải LỚN HƠN 5% tổng TC (đúng 5% chưa vượt); không tính F của học phần học cải thiện; chỉ kỷ luật từ cảnh cáo cấp Trường trở lên mới giảm (khiển trách thì không).
  - Cảnh báo học tập và buộc thôi học (Điều 18): ĐTBCHK dưới 0,80 (học kỳ đầu) / 1,00; từ K47 mới có các tiêu chí TC không đạt > 50%, nợ > 24 TC, ĐTBCTL dưới 1,2/1,4/1,6/1,8 theo năm; tiêu chí nào thiếu số liệu thì báo "chưa kiểm tra được" chứ không kết luận "không bị".
  - Học bổng (Điều 9): xếp MỨC (cả ĐTBCHK và ĐRL; ĐRL theo Thông tư 16/2015: 90-100 xuất sắc, 80-dưới 90 tốt, 65-dưới 80 khá), cấp từ mức cao xuống, cùng mức mới so ĐTBCHK rồi ĐRL; kiểm tra 12 TC đăng ký, điểm F, kỷ luật.
  - Máy tính điểm (`grades.py`) có thêm "ĐÃ CHẮC CHẮN / CHƯA CHẮC CHẮN" (tính ĐTBCTL tối thiểu nếu phần còn lại chỉ được điểm D).
  - Kết quả được chèn vào prompt dưới tiêu đề "KẾT QUẢ TÍNH SẴN"; bot dùng NGUYÊN các kết luận đó.
- **Công cụ máy tính cho bot** (`app/services/tools/calculator.py`, vòng lặp gọi công cụ ở `app/services/chat/tooling.py`): `calculate` (số học bằng phân số, không `eval`, làm tròn kiểu thông thường, trả cả giá trị chi tiết và làm tròn 2 chữ số) và `compare_numbers` (ĐÚNG/SAI cho "vượt quá", "từ... trở lên", "dưới", "tối đa", "đúng bằng"). Prompt bắt buộc dùng cho mọi phép tính và so sánh với ngưỡng. `GeminiClient.stream(messages, tools=...)` gắn công cụ qua `bind_tools`; client nào có `supports_tools = True` thì đồ thị dùng vòng lặp công cụ (tối đa 4 lượt), client khác (FakeLLM...) stream thẳng. Các lần gọi công cụ được lưu trong `additional_kwargs["tools"]` để gỡ lỗi.
- **Kết quả:** lần chạy đầu bộ câu khó 56/62; sau khi thêm bộ luật + công cụ 59/62 (3 câu còn lại là regex kiểm tra quá chặt hoặc thiếu chức năng "chắc chắn", đã sửa; chạy lại các câu đó đều đạt). Test offline 371 đạt. Kết quả live có thể dao động giữa các lần chạy vì model sinh chữ.
- **Giới hạn đã biết:** cách trích số liệu vẫn nhờ LLM đọc câu hỏi (có thể trích nhầm khóa, năm học...); ĐTBCTL người dùng nêu được coi là đúng; ĐRL dưới 65 chưa dùng trong tiêu chí học bổng nào ngoài "khá".

## Câu hỏi gợi ý có cache, trang chủ mới, chỉ tiếng Việt (2026-10-18)

- **Câu hỏi gợi ý khi mới mở chat** thay cho 3 câu cũ: 4 câu về học bổng và điểm trung bình (2 học bổng: so sánh hai bạn, xếp mức theo ĐRL; 2 điểm: tính ĐTBCHK 3 môn, khả năng tốt nghiệp xuất sắc). Hiển thị xếp thành MỘT cột, mỗi câu một hàng, kèm nhãn nhóm; nguồn danh sách là server (`GET /api/v1/suggestions`, công khai, không kèm câu trả lời).
- **Cache câu trả lời, không gọi LLM:** file `app/data/suggested.json` do `scripts/build_suggested_cache.py` sinh bằng cách chạy bot thật tối đa 4 lần mỗi câu cho tới khi qua bộ kiểm tra đáp án (`tests/answer_checks.py`). Khi tin nhắn gửi lên khớp một câu gợi ý (`app/services/chat/suggested.py`: không phân biệt hoa thường, dấu cách thừa, dấu câu cuối) thì `cached_turn` ghi cặp tin nhắn vào checkpoint bằng `graph.update_state(..., as_node="generate")` và trả câu trả lời có sẵn: không gọi LLM, embedding hay công cụ; câu hỏi sau đó vẫn nhớ ngữ cảnh. Câu có sẵn KHÔNG tính vào giới hạn chat 10 tin/5 phút. Tin của bot có cờ `cached` (FE hiện nhãn "Trả lời có sẵn" thay cho thời gian chờ). Endpoint stream phát lại theo đúng định dạng sự kiện (start, nhiều token, done).
- **Đổi câu hỏi hoặc prompt thì chạy lại script;** test `tests/test_suggested.py` kiểm tra cache khớp danh sách trong script và mọi câu trả lời vẫn qua bộ kiểm tra đáp án (đáp án đúng chính xác, giọng thân thiện, tham chiếu hợp lệ), cùng các hành vi API ở trên.
- **Trang chủ thiết kế lại** (`src/pages/Landing.tsx`): header navy, hero có minh họa chat và trang văn bản tô vàng, dải căn cứ (QĐ 3266, 36 Điều, 4 Chương), 4 tính năng thật (dẫn đến Điều, tính điểm chính xác, kiểm tra đúng từng mốc, dễ hiểu), mục "Thử ngay những câu hỏi khó" lấy từ API gợi ý (ẩn nếu lỗi mạng), 3 bước, kêu gọi đăng nhập, footer. Nội dung chỉ nói tính năng có thật (đã bỏ "đính kèm ảnh, PDF" và "chia sẻ" vì chưa làm). Thiết kế gốc dựng bằng Claude Design (xem canvas), bản React bám theo.
- **Chỉ tiếng Việt:** xóa `i18n/en.ts`, nút chuyển ngôn ngữ, ô chọn ngôn ngữ ở hồ sơ; `formatSeconds` và định dạng ngày luôn dùng `vi-VN`. Giữ BE nguyên (cột `language` còn đó nhưng không dùng). Bot vẫn trả lời bằng ngôn ngữ người dùng viết nếu họ hỏi tiếng Anh.

## Chạy test online các câu khó (2026-10-18)

- Chạy với `gemini-3.5-flash-lite` thật: 62 câu khó + học bổng + "có đạt được mục tiêu không" + 26 câu công thức = 97 câu, **97/97 đạt** (lần chạy chính 94 đạt; 2 câu k03/k08 lỗi vì Gemini thỉnh thoảng trả về câu trả lời RỖNG, 1 câu o10 bị bỏ qua do chạm trần gọi mỗi ngày tự đặt; chạy lại riêng 3 câu đều đạt).
- **Thử lại khi Gemini trả rỗng** (`generate` trong `app/services/chat/graph.py`): chưa có chữ nào gửi cho người dùng nên thử lại được. Lần 1 chạy lại vòng lặp công cụ; lần 2 gọi không có công cụ nhưng kèm kết quả các phép tính đã chạy trong prompt; vẫn rỗng mới báo `LLM_ERROR`. Có test `tests/test_tools.py` (4 trường hợp).
- Trần bảo vệ quota của test live nằm ở `tests/live_gemini.py` (mỗi lượt 200 lần gọi LLM, mỗi ngày 520; đếm trong `tests/.live_quota.json`). Mỗi câu hỏi có thể tốn 2-5 lần gọi (trích số liệu, các lượt công cụ, trả lời).

## Guardrail phạm vi + tìm web + hàng đợi lượt chat

**Guardrail (`app/services/chat/scope.py`)** — mỗi lượt được xếp vào một tuyến:
- `regulation` (thuộc QĐ 3266 → RAG + máy tính như cũ), `external` (về CTU nhưng ngoài quy chế → bật công cụ `web_search`),
  `offtopic` (từ chối lịch sự, không tìm), `smalltalk` (chào hỏi).
- Luật rẻ trước: chào hỏi ngắn → smalltalk; nêu "Điều N"/ĐTBCTL/cảnh báo học tập... hoặc điểm cosine ≥ 0,75 → regulation.
  Vùng mơ hồ (điểm đo được: quy chế 0,68–0,83; ngoài quy chế nhưng về CTU 0,62–0,74; lạc đề 0,52–0,59 — hai nhóm đầu chồng nhau
  nên không thể chỉ dùng điểm) nhờ MỘT lần gọi LLM phân loại. Lỗi/đầu ra lạ → `regulation` (hành vi cũ, an toàn).
- Tuyến lưu vào `additional_kwargs["route"]`. Tắt cả guardrail: `WEB_SEARCH_ENABLED=false`.

**Tìm web (`app/services/tools/web_search.py`)** — DuckDuckGo qua `ddgs` (Gemini Google Search grounding bị 429 ở gói miễn phí).
Trang `*.ctu.edu.vn` xếp lên đầu; cache 10 phút; tối đa 2 lần tìm/lượt và 20 lần/phút cho cả server; kết quả web là dữ liệu
không tin cậy (prompt dặn không làm theo chỉ dẫn trong đó). Câu trả lời trích nguồn bằng `[n]`; các nguồn thật sự được trích
(hoặc các trang chính thức nếu model không đánh số) trả về trong `sources` dưới dạng `{title, url}` và hiện ở mục "Nguồn trên web"
(chỉ nhận http/https). Tuyến `external` không đưa ngữ cảnh quy chế vào prompt để model khỏi lạc sang quy chế.

**Hàng đợi (`app/services/chat/queue.py`)** — `CHAT_MAX_CONCURRENT` (4) lượt chạy cùng lúc, tối đa `CHAT_QUEUE_MAX_WAITING` (30)
lượt xếp hàng FIFO; hàng đầy → HTTP 503 `SERVER_BUSY` + `Retry-After` (thay vì nhận vô hạn rồi sập); mỗi người một lượt đang
chờ/chạy (429 `TURN_IN_PROGRESS`); chờ quá `CHAT_QUEUE_WAIT_SECONDS` (120) → lỗi `SERVER_BUSY`. SSE có thêm sự kiện
`queued {position}`, giao diện hiện "Đang xếp hàng, vị trí N". Lượt bị từ chối vì hàng đầy không bị trừ giới hạn 10 tin/5 phút.
Câu hỏi gợi ý (có sẵn đáp án) không qua hàng đợi. Chỗ luôn được trả (finally), vé bị bỏ quên được dọn theo thời gian.
Hàng đợi nằm trong bộ nhớ một process: chạy nhiều worker/instance thì mỗi cái có hàng riêng (muốn chung phải dùng Redis).

Kiểm thử: `test_queue.py`, `test_scope.py`, `test_web_search.py`, `test_graph_routing.py` (offline); `test_scope_live.py`
(`pytest -m live`: 12 câu quy chế không bị đẩy sang web, 8 câu ngoài quy chế → external, 4 lạc đề, 3 xã giao, 1 e2e có nguồn web).

### 2026-10-18: sửa tuyến câu hỏi và đồng hồ thời gian
- Chọn tuyến (regulation / external / ...) dựa trên điểm của CÂU MỚI NHẤT riêng (trước đây dùng câu ghép với câu trước nên hỏi quy chế xong hỏi sang ký túc xá bị coi là vẫn thuộc quy chế và không tìm web). Có từ hai câu hỏi trở lên thì tốn thêm một lần embedding.
- Nguồn web trả lời kèm số `[n]` khớp với trích dẫn trong câu trả lời.
- Đồng hồ: con số cuối của tin bot chính là số đồng hồ đang chạy trên giao diện (từ lúc bấm gửi đến lúc nhận đủ câu trả lời), không đổi sang số server đo; mở lại cuộc trò chuyện thì hiện số server đo (không gồm mạng/hàng đợi).

### 2026-10-18: giới hạn chat chỉnh bằng MỘT biến `CHAT_RATE_LIMIT`
- Định dạng `"<số tin>/<thời gian>"`, đơn vị `s` (giây) / `m` (phút) / `h` (giờ): `10/5m` (mặc định), `30/1h`, `5/30s`; `off` = không giới hạn. Sai định dạng thì app báo lỗi rõ ngay lúc khởi động. Thay hai biến cũ `CHAT_RATE_LIMIT_MAX` / `CHAT_RATE_LIMIT_WINDOW_SECONDS` (nếu `.env` còn hai biến này thì bị bỏ qua — phải đổi sang `CHAT_RATE_LIMIT`).
- Giới hạn tính theo từng user, trong bộ nhớ một process (xem `app/services/rate_limit.py`); câu hỏi gợi ý có sẵn đáp án không tính.
- Lỗi 429 trả kèm `{"code": "RATE_LIMITED", "limit": N, "window": {"amount": M, "unit": "m"}}` nên giao diện hiện đúng "tối đa N tin trong M phút" theo cấu hình hiện tại.

### 2026-10-18: hộp thoại vui khi bị giới hạn / chat lỗi + chào mừng người dùng mới
- **Khi gửi tin bị lỗi** (vượt `CHAT_RATE_LIMIT`, chatbot đang bận / đông, hết hạn mức LLM, lỗi LLM, mất mạng, chỉ có quyền xem...): hiện hộp thoại `ChatErrorDialog` có GIF ngẫu nhiên trong `src/assets/exceed_rate_limit_gifs/`, huy hiệu icon (đồng hồ cát = nhắn quá nhanh, lấp lánh = chatbot bận, cảnh báo = lỗi), lời nhắn, và đếm ngược "Thử lại sau m:ss" khi server báo `retry_after`. Nội dung đang gõ được giữ lại trong ô nhập. Phân loại ở `src/lib/chatErrors.ts`.
- **Chào mừng người dùng mới:** `WelcomeDialog` hiện đúng MỘT lần cho tài khoản mới (cột `users.welcomed_at`, migration `e5f1c3a8d902` đánh dấu sẵn cho mọi tài khoản đã có; `POST /me/welcome` ghi nhận ngay khi hộp thoại hiện ra). Bố cục: GIF to ở giữa (ngẫu nhiên trong `src/assets/welcome_gifs/`), pháo hoa bắn liên tục hai bên (`components/Fireworks.tsx`, canvas tự vẽ, tôn trọng `prefers-reduced-motion`), bên dưới là lời chào hài hài chọn ngẫu nhiên (`lib/greetings.ts`: "Chào đại ca / bé iu / cục dàng / baby ..."). Thêm GIF mới = bỏ file `.gif` vào thư mục tương ứng, không cần sửa code.

### 2026-10-18: lời chào mừng người dùng mới (không phân biệt nam / nữ)
- Lời chào chọn NGẪU NHIÊN từ một danh sách chung (đã bỏ ý định đoán giới tính từ tên cho đỡ rắc rối). **Chỗ chỉnh:** `src/lib/greetings.ts`, mảng `GREETINGS` ở đầu file, mỗi dòng `[cách gọi, lời nhắn]` → hiển thị "Chào {cách gọi} {tên}!" + lời nhắn. Câu chúc mừng nhỏ phía dưới: `src/i18n/vi.ts`, khoá `welcome.congrats`; nút: `welcome.start`. Xem thử mọi GIF: `/dev/gifs` (chạy `npm run dev`).

## Bộ lọc trước LLM: chửi thề và chào hỏi
- `app/services/chat/moderation.py` (`is_profane`): chửi thề / lăng mạ (có dấu, không dấu, viết tắt như đm, vcl, tiếng Anh) → HTTP 422 `PROFANITY`, không vào hàng đợi, không gọi LLM, không lưu vào lịch sử. Từ mơ hồ khi bỏ dấu (cac, lon, du, deo...) chỉ bị xét khi cả câu gõ không dấu để tránh chặn nhầm ("các bạn", "du lịch").
- `app/services/chat/smalltalk.py`: tin nhắn thuần chào hỏi / cảm ơn / tạm biệt / "bạn là ai" / "làm được gì" / "ok" → trả lời có sẵn (nhiều biến thể ngẫu nhiên), không gọi LLM; đi chung đường "trả lời có sẵn" với câu hỏi gợi ý. Câu có nội dung thật ("chào bạn, cho mình hỏi điều 14") vẫn đi đường bình thường.
- Cả chửi thề và chào hỏi đều TÍNH vào `CHAT_RATE_LIMIT` (câu hỏi gợi ý vẫn không tính). Hook ở `_pre_screen` trong `app/api/v1/conversations.py` (áp cho cả gửi thường lẫn stream, kể cả chat qua liên kết chia sẻ).
- FE: 422 PROFANITY → `ChatErrorDialog` kind `warning`: hộp thoại giữa màn hình với `assets/warning.gif`, tiêu đề + lời nhắn dễ thương ngẫu nhiên chỉnh tay ở `src/lib/warnings.ts`; nội dung không trả lại ô nhập.
- Lưu ý: tin chửi thề luôn nhận 422 PROFANITY (hộp thoại cảnh báo) kể cả khi người dùng đang bị giới hạn tốc độ; nó vẫn được tính vào giới hạn khi còn chỗ, còn tin bình thường kế tiếp mới nhận 429.
- Chê "ngu / ngố / ngáo / đần / khùng" cũng bị chặn (`_INSULT_WORDS` trong `moderation.py`), nhưng tự nhận ("mình ngu quá không hiểu điều 14") thì KHÔNG chặn; gõ không dấu chỉ chặn khi có đại từ chê bai đi kèm (bot ngu, mày ngu...) để khỏi nhầm với "ngủ", "ngao".

## Sức chịu tải và khuyến nghị rate limit (ước tính 2026-10-18, chưa đo thực tế)
- **Hạn mức Gemini tính theo project, không theo key.** Key thuộc cùng một project dùng chung quota; thêm key chỉ tăng quota thực tế nếu key thuộc project khác nhau. Router xoay khi bị 429 (`app/services/llm/key_pool.py`: dùng một key đến khi hết hạn mức mới chuyển).
- Mỗi lượt hỏi tốn khoảng 1,5 request LLM (1 lần trả lời; thêm 1 lần phân loại khi câu mơ hồ, thêm vòng gọi công cụ khi tìm web / tính điểm) và khoảng 6–9 nghìn token (do đưa các Điều trích vào ngữ cảnh), cộng 1–2 lần embedding truy vấn (hạn mức embedding riêng, chưa kiểm).
- Với `gemini-3.5-flash-lite` (15 RPM / 250K TPM / 500 RPD mỗi project) và 6 project: tối đa khoảng 60 lượt/phút (RPM là điểm nghẽn theo phút), khoảng 2.000 lượt/ngày (**RPD là điểm nghẽn thật**, reset nửa đêm giờ Thái Bình Dương) ⇒ khoảng 40–50 người chat liên tục cùng lúc, khoảng 50–70 người dùng đều đặn mỗi ngày. Cùng một project thì chia cho 6. Bật billing để tăng hạn mức nhiều lần.
- Điểm nghẽn phía server: `chat_max_concurrent=4` (mỗi lượt giữ chỗ 6–10 giây ⇒ khoảng 25–35 lượt/phút), nên tăng lên 8 nếu hạn mức API đủ.
- Câu hỏi gợi ý, chào hỏi, chửi thề không tốn request LLM nào; mở rộng bộ trả lời có sẵn là cách rẻ nhất để tăng sức chịu tải.
- **Khuyến nghị `CHAT_RATE_LIMIT=10/5m`** (khoảng 2 tin/phút/người; người thật hiếm khi chạm trần, người spam bị chặn sau 10 tin). Đổi lại giá trị này trước khi cho người dùng thật dùng nếu đang để thấp (như `1/60s`) để thử hộp thoại.
- **Chưa làm (đề xuất):** hỗ trợ nhiều cửa sổ giới hạn (ví dụ `10/5m,40/1d`) để chặn tổng lượt mỗi ngày mỗi người (khoảng 30–40) bảo vệ RPD, và đếm bằng DB thay vì bộ nhớ process (hiện restart là đếm lại từ đầu).
- Thông báo 429 trên giao diện không còn nêu con số giới hạn: lời nhắn "Phải cục dàng spam không dza?? Sống chậm lại xíu nhoaaa <3" (khoá `chat.errTooManyMessages*` trong `src/i18n/vi.ts`). Tin chửi thề luôn hiện cảnh báo chửi thề chứ không bị đổi thành thông báo giới hạn.

### 2026-10-18: giới hạn chat theo ngày (nhiều cửa sổ)
- `CHAT_RATE_LIMIT` nhận thêm đơn vị `d` (ngày) và NHIỀU cửa sổ cách nhau bằng dấu phẩy, ví dụ `10/5m,40/1d` (khuyến nghị để bảo vệ RPD của Gemini). Tin chỉ được nhận khi mọi cửa sổ còn chỗ; bị từ chối thì không cửa sổ nào bị tính thêm; 429 báo cửa sổ phải chờ lâu nhất (`limit`/`window` trong `detail`). Code: `MultiWindowLimiter`, `parse_rate_limits` trong `app/services/rate_limit.py`. Cửa sổ ngày là trượt 24 giờ, đếm trong bộ nhớ process (restart là đếm lại).
- FE: 429 do cửa sổ ngày hiện lời nhắn riêng `chat.errDailyLimit` ("hẹn bạn ngày mai nha") và KHÔNG có đồng hồ đếm ngược. Hướng dẫn deploy: `DEPLOY.md` ở thư mục gốc.

### 2026-10-18: câu gợi ý, giờ gửi, sidebar điện thoại
- 4 câu gợi ý (`app/data/suggested.json`, sinh bằng `scripts/build_suggested_cache.py`, chỉ sinh câu chưa có, `--force` = sinh lại hết), theo thứ tự: "151 tín chỉ / xuất sắc" (Điểm trung bình), "Hai bạn A/B" (Học bổng), "Cảnh báo học tập" (K48 rớt 8/16 TC) và "Tốt nghiệp" (ĐTBCTL 3,5 + 8 TC điểm F → loại khá). Lần sinh đầu của câu "Tốt nghiệp" từng ghi nhầm 5,67% (đúng 6,67%) mà vẫn qua bộ kiểm tra cũ nên đã thêm kiểm tra con số trong script.
- Rê chuột vào tin nhắn (cả của người dùng lẫn của bot): "Đã gửi lúc …" theo múi giờ đã cài, NỔI phía trên tin (không chừa chỗ trống trong bố cục).
- Sidebar (chat và admin) trên điện thoại (< 768px) là ngăn kéo trượt từ trái: nút hamburger ở đầu trang, bấm nền mờ / Esc / chọn một liên kết thì đóng, khoá cuộn nền khi mở, ngăn kéo đóng thì `inert`. Máy tính: cột cố định `sticky h-dvh`, thu gọn thành cột icon. Đã đo ở 390px: không trang nào tràn ngang.
