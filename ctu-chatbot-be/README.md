# Flow xử lý một tin nhắn của agent

Tài liệu này chỉ mô tả đường đi của một prompt từ lúc người dùng gửi cho tới lúc có câu trả lời.
Code chính: `app/api/v1/conversations.py` (lọc đầu vào, hàng đợi), `app/services/chat/graph.py` (đồ thị LangGraph),
`app/services/chat/scope.py` (router phạm vi), `app/services/rag/store.py` (ChromaDB).

## 1. Toàn cảnh

```mermaid
flowchart TD
    U([Người dùng gửi prompt]) --> P{Chửi thề?<br/>moderation.is_profane}

    P -- Có --> P1[Tính 1 lượt vào rate limit]
    P1 --> P2([HTTP 422 PROFANITY<br/>không lưu lịch sử, không gọi LLM])

    P -- Không --> C{Câu hỏi mẫu hoặc<br/>chào hỏi có sẵn đáp án?<br/>suggested / smalltalk}
    C -- "Câu hỏi mẫu" --> C1([Trả đáp án đã lưu<br/>không gọi LLM, không tính rate limit])
    C -- "Chào hỏi xã giao" --> RL0{Rate limit}
    RL0 -- Vượt --> X429
    RL0 -- Còn --> C2([Trả đáp án có sẵn, không gọi LLM])

    C -- Không --> Q{Hàng đợi<br/>queue.enter}
    Q -- "Hàng đầy" --> X503([503 SERVER_BUSY])
    Q -- "User đang có lượt khác" --> X429([429 TURN_IN_PROGRESS])
    Q -- "Vào được" --> RL{Rate limit<br/>mặc định 10 tin / 5 phút}
    RL -- Vượt --> X429b([429 RATE_LIMITED + Retry-After])
    RL -- Còn --> G[[Đồ thị LangGraph: node generate]]

    G --> A([Stream câu trả lời về client<br/>lưu vào checkpoint Postgres])
```

Lưu ý thứ tự: **chửi thề được kiểm tra TRƯỚC rate limit** (tin chửi vẫn bị tính vào hạn mức nhưng luôn nhận lời cảnh báo
chửi thề chứ không nhận 429). Rate limit chỉ chặn các tin còn lại, và nằm sau bước xin chỗ trong hàng đợi.

## 2. Bên trong node `generate` (router phạm vi + RAG)

Đồ thị chỉ có **một node** `generate`. Router nằm bên trong node này và chạy **sau** khi đã tra ChromaDB một lần
(vì điểm giống nhau của kết quả tra cứu là một tín hiệu để chọn tuyến).

```mermaid
flowchart TD
    S([Bắt đầu node generate]) --> W[Lấy N tin gần nhất làm lịch sử]
    W --> R[Tra ChromaDB bằng câu mới + câu người dùng trước đó<br/>Retriever.retrieve]
    R --> E{Có retriever<br/>và web_search_enabled?}
    E -- Không --> REG
    E -- Có --> Q1[router_score:<br/>điểm cosine cao nhất của câu mới nhất]

    Q1 --> QR{quick_route - không cần LLM}
    QR -- "Chào hỏi ngắn" --> SMALL
    QR -- "Nêu 'Điều N' hoặc có ĐTBCTL, ĐTBCHK, cảnh báo học tập..." --> REG
    QR -- "Điểm >= 0,75" --> REG
    QR -- "Còn mơ hồ" --> LLM[Gọi LLM phân loại<br/>CLASSIFY_PROMPT]
    LLM -- "regulation" --> REG
    LLM -- "external" --> EXT
    LLM -- "offtopic" --> OFF
    LLM -- "smalltalk" --> SMALL
    LLM -- "Lỗi hoặc đầu ra lạ" --> REG

    subgraph REGB [Tuyến regulation: quy chế học vụ]
        REG[regulation] --> GPA[gpa_assist: trích số liệu, tính điểm bằng mã Python]
        GPA --> RP[SYSTEM_PROMPT + NGỮ CẢNH là các Điều lấy từ ChromaDB + KẾT QUẢ TÍNH SẴN]
        RP --> RT[Công cụ: calculate, compare_numbers]
    end

    subgraph EXTB [Tuyến external: ngoài quy chế]
        EXT[external] --> EP[WEB_PROMPT, bỏ ngữ cảnh ChromaDB]
        EP --> ET[Công cụ: web_search, ưu tiên ctu.edu.vn]
    end

    subgraph OFFB [Tuyến offtopic]
        OFF[offtopic] --> OP[OFFTOPIC_PROMPT: từ chối lịch sự, không tìm web]
    end

    subgraph SMB [Tuyến smalltalk]
        SMALL[smalltalk] --> SP[SMALLTALK_PROMPT: đáp ngắn]
    end

    RT --> GEN[Gemini stream câu trả lời]
    ET --> GEN
    OP --> GEN
    SP --> GEN
    GEN --> O([Tin nhắn trả lời kèm nguồn: Điều N hoặc link web])
```

## 3. Bảng tóm tắt các tuyến

| Tuyến | Khi nào | Dùng ChromaDB | Công cụ | Nguồn trích dẫn |
|---|---|---|---|---|
| `regulation` | Hỏi quy chế học vụ (tín chỉ, điểm, học bổng, cảnh báo học tập, tốt nghiệp...) | Có: đưa các Điều liên quan vào prompt | `calculate`, `compare_numbers` | "Điều N" |
| `external` | Về trường hoặc việc học nhưng ngoài quy chế (học phí cụ thể, lịch thi, ký túc xá, tuyển sinh...) | Không (đã tra nhưng bỏ kết quả) | `web_search` | Link web `[n]` |
| `offtopic` | Không liên quan học vụ hoặc trường | Không | Không | Không |
| `smalltalk` | Chào hỏi, cảm ơn, hỏi bot là ai | Không | Không | Không |

## 4. Những điểm cần nhớ

- **Mọi lỗi của router đều rơi về `regulation`** (hành vi an toàn, dùng RAG như mặc định).
- **Tra ChromaDB luôn chạy trước router.** Nếu tra lỗi (ví dụ hết quota embedding) thì vẫn trả lời, chỉ là không có ngữ cảnh.
- **Có hai chỗ "chào hỏi"**: chào ngắn có sẵn đáp án được chặn từ lớp API (`smalltalk.lookup`, không gọi LLM); các câu chào
  còn lại nếu lọt vào graph sẽ được router đưa sang tuyến `smalltalk` và vẫn gọi LLM.
- Khi `web_search_enabled = false` hoặc không có retriever thì không chạy router, mọi câu đi tuyến `regulation`.
- Router chỉ có 1 tuyến "trong phạm vi" (quy chế học vụ). Thêm tài liệu/nhóm mới nghĩa là thêm một giá trị route vào
  `scope.ROUTES`, cập nhật `CLASSIFY_PROMPT` và thêm một nhánh trong `graph.py`.
