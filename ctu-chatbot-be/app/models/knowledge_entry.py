import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeEntry(Base):
    """Một mục hỏi-đáp do admin nhập. Phải được "embedding" thì chatbot mới tra cứu được (vector nằm trong ChromaDB)."""

    __tablename__ = "knowledge_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    # Băm của câu hỏi đã chuẩn hoá (không phân biệt hoa thường / khoảng trắng): chặn nhập trùng.
    question_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Băm của (câu hỏi + câu trả lời) lúc embedding gần nhất. Khác băm hiện tại = nội dung đã đổi, cần embedding lại.
    embedded_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
