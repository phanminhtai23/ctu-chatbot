import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("type IN ('answer_issue', 'general')", name="ck_feedback_type"),
        CheckConstraint(
            "category IN ('wrong_answer', 'wrong_citation', 'outdated', 'bug', 'suggestion', 'other')",
            name="ck_feedback_category",
        ),
        CheckConstraint("status IN ('new', 'reviewed', 'resolved')", name="ck_feedback_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, default="")
    # Không đặt FK: nội dung hội thoại nằm trong checkpoint LangGraph.
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Bản chụp câu hỏi + câu trả lời bị báo cáo (còn xem được kể cả khi người dùng xoá cuộc trò chuyện).
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
