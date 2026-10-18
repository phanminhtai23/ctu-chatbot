from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql://ctu:ctu_dev_password@localhost:5433/ctu_chatbot"
    deepseek_api_key: str = ""

    # LLM (Gemini). Điền key vào GEMINI_API_KEY_1..9 trong .env; hết hạn mức thì tự xoay sang key kế tiếp.
    llm_model: str = "gemini-3.5-flash-lite"
    gemini_api_key: str = ""  # key đơn (tuỳ chọn, được tính như key đầu tiên)
    gemini_api_key_1: str = ""
    gemini_api_key_2: str = ""
    gemini_api_key_3: str = ""
    gemini_api_key_4: str = ""
    gemini_api_key_5: str = ""
    gemini_api_key_6: str = ""
    gemini_api_key_7: str = ""
    gemini_api_key_8: str = ""
    gemini_api_key_9: str = ""
    llm_timeout_seconds: float = 60
    llm_key_cooldown_seconds: int = 60  # key bị 429 thì nghỉ chừng này giây (nếu Gemini không báo thời gian chờ)
    chat_history_window: int = 30  # số tin nhắn gần nhất gửi cho LLM; toàn bộ lịch sử vẫn nằm trong checkpoint

    # Giới hạn chat: mỗi user tối đa `chat_rate_limit_max` tin trong `chat_rate_limit_window_seconds` giây.
    chat_rate_limit_max: int = 10
    chat_rate_limit_window_seconds: int = 300

    # RAG: văn bản quy chế -> chunk theo Điều -> embedding Gemini -> ChromaDB (nhúng, không cần server).
    embedding_model: str = "models/gemini-embedding-2"
    embedding_model_api_key: str = ""  # rỗng thì dùng key Gemini đầu tiên
    embedding_dim: int = 768
    rag_source_path: str = ""  # rỗng = vector-docs/qd3266-clean.md ở thư mục gốc dự án
    chroma_path: str = "chroma_db"  # tương đối so với thư mục ctu-chatbot-be
    rag_top_k: int = 5

    # Guardrail phạm vi + tìm web: câu hỏi ngoài quy chế thì bot tự tìm trên web (DuckDuckGo). false = luôn dùng RAG.
    web_search_enabled: bool = True

    # Hàng đợi lượt chat: tối đa `chat_max_concurrent` lượt chạy cùng lúc (mỗi lượt giữ 1 luồng + gọi LLM),
    # tối đa `chat_queue_max_waiting` lượt xếp hàng chờ; vượt quá thì trả 503 kèm Retry-After thay vì làm sập server.
    chat_max_concurrent: int = 4
    chat_queue_max_waiting: int = 30
    chat_queue_wait_seconds: int = 120  # chờ quá lâu trong hàng thì bỏ cuộc (báo QUEUE_TIMEOUT)

    # Admin nạp tài liệu mới: PDF -> OCR -> chuẩn hóa -> chunk theo Điều -> embedding -> vị trí trên trang -> test -> kích hoạt.
    document_ingest_enabled: bool = True  # false = tắt hẳn các endpoint nạp tài liệu (ví dụ ở production)
    documents_dir: str = "data/documents"  # tương đối so với ctu-chatbot-be; mỗi lần nạp là một thư mục phiên bản
    ingest_model: str = "gemini-3.5-flash"  # model đọc ảnh trang (OCR + khoanh vị trí Điều)
    ingest_ocr_pages_per_call: int = 5  # Gemini hay từ chối khi gửi cả file dài: chia nhóm trang nhỏ
    ingest_call_interval_seconds: float = 4.0  # giãn cách giữa các lần gọi Gemini để không vượt hạn mức free
    ingest_max_pdf_mb: int = 30
    ingest_keep_versions: int = 10  # giữ tối đa chừng này phiên bản đã nạp (để chuyển qua lại); bản đang dùng luôn được giữ
    ingest_max_pages: int = 80
    ingest_min_retrieval_pass: float = 0.9  # tỉ lệ Điều tự truy xuất lại đúng ở bước test để được kích hoạt


    # OAuth Client ID (Web application) tạo ở Google Cloud Console. Rỗng = tắt đăng nhập Google.
    google_client_id: str = ""

    # JWT. Đổi secret_key ở mọi môi trường không phải dev.
    secret_key: str = "dev-only-change-me-dev-only-change-me-0000"
    access_token_expire_minutes: int = 60 * 24 * 7  # access token: 7 ngày
    refresh_token_expire_days: int = 30  # refresh token: 30 ngày

    # Tên miền email được phép đăng nhập (khớp domain chính xác hoặc subdomain).
    # Đặt ALLOWED_EMAIL_DOMAINS=[] trong .env để cho MỌI email đăng nhập (chỉ khi test).
    # CHƯA CHỐT: brainstorm ghi ".edu.ctu.vn" nhưng email sinh viên thật là "@student.ctu.edu.vn".
    allowed_email_domains: list[str] = ["ctu.edu.vn", "edu.ctu.vn"]

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]


    @property
    def gemini_api_keys(self) -> list[str]:
        """Các key đã điền, theo thứ tự, bỏ trùng và bỏ ô trống."""
        candidates = [
            self.gemini_api_key,
            self.gemini_api_key_1,
            self.gemini_api_key_2,
            self.gemini_api_key_3,
            self.gemini_api_key_4,
            self.gemini_api_key_5,
            self.gemini_api_key_6,
            self.gemini_api_key_7,
            self.gemini_api_key_8,
            self.gemini_api_key_9,
        ]
        return list(dict.fromkeys(k.strip() for k in candidates if k and k.strip()))


settings = Settings()
