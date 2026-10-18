import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.avatar import default_avatar_url
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
    # Ảnh đại diện người dùng ĐÃ CHỌN: ảnh tải lên (Cloudinary) hoặc ảnh ngẫu nhiên (DiceBear). NULL = dùng ảnh mặc định (xem `default_avatar`).
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Ảnh gốc của tài khoản Google, cập nhật mỗi lần đăng nhập Google. Là ảnh MẶC ĐỊNH nếu có (nút "Mặc định" quay về ảnh này).
    google_picture: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Cài đặt cá nhân, lưu theo user.
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    language: Mapped[str] = mapped_column(String(2), default="vi")
    theme: Mapped[str] = mapped_column(String(10), default="system")

    # Phân quyền. Mọi tài khoản mới là 'user'; nâng lên 'admin' bằng cách sửa trực tiếp trong DB.
    role: Mapped[str] = mapped_column(String(10), default="user", server_default="user")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Lúc người dùng được chào mừng lần đầu (hộp thoại pháo hoa sau khi đăng ký). None = chưa chào mừng.
    welcomed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def default_avatar(self) -> str:
        """Ảnh mặc định của tài khoản: ảnh Google gốc nếu có, không thì ảnh ngộ nghĩnh cố định theo id."""
        return self.google_picture or default_avatar_url(str(self.id))

    @property
    def avatar(self) -> str:
        return self.avatar_url or self.default_avatar

    @property
    def welcomed(self) -> bool:
        return self.welcomed_at is not None

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
