from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import can_access, is_domain_allowed
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.schemas.auth import DevLoginIn, GoogleLoginIn, RefreshIn, TokenOut
from app.services.auth_tokens import issue_tokens, revoke_refresh_token, rotate_refresh_token
from app.services.google_auth import GoogleAuthError, verify_google_id_token

router = APIRouter(prefix="/auth", tags=["auth"])

DOMAIN_NOT_ALLOWED = "Email domain is not allowed"


def _login(
    db: Session, email: str, *, name: str, avatar_url: str | None = None
) -> TokenOut:
    """Chung cho mọi cách đăng nhập: chặn domain lạ, tạo user nếu chưa có, cấp JWT."""
    email = email.lower()
    is_admin_email = email in settings.admin_email_set  # khai báo trong .env (ADMIN_EMAILS)

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        # Tài khoản mới là 'user' nên phải thuộc tên miền được phép; email admin trong .env được miễn.
        if not is_admin_email and not is_domain_allowed(email):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=DOMAIN_NOT_ALLOWED)
        user = User(email=email, name=name, avatar_url=avatar_url, role="admin" if is_admin_email else "user")
        db.add(user)
        db.commit()
        db.refresh(user)
    elif is_admin_email and user.role != "admin":
        user.role = "admin"  # nâng quyền theo .env; bỏ email khỏi .env KHÔNG tự hạ quyền (tránh tự khoá mình)
        db.commit()
        db.refresh(user)
    elif not can_access(user.email, user.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=DOMAIN_NOT_ALLOWED)

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    return issue_tokens(db, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    """Đổi refresh token (còn hạn, chưa dùng) lấy access + refresh token mới."""
    return rotate_refresh_token(db, body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    """Thu hồi refresh token. Không cần access token (có thể đã hết hạn)."""
    revoke_refresh_token(db, body.refresh_token)


@router.post("/google", response_model=TokenOut)
def google_login(body: GoogleLoginIn, db: Session = Depends(get_db)):
    """Đăng nhập bằng Google ID token. Tài khoản mới mặc định role 'user'."""
    if not settings.google_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google login is not configured")
    try:
        identity = verify_google_id_token(body.credential)
    except GoogleAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _login(db, identity.email, name=identity.name, avatar_url=identity.picture)


@router.post("/dev-login", response_model=TokenOut)
def dev_login(body: DevLoginIn, db: Session = Depends(get_db)):
    """Đăng nhập không cần Google, CHỈ cho môi trường dev (404 khi ENV != dev)."""
    if settings.env != "dev":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    return _login(db, body.email, name=body.email.split("@")[0])
