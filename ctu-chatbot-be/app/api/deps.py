import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.access import can_access
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized
    try:
        user = db.get(User, uuid.UUID(user_id))
    except ValueError:
        raise unauthorized from None
    if user is None:
        raise unauthorized
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    # Token cấp từ trước khi siết tên miền cũng phải mất hiệu lực với tài khoản không còn được phép.
    if not can_access(user.email, user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email domain is not allowed")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Người dùng đã đăng nhập hợp lệ, hoặc None (khách). Dùng cho trang công khai có thêm tính năng khi đã đăng nhập."""
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


def get_ingest_manager(request: Request):
    """Bộ điều phối các lần nạp tài liệu (dựng một lần lúc khởi động app)."""
    return request.app.state.ingest_manager


def get_document_catalog(request: Request):
    """Quy trình version tài liệu trong vector-docs và đồng bộ Chroma."""
    return request.app.state.document_catalog


def get_chat_graph(request: Request):
    """Đồ thị LangGraph (đã gắn checkpointer Postgres) được dựng một lần lúc khởi động app."""
    return request.app.state.chat_graph


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user
