from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.access import can_access
from app.core.config import settings
from app.core.security import create_access_token, generate_refresh_token, hash_refresh_token
from app.models import RefreshToken, User
from app.schemas.auth import TokenOut

# Hai tab/hai request cùng làm mới một lúc sẽ cùng dùng token cũ; trong khoảng này coi là "đua nhau"
# chứ không phải bị đánh cắp, nên chỉ từ chối chứ không thu hồi toàn bộ phiên.
REUSE_GRACE = timedelta(seconds=30)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    # SQLite (dùng trong test) trả datetime không có múi giờ; Postgres thì có.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail)


def issue_tokens(db: Session, user: User) -> TokenOut:
    """Cấp cặp token mới: access (7 ngày) + refresh (30 ngày, lưu băm trong DB)."""
    refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh),
            expires_at=_utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(str(user.id)), refresh_token=refresh, user=user)


def rotate_refresh_token(db: Session, raw_token: str) -> TokenOut:
    """Đổi refresh token cũ lấy cặp token mới; token cũ bị vô hiệu ngay (dùng một lần)."""
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)))
    if row is None:
        raise _unauthorized("Invalid refresh token")

    now = _utcnow()
    if row.revoked_at is not None:
        if now - _aware(row.revoked_at) > REUSE_GRACE:
            # Token đã dùng/thu hồi từ lâu mà vẫn bị đem ra dùng: nghi bị đánh cắp -> đăng xuất mọi thiết bị.
            db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            db.commit()
        raise _unauthorized("Refresh token revoked")
    if _aware(row.expires_at) <= now:
        raise _unauthorized("Refresh token expired")

    user = db.get(User, row.user_id)
    if user is None:
        raise _unauthorized("Invalid refresh token")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    if not can_access(user.email, user.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Email domain is not allowed")

    row.revoked_at = now
    return issue_tokens(db, user)  # commit chung với việc thu hồi token cũ


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    """Đăng xuất: thu hồi refresh token. Idempotent — token lạ/đã thu hồi thì bỏ qua."""
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = _utcnow()
        db.commit()
