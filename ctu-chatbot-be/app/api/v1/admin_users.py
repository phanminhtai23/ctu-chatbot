import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models import Conversation, RefreshToken, UsageEvent, User, UserFile
from app.services import user_files
from app.services.usage import user_activity

router = APIRouter(prefix="/admin/users", tags=["admin"])


class UserPatch(BaseModel):
    is_active: bool | None = None
    role: Literal["user", "admin"] | None = None


def _row(user: User, messages: int, conversations: int, last_active: datetime | None, storage_bytes: int = 0) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar,
        "storage_bytes": storage_bytes,
        "storage_quota_bytes": user_files.quota_bytes(),
        "role": user.role,
        "admin_by_env": user.email in settings.admin_email_set,
        "is_active": user.is_active,
        "spam_count": user.spam_count or 0,
        "profanity_count": user.profanity_count or 0,
        "created_at": user.created_at.isoformat(),
        "messages": messages,
        "conversations": conversations,
        "last_active": last_active.isoformat() if last_active else None,
    }


SortKey = Literal["name", "role", "state", "created", "last_active", "messages", "storage", "spam", "profanity"]


@router.get("")
def list_users(
    q: str = Query("", max_length=100),
    role: Literal["all", "user", "admin"] = "all",
    state: Literal["all", "active", "disabled"] = "all",
    sort: SortKey = "created",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Danh sách tài khoản kèm số lượt hỏi, số cuộc trò chuyện, dung lượng và lần dùng gần nhất; sắp xếp theo cột được chọn."""
    conditions = []
    if q.strip():
        like = f"%{q.strip().lower()}%"
        conditions.append(or_(func.lower(User.email).like(like), func.lower(User.name).like(like)))
    if role != "all":
        conditions.append(User.role == role)
    if state != "all":
        conditions.append(User.is_active.is_(state == "active"))

    usage = (
        select(UsageEvent.user_id.label("uid"), func.count().label("msgs"), func.max(UsageEvent.created_at).label("last"))
        .group_by(UsageEvent.user_id)
        .subquery()
    )
    files = (
        select(UserFile.user_id.label("uid"), func.sum(UserFile.size_bytes).label("bytes")).group_by(UserFile.user_id).subquery()
    )
    sort_columns = {
        "name": func.lower(func.coalesce(func.nullif(User.name, ""), User.email)),
        "role": User.role,
        "state": User.is_active,
        "created": User.created_at,
        "last_active": usage.c.last,
        "messages": func.coalesce(usage.c.msgs, 0),
        "storage": func.coalesce(files.c.bytes, 0),
        "spam": User.spam_count,
        "profanity": User.profanity_count,
    }
    column = sort_columns[sort]
    direction = column.asc() if order == "asc" else column.desc()
    if sort == "last_active":
        direction = direction.nulls_last()  # người chưa từng dùng luôn xuống cuối, dù tăng hay giảm

    total = db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    users = db.scalars(
        select(User)
        .outerjoin(usage, usage.c.uid == User.id)
        .outerjoin(files, files.c.uid == User.id)
        .where(*conditions)
        .order_by(direction, User.created_at.desc(), User.id)
        .offset(offset)
        .limit(limit)
    ).all()
    ids = [u.id for u in users]
    msgs = {
        r[0]: (r[1], r[2])
        for r in db.execute(
            select(UsageEvent.user_id, func.count(), func.max(UsageEvent.created_at))
            .where(UsageEvent.user_id.in_(ids))
            .group_by(UsageEvent.user_id)
        ).all()
    }
    convs = dict(
        db.execute(
            select(Conversation.user_id, func.count()).where(Conversation.user_id.in_(ids)).group_by(Conversation.user_id)
        ).all()
    )
    storage = dict(
        db.execute(
            select(UserFile.user_id, func.sum(UserFile.size_bytes)).where(UserFile.user_id.in_(ids)).group_by(UserFile.user_id)
        ).all()
    )
    return {
        "total": total,
        "items": [
            _row(u, msgs.get(u.id, (0, None))[0], convs.get(u.id, 0), msgs.get(u.id, (0, None))[1], int(storage.get(u.id, 0)))
            for u in users
        ],
    }


@router.get("/{user_id}")
def get_user(user_id: uuid.UUID, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    activity = user_activity(db, user.id)
    return {
        **_row(user, activity["messages"], activity["conversations"], None, user_files.used_bytes(db, user.id)),
        "last_active": activity["last_active"],
        "first_active": activity["first_active"],
        "daily": activity["daily"],
        "birthday": user.birthday.isoformat() if user.birthday else None,
        "timezone": user.timezone,
    }


def _other_active_admins(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True), User.id != user.id)
    ) or 0


@router.patch("/{user_id}")
def update_user(
    user_id: uuid.UUID,
    body: UserPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Khoá/mở khoá tài khoản (revoke) hoặc đổi quyền. Có các chốt chặn để admin không tự khoá mình."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == admin.id and (body.is_active is False or body.role == "user"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="CANNOT_CHANGE_SELF")
    demoting = body.role == "user" and user.role == "admin"
    disabling = body.is_active is False and user.is_active
    if demoting and user.email in settings.admin_email_set:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="ADMIN_BY_ENV")  # .env sẽ nâng lại ở lần đăng nhập sau
    if user.role == "admin" and (demoting or disabling) and _other_active_admins(db, user) == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="LAST_ADMIN")

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
        if disabling:
            # Access token cũ bị chặn ngay vì get_current_user kiểm tra is_active; thu hồi luôn refresh token.
            now = datetime.now(timezone.utc)
            for token in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))):
                token.revoked_at = now
    db.commit()
    db.refresh(user)
    activity = user_activity(db, user.id, days=1)
    return _row(user, activity["messages"], activity["conversations"], None) | {"last_active": activity["last_active"]}
