from pydantic import BaseModel, EmailStr

from app.schemas.user import UserOut


class DevLoginIn(BaseModel):
    email: EmailStr


class GoogleLoginIn(BaseModel):
    """`credential` là Google ID token mà Google Identity Services trả về ở FE."""

    credential: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str  # JWT, sống 7 ngày
    refresh_token: str  # chuỗi ngẫu nhiên, sống 30 ngày, dùng 1 lần rồi đổi cái mới
    token_type: str = "bearer"
    user: UserOut
