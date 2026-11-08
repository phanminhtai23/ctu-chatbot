import re
import uuid
from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

Language = Literal["vi", "en"]
Theme = Literal["system", "light", "dark"]
Role = Literal["user", "admin"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    birthday: date | None
    avatar_url: str = Field(validation_alias=AliasChoices("avatar", "avatar_url"))  # luôn có ảnh (mặc định ngẫu nhiên nếu chưa đặt)
    role: Role
    timezone: str
    language: Language
    theme: Theme
    welcomed: bool = False  # đã hiện hộp thoại chào mừng lần đầu chưa (false = tài khoản mới, cần chào mừng)
    document_routes: list[str] | None = None  # tuyến tài liệu người dùng chọn để hỏi; None = tất cả


class UserUpdate(BaseModel):
    """PATCH /me — chỉ field nào được gửi lên mới được cập nhật."""

    name: str | None = None
    birthday: date | None = None
    timezone: str | None = None
    language: Language | None = None
    theme: Theme | None = None
    # Gửi null = quay về "tất cả"; gửi danh sách = chỉ tra cứu các tuyến này (ít nhất một).
    document_routes: list[str] | None = None

    @field_validator("document_routes")
    @classmethod
    def _document_routes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        ids = list(dict.fromkeys(v))
        if not 1 <= len(ids) <= 50 or not all(re.fullmatch(r"[a-z][a-z0-9-]{1,39}", i) for i in ids):
            raise ValueError("document_routes must list 1-50 valid route ids")
        return ids

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) > 100:
            raise ValueError("name must be at most 100 characters")
        return v

    @field_validator("birthday")
    @classmethod
    def _birthday(cls, v: date | None) -> date | None:
        if v is None:
            return v
        if v > date.today() or v.year < 1900:
            raise ValueError("birthday is out of range")
        return v

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError("unknown IANA timezone") from None
        return v
