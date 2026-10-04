import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("language IN ('vi', 'en')", name="ck_users_language"),
        CheckConstraint("theme IN ('system', 'light', 'dark')", name="ck_users_theme"),
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Cột sẵn cho avatar; upload chưa làm (chưa chốt nơi lưu file).
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Cài đặt cá nhân, lưu theo user.
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    language: Mapped[str] = mapped_column(String(2), default="vi")
    theme: Mapped[str] = mapped_column(String(10), default="system")

    # Phân quyền. Mọi tài khoản mới là 'user'; nâng lên 'admin' bằng cách sửa trực tiếp trong DB.
    role: Mapped[str] = mapped_column(String(10), default="user", server_default="user")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
