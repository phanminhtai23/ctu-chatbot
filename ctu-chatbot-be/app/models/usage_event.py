import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageEvent(Base):
    """Mỗi lượt hỏi-đáp thành công của một user, để thống kê tần suất sử dụng cho admin.

    Nội dung tin nhắn KHÔNG lưu ở đây (nằm trong checkpoint LangGraph); chỉ ghi ai hỏi, ở cuộc trò chuyện nào, lúc nào.
    Không tự xoá khi cuộc trò chuyện bị xoá (conversation_id không có khoá ngoại) để thống kê không bị tụt.
    """

    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # câu hỏi gợi ý có sẵn đáp án
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
