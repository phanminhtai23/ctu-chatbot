import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


def generate_refresh_token() -> str:
    """Chuỗi ngẫu nhiên không đoán được (384 bit); không phải JWT nên không tự mang thông tin."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    # Token đã đủ ngẫu nhiên nên sha256 là đủ (không cần bcrypt chậm như mật khẩu).
    return hashlib.sha256(token.encode()).hexdigest()


def decode_access_token(token: str) -> str | None:
    """Trả về user_id nếu token hợp lệ, ngược lại None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None
