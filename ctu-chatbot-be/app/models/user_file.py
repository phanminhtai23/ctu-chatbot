import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserFile(Base):
    """Một file người dùng đã tải lên (nội dung nằm trên Cloudinary, ở đây chỉ giữ thông tin để tính dung lượng và xoá)."""

    __tablename__ = "user_files"
    __table_args__ = (CheckConstraint("kind IN ('avatar', 'attachment')", name="ck_user_files_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # 'avatar' (mỗi người tối đa 1) | 'attachment'
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    public_id: Mapped[str] = mapped_column(String(300))
    resource_type: Mapped[str] = mapped_column(String(10))  # 'image' | 'raw' (cách Cloudinary phân loại)
    delivery_type: Mapped[str] = mapped_column(String(15))  # 'upload' (công khai) | 'authenticated' (URL có chữ ký)
    url: Mapped[str] = mapped_column(String(600))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
