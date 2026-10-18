"""Chia sẻ cuộc trò chuyện: mời theo email, liên kết công khai, xem/chat tiếp trên cuộc trò chuyện được chia sẻ."""

import uuid
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_chat_graph, get_current_user, get_optional_user
from app.api.v1.conversations import stream_response
from app.db.session import get_db, get_sessionmaker
from app.models import Conversation, ConversationShare, User
from app.schemas.conversation import ChatMessageOut, SendMessageIn
from app.services import sharing
from app.services.chat.service import get_history

owner_router = APIRouter(prefix="/conversations/{conversation_id}/shares", tags=["shares"])
router = APIRouter(prefix="/shares", tags=["shares"])
public_router = APIRouter(prefix="/shared-links", tags=["shares"])

Permission = Literal["view", "chat"]


class PersonIn(BaseModel):
    email: str = Field(max_length=320)
    permission: Permission = "view"


class PermissionIn(BaseModel):
    permission: Permission


class LinkIn(BaseModel):
    permission: Permission = "view"
    regenerate: bool = False  # true: đổi liên kết mới, liên kết cũ hết hiệu lực


def _owned(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def _error(exc: sharing.ShareError) -> HTTPException:
    return HTTPException(422, detail=exc.code)


def _person(db: Session, share: ConversationShare) -> dict:
    user = db.scalar(select(User).where(User.email == share.email))
    return {
        "id": str(share.id),
        "email": share.email,
        "name": user.name if user else None,
        "registered": user is not None,  # chưa từng đăng nhập thì chỉ là lời mời, người đó đăng nhập là thấy
        "permission": share.permission,
        "created_at": share.created_at.isoformat() if share.created_at else None,
    }


def _link(share: ConversationShare | None) -> dict | None:
    if share is None:
        return None
    return {"token": share.token, "permission": share.permission, "created_at": share.created_at.isoformat() if share.created_at else None}


def _state(db: Session, conv: Conversation) -> dict:
    people = db.scalars(
        select(ConversationShare)
        .where(ConversationShare.conversation_id == conv.id, ConversationShare.kind == "email")
        .order_by(ConversationShare.created_at)
    ).all()
    return {"link": _link(sharing.link_share(db, conv.id)), "people": [_person(db, p) for p in people]}


# ---- chủ cuộc trò chuyện quản lý chia sẻ ----


@owner_router.get("")
def get_shares(conversation_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _state(db, _owned(db, user, conversation_id))


@owner_router.post("/people")
def add_person(
    conversation_id: uuid.UUID, body: PersonIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    conv = _owned(db, user, conversation_id)
    try:
        share = sharing.add_person(db, conv, user, body.email, body.permission)
    except sharing.ShareError as exc:
        raise _error(exc) from None
    return _person(db, share)


@owner_router.patch("/people/{share_id}")
def update_person(
    conversation_id: uuid.UUID,
    share_id: uuid.UUID,
    body: PermissionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    conv = _owned(db, user, conversation_id)
    share = db.get(ConversationShare, share_id)
    if share is None or share.conversation_id != conv.id or share.kind != "email":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Share not found")
    share.permission = body.permission
    db.commit()
    db.refresh(share)
    return _person(db, share)


@owner_router.delete("/people/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_person(
    conversation_id: uuid.UUID, share_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    conv = _owned(db, user, conversation_id)
    share = db.get(ConversationShare, share_id)
    if share is None or share.conversation_id != conv.id or share.kind != "email":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Share not found")
    db.delete(share)
    db.commit()


@owner_router.put("/link")
def put_link(
    conversation_id: uuid.UUID, body: LinkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Bật liên kết chia sẻ công khai (hoặc đổi quyền / đổi liên kết mới)."""
    conv = _owned(db, user, conversation_id)
    try:
        share = sharing.set_link(db, conv, user, body.permission, body.regenerate)
    except sharing.ShareError as exc:
        raise _error(exc) from None
    return _link(share)  # type: ignore[return-value]


@owner_router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(conversation_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """Tắt liên kết chia sẻ: liên kết cũ không dùng được nữa."""
    conv = _owned(db, user, conversation_id)
    share = sharing.link_share(db, conv.id)
    if share is not None:
        db.delete(share)
        db.commit()


# ---- tìm người để mời / danh sách được chia sẻ với tôi ----


@router.get("/suggestions")
def suggest_people(
    q: str = Query("", max_length=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    """Gợi ý người dùng theo email/tên khi gõ ô mời (cần ít nhất 2 ký tự; tối đa 8 kết quả; không gồm chính mình)."""
    needle = q.strip().lower()
    if len(needle) < 2:
        return []
    like = f"%{needle}%"
    rows = db.scalars(
        select(User)
        .where(User.id != user.id, User.is_active.is_(True), or_(func.lower(User.email).like(like), func.lower(User.name).like(like)))
        .order_by(User.email)
        .limit(8)
    ).all()
    return [{"email": u.email, "name": u.name} for u in rows]


@router.get("/with-me")
def shared_with_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": str(item.conversation_id),
            "title": item.title,
            "owner_name": item.owner_name,
            "permission": item.permission,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
        for item in sharing.shared_with(db, user)
    ]


# ---- xem / chat tiếp qua liên kết chia sẻ ----


def _resolve(db: Session, token: str) -> tuple[Conversation, ConversationShare]:
    found = sharing.resolve_token(db, token)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found")
    return found


@public_router.get("/{token}")
def view_shared_link(
    token: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
    graph=Depends(get_chat_graph),
) -> dict:
    """Xem cuộc trò chuyện qua liên kết (không cần đăng nhập). `can_chat` cho FE biết có hiện ô chat không."""
    conv, share = _resolve(db, token)
    owner = db.get(User, conv.user_id)
    messages = get_history(graph, conv.id)
    return {
        "title": conv.title,
        "owner_name": sharing.display_name(owner) if owner else "",
        "permission": share.permission,
        "can_chat": user is not None and share.permission == "chat",
        "is_owner": user is not None and user.id == conv.user_id,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        "messages": [ChatMessageOut(**asdict(m)).model_dump() for m in messages],
    }


@public_router.post("/{token}/messages/stream")
def chat_via_link(
    token: str,
    body: SendMessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    graph=Depends(get_chat_graph),
    sessionmaker=Depends(get_sessionmaker),
):
    """Chat tiếp qua liên kết: chỉ khi liên kết có quyền 'chat' và người gửi đã đăng nhập bằng email CTU."""
    conv, share = _resolve(db, token)
    if share.permission != "chat":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="READ_ONLY")
    author = None if conv.user_id == user.id else sharing.display_name(user)
    return stream_response(db, user, conv, body, graph, sessionmaker, author=author)
