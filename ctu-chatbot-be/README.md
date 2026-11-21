# Luồng xử lý tin nhắn chat

Tài liệu mô tả luồng gửi tin hiện tại. Code chính: `app/api/v1/conversations.py` (quyền truy cập, lọc trước, hàng đợi và stream), `app/services/chat/graph.py` (LangGraph), `app/services/chat/route_catalog.py` (cấu hình tuyến), `app/services/chat/scope.py` (phân loại), `app/services/rag/` (truy xuất tài liệu).

## 1. Từ request đến câu trả lời

```mermaid
flowchart TD
    A([Gửi tin nhắn]) --> B{Có quyền chat<br/>với cuộc trò chuyện?}
    B -- Không --> B1([HTTP 404 hoặc 403])
    B -- Có --> C[Kiểm tra attachment thuộc người gửi]
    C --> D{Tin nhắn có chửi thề?}
    D -- Có --> D1[Cộng lượt rate limit nếu còn chỗ<br/>Ghi bộ đếm vi phạm]
    D1 --> D2([HTTP 422 PROFANITY<br/>không vào hàng đợi, không gọi LLM])
    D -- Không --> E{Có attachment?}
    E -- Có --> Q
    E -- Không --> F{Khớp câu hỏi gợi ý?}
    F -- Có --> F1[Trả lời đã lưu<br/>không tính rate limit, không vào hàng đợi]
    F -- Không --> G{Khớp chào hỏi xã giao?}
    G -- Có --> H{Còn trong rate limit?}
    H -- Không --> H1([HTTP 429 RATE_LIMITED])
    H -- Có --> G1[Trả lời có sẵn<br/>không vào hàng đợi, không gọi LLM]
    G -- Không --> Q{Vào được hàng đợi?}
    Q -- Hàng đầy --> Q1([HTTP 503 SERVER_BUSY])
    Q -- User đã có lượt khác --> Q2([HTTP 429 TURN_IN_PROGRESS])
    Q -- Có --> R{Còn trong rate limit?}
    R -- Không --> R1[Trả chỗ trong hàng đợi]
    R1 --> R2([HTTP 429 RATE_LIMITED])
    R -- Có --> S[Chờ đến lượt]
    S -- Hết thời gian chờ --> S1([HTTP/SSE 503 SERVER_BUSY])
    S -- Đến lượt --> S2{Khóa được cuộc trò chuyện?}
    S2 -- Không --> S3([HTTP/SSE 409 CONVERSATION_BUSY])
    S2 -- Có --> T[[LangGraph: node generate]]
    T --> U{Gửi kiểu nào?}
    U -- Stream --> U1([SSE start, rồi token trong lúc graph chạy])
    U1 --> V[Lưu lịch sử trong checkpoint Postgres<br/>cập nhật cuộc trò chuyện và thống kê]
    V --> U2([SSE done])
    U -- Request thường --> U3[Lưu checkpoint và cập nhật cuộc trò chuyện]
    U3 --> U4([JSON có tin nhắn người dùng và bot])
    F1 --> C1[Lưu lượt có sẵn vào checkpoint<br/>cập nhật cuộc trò chuyện và thống kê]
    G1 --> C1
    C1 --> C2{Gửi kiểu nào?}
    C2 -- Stream --> C3([SSE start → token... → done])
    C2 -- Request thường --> C4([JSON có tin nhắn người dùng và bot])
    U2 --> W[Trả chỗ queue nếu đã xin<br/>nhả khóa nếu đã lấy]
    U4 --> W
```

Các kiểm tra quyền và attachment diễn ra trước lọc nội dung. Chửi thề luôn trả `422 PROFANITY`; lượt này chỉ được ghi vào rate limit nếu cửa sổ còn chỗ, và không bị đổi thành lỗi 429. Tin có attachment bỏ qua câu trả lời gợi ý/chào hỏi để nội dung tệp được xử lý trong graph. Câu hỏi gợi ý không tính rate limit; chào hỏi có sẵn thì có tính. Tin bình thường xin chỗ trong queue trước rồi mới tính rate limit; nếu rate limit từ chối, chỗ queue được trả ngay. Giới hạn lấy từ `CHAT_RATE_LIMIT` (mặc định `10/5m`, hỗ trợ nhiều cửa sổ hoặc `off`).

Với endpoint stream, lỗi kiểm tra trước khi stream được trả dưới dạng HTTP bình thường. Trong stream, queue có thể phát `queued`; lượt xử lý tiếp tục bằng `start`, các `token`, rồi `done`, hoặc `error` nếu lỗi. Request thường chờ queue mà không phát sự kiện vị trí. Queue và khóa cuộc trò chuyện được nhả trong mọi trường hợp.

## 2. Bên trong node `generate`

```mermaid
flowchart TD
    A([Bắt đầu generate]) --> B[Lấy cửa sổ lịch sử gần nhất]
    B --> C[Tra vector store bằng tin mới nhất<br/>và tin người dùng ngay trước đó]
    C --> D[Tra kiến thức hỏi-đáp bổ sung<br/>bằng riêng tin mới nhất]
    D --> E{Có retriever<br/>và route đang bật?}
    E -- Không --> E1[Tuyến mặc định regulation<br/>không phân loại]
    E -- Có --> F{Có attachment?}
    F -- Có --> F1[Chọn regulation nếu đang bật;<br/>nếu không, chọn tuyến document<br/>hoặc tuyến đầu tiên]
    F -- Không --> G{Kiến thức bổ sung<br/>đạt ngưỡng mạnh?}
    G -- Có --> G1[Chọn regulation<br/>hoặc tuyến đầu tiên nếu chưa bật]
    G -- Không --> H[Phân loại vào các tuyến đang bật<br/>router nhanh nếu áp dụng, nếu không gọi LLM]
    H --> I{Tuyến được chọn}
    E1 --> J
    F1 --> J
    G1 --> J
    I --> J{Tuyến loại document?}
    J -- Có --> K{Collection khác<br/>collection mặc định?}
    K -- Có --> K1[Tra lại collection của tuyến]
    K -- Không --> L[Soạn prompt theo tuyến và ngữ cảnh]
    K1 --> L
    J -- Không --> L
    L --> M{Tuyến và công cụ}
    M -- Document/regulation --> N[Prompt tài liệu + kiến thức khớp<br/>+ attachment nếu có<br/>+ kết quả GPA nếu có]
    M -- Document khác --> O[Prompt tuyến + tài liệu<br/>đã truy xuất]
    M -- Web --> P[Prompt web, bỏ ngữ cảnh tài liệu<br/>bật web_search]
    M -- Smalltalk/offtopic --> R[Prompt ngắn<br/>không tra cứu web]
    N --> S{LLM hỗ trợ tool<br/>và tuyến có tool?}
    O --> T[Stream LLM]
    P --> S
    R --> T
    S -- Có --> S1[Chạy vòng tool rồi stream câu trả lời]
    S -- Không --> T
    S1 --> U[Lưu câu trả lời và metadata<br/>route, nguồn, tools vào checkpoint]
    T --> U
    U --> V([Stream token cho client<br/>hoặc trả kết quả JSON])
```

Retriever lỗi không làm hỏng lượt chat: graph tiếp tục mà không có ngữ cảnh tài liệu. Danh sách tuyến lấy từ `vector-docs/routes.json`, chỉ gồm edge đang bật và node không ở trạng thái `pending`; tuyến loại `web` bị loại khi `WEB_SEARCH_ENABLED=false`. Không có retriever thì phân loại bị bỏ qua và graph dùng prompt mặc định regulation.

Với câu hỏi nối tiếp, truy vấn tài liệu ghép hai tin người dùng gần nhất để giữ ngữ cảnh; điểm phân loại dùng riêng câu mới nhất khi có lịch sử trước đó. Nếu có kiến thức bổ sung đạt ngưỡng `KB_STRONG_SCORE`, graph ưu tiên tuyến regulation (hoặc tuyến đầu tiên nếu regulation không bật). Attachment cũng bỏ qua phân loại và chọn regulation, nếu không có thì chọn tuyến document rồi tuyến đầu tiên. Tuyến document có thể kích hoạt lần truy xuất thứ hai vào collection riêng của tuyến.

Các tuyến loại document dùng tài liệu đã truy xuất. Riêng regulation còn ghép kiến thức hỏi-đáp phù hợp, nội dung attachment và kết quả tính GPA nếu có. Tuyến web bỏ ngữ cảnh ChromaDB và bật `web_search`; tuyến smalltalk/offtopic không tìm web. Công cụ chỉ chạy khi model hỗ trợ tool calling. Lịch sử chat được checkpoint trong Postgres; nguồn, tuyến và log tool cũng được lưu trong metadata của tin bot.

## 3. Ý nghĩa các loại tuyến

| Loại tuyến | Prompt / dữ liệu | Công cụ |
|---|---|---|
| `document` | Dùng collection ChromaDB được cấu hình cho node. `regulation` dùng prompt quy chế và có thêm xử lý GPA/kiến thức bổ sung. | `calculate`, `compare_numbers` cho regulation nếu model hỗ trợ |
| `web` | Bỏ ngữ cảnh tài liệu, tìm thông tin web theo prompt tuyến | `web_search` nếu model hỗ trợ |
| `smalltalk` | Trả lời xã giao bằng LLM nếu request không được lớp API trả lời có sẵn | Không |
| `offtopic` | Từ chối lịch sự theo prompt tuyến | Không |

ID tuyến có thể được quản trị viên cấu hình; `regulation`, `external`, `offtopic`, `smalltalk` là các ID mặc định, không phải danh sách cố định của graph.

## 4. Hai lớp trả lời xã giao

- `suggested.lookup`: câu hỏi gợi ý có câu trả lời được lưu sẵn; bỏ qua rate limit, queue và LLM.
- `smalltalk.lookup`: câu chào/cảm ơn/tạm biệt thuần xã giao có câu trả lời có sẵn; tính rate limit nhưng bỏ queue và LLM.
- Nếu không khớp toàn bộ tin nhắn (hoặc có attachment), tin đi qua graph. Router có thể chọn tuyến `smalltalk`, trường hợp này vẫn gọi LLM.

Code triển khai: `app/api/v1/conversations.py`, `app/services/chat/graph.py`, `app/services/chat/route_catalog.py`, `app/services/chat/scope.py`.
