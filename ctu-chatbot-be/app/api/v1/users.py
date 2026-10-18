from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserOut, UserUpdate

router = APIRouter(prefix="/me", tags=["users"])


@router.get("", response_model=UserOut)
def read_me(user: User = Depends(get_current_user)):
    return user


@router.post("/welcome", response_model=UserOut)
def mark_welcomed(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Đánh dấu đã chào mừng người dùng mới (gọi khi hộp thoại chào mừng hiện ra); gọi lại không đổi gì."""
    if user.welcomed_at is None:
        user.welcomed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
    return user


@router.patch("", response_model=UserOut)
def update_me(
    body: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # exclude_unset: field không gửi lên thì giữ nguyên; birthday=null thì xoá ngày sinh.
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is None and field != "birthday":
            continue  # không cho set null các cột bắt buộc
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user
