"""Chia sẻ cuộc trò chuyện: ai được xem, ai được chat tiếp.

Quy tắc:
- Chủ sở hữu luôn có toàn quyền (xem, chat, đổi tên, xoá, quản lý chia sẻ).
- Chia sẻ theo email: người nhận đăng nhập bằng ĐÚNG email đó thì xem được; có quyền 'chat' thì chat tiếp được.
- Chia sẻ bằng liên kết: ai có liên kết cũng XEM được (không cần đăng nhập). Chat tiếp chỉ khi liên kết có quyền 'chat'
  VÀ người đó đăng nhập bằng email CTU (đăng nhập thành công nghĩa là email đã qua kiểm tra tên miền).
- Admin không tự động xem được cuộc trò chuyện của người khác.
"""

import re
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import is_domain_allowed
from app.core.config import settings
from app.models import Conversation, ConversationShare, User

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PERMISSIONS = ("view", "chat")
OWNER, CHAT, VIEW = "owner", "chat", "view"


class ShareError(Exception):
    """Lỗi nghiệp vụ khi chia sẻ; `code` là mã ổn định để FE hiện đúng thông báo."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def normalize_email(email: str) -> str:
    return email.strip().lower()


def can_receive_by_email(db: Session, email: str) -> bool:
    """Email này có đăng nhập được vào hệ thống không (tên miền CTU, admin theo .env hoặc tài khoản admin đã có)?"""
    if is_domain_allowed(email) or email in settings.admin_email_set:
        return True
    user = db.scalar(select(User).where(User.email == email))
    return user is not None and user.role == "admin"


def access_level(db: Session, user: User, conv: Conversation) -> str | None:
    """'owner' | 'chat' | 'view' | None (không có quyền)."""
    if conv.user_id == user.id:
        return OWNER
    share = db.scalar(
        select(ConversationShare).where(
            ConversationShare.conversation_id == conv.id,
            ConversationShare.kind == "email",
            ConversationShare.email == user.email.lower(),
        )
    )
    return share.permission if share else None


def link_share(db: Session, conversation_id: uuid.UUID) -> ConversationShare | None:
    return db.scalar(
        select(ConversationShare).where(ConversationShare.conversation_id == conversation_id, ConversationShare.kind == "link")
    )


def resolve_token(db: Session, token: str) -> tuple[Conversation, ConversationShare] | None:
    if not token or len(token) > 64:
        return None
    share = db.scalar(select(ConversationShare).where(ConversationShare.token == token, ConversationShare.kind == "link"))
    if share is None:
        return None
    conv = db.get(Conversation, share.conversation_id)
    return (conv, share) if conv is not None else None


def add_person(db: Session, conv: Conversation, owner: User, email: str, permission: str) -> ConversationShare:
    email = normalize_email(email)
    if permission not in PERMISSIONS:
        raise ShareError("INVALID_PERMISSION")
    if not EMAIL_RE.match(email) or len(email) > 320:
        raise ShareError("INVALID_EMAIL")
    if email == owner.email.lower():
        raise ShareError("CANNOT_SHARE_WITH_SELF")
    if not can_receive_by_email(db, email):
        raise ShareError("EMAIL_NOT_ALLOWED")  # email ngoài trường không đăng nhập được nên chia sẻ cũng vô ích
    share = db.scalar(
        select(ConversationShare).where(
            ConversationShare.conversation_id == conv.id, ConversationShare.kind == "email", ConversationShare.email == email
        )
    )
    if share is None:
        share = ConversationShare(conversation_id=conv.id, kind="email", email=email, permission=permission, created_by=owner.id)
        db.add(share)
    else:
        share.permission = permission
    db.commit()
    db.refresh(share)
    return share


def set_link(db: Session, conv: Conversation, owner: User, permission: str, regenerate: bool = False) -> ConversationShare:
    if permission not in PERMISSIONS:
        raise ShareError("INVALID_PERMISSION")
    share = link_share(db, conv.id)
    if share is None:
        share = ConversationShare(
            conversation_id=conv.id, kind="link", token=secrets.token_urlsafe(32), permission=permission, created_by=owner.id
        )
        db.add(share)
    else:
        share.permission = permission
        if regenerate:
            share.token = secrets.token_urlsafe(32)  # liên kết cũ hết hiệu lực
    db.commit()
    db.refresh(share)
    return share


@dataclass
class SharedWithMe:
    conversation_id: uuid.UUID
    title: str
    owner_name: str
    permission: str
    updated_at: object


def shared_with(db: Session, user: User) -> list[SharedWithMe]:
    rows = db.execute(
        select(ConversationShare, Conversation, User)
        .join(Conversation, Conversation.id == ConversationShare.conversation_id)
        .join(User, User.id == Conversation.user_id)
        .where(ConversationShare.kind == "email", ConversationShare.email == user.email.lower())
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [SharedWithMe(c.id, c.title, display_name(owner), s.permission, c.updated_at) for s, c, owner in rows]


def display_name(user: User) -> str:
    """Tên hiển thị công khai: họ tên nếu có, nếu không thì phần trước @ của email (không lộ email đầy đủ)."""
    return user.name.strip() or user.email.split("@")[0]
