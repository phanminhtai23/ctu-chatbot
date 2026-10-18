import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationShare(Base):
    """Một cách chia sẻ cuộc trò chuyện của chủ sở hữu.

    - kind='email': chia sẻ cho một địa chỉ email (người đó phải đăng nhập bằng đúng email này mới xem được);
    - kind='link': một liên kết công khai (mỗi cuộc trò chuyện tối đa một liên kết), ai có liên kết cũng xem được.
    `permission`: 'view' = chỉ đọc; 'chat' = có thể chat tiếp (người nhận phải đăng nhập bằng email CTU).
    """

    __tablename__ = "conversation_shares"
    __table_args__ = (
        CheckConstraint("kind IN ('email', 'link')", name="ck_conversation_shares_kind"),
        CheckConstraint("permission IN ('view', 'chat')", name="ck_conversation_shares_permission"),
        UniqueConstraint("conversation_id", "email", name="uq_conversation_shares_conversation_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(5))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)  # chữ thường
    token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    permission: Mapped[str] = mapped_column(String(5), default="view")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
