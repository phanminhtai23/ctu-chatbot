import json
import logging
import re
import uuid
from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_chat_graph, get_current_user
from app.db.session import get_db, get_sessionmaker
from app.models import Conversation, User
from app.schemas.conversation import (
    ChatMessageOut,
    ConversationDetail,
    ConversationOut,
    RenameConversationIn,
    SendMessageIn,
    SendMessageOut,
)
from app.services.chat import suggested
from app.services.chat.service import cached_turn, delete_thread, get_history, run_turn, stream_cached_turn, stream_turn
from app.services.llm.gemini import LLMError, LLMNotConfigured, LLMUnavailable
from app.services.rate_limit import chat_limiter

logger = logging.getLogger("app.chat")

router = APIRouter(prefix="/conversations", tags=["conversations"])

TITLE_MAX = 60


def _title_from(text: str) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    return one_line if len(one_line) <= TITLE_MAX else one_line[: TITLE_MAX - 1].rstrip() + "…"


def _owned(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    # Không phải của mình thì trả 404 như không tồn tại, để không lộ id của người khác.
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def _enforce_rate_limit(user: User) -> None:
    """Mỗi user tối đa N tin trong M giây (mặc định 10 tin / 5 phút). Quá thì 429 kèm Retry-After."""
    allowed, retry_after = chat_limiter.hit(str(user.id))
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="RATE_LIMITED",
            headers={"Retry-After": str(retry_after)},
        )


def _touch(db: Session, conversation_id: uuid.UUID, first_text: str) -> Conversation | None:
    """Sau mỗi lượt: đặt tiêu đề (nếu chưa có) từ câu hỏi đầu tiên và cập nhật thời gian hoạt động."""
    conv = db.get(Conversation, conversation_id)
    if conv is None:  # bị xoá đúng lúc đang trả lời
        return None
    if not conv.title:
        conv.title = _title_from(first_text)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conv)
    return conv


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = Conversation(user_id=user.id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("", response_model=list[ConversationOut])
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    ).all()


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    graph=Depends(get_chat_graph),
):
    conv = _owned(db, user, conversation_id)
    messages = get_history(graph, conv.id)
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[ChatMessageOut(**asdict(m)) for m in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: uuid.UUID,
    body: RenameConversationIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _owned(db, user, conversation_id)
    conv.title = body.title
    db.commit()
    db.refresh(conv)
    return conv


@router.post("/{conversation_id}/messages", response_model=SendMessageOut)
def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    graph=Depends(get_chat_graph),
):
    conv = _owned(db, user, conversation_id)
    conv_id = conv.id
    db.rollback()  # trả kết nối DB về pool trong lúc chờ LLM (có thể mất vài chục giây)
    # Câu hỏi gợi ý: trả lời có sẵn, không gọi LLM và không tính vào giới hạn chat.
    hit = suggested.lookup(body.content)
    if hit is None:
        _enforce_rate_limit(user)

    try:
        if hit is not None:
            user_msg, bot_msg = cached_turn(graph, conv_id, body.content, hit)
        else:
            user_msg, bot_msg = run_turn(graph, conv_id, body.content)
    except LLMNotConfigured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM_NOT_CONFIGURED") from None
    except LLMUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM_RATE_LIMITED",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    except LLMError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="LLM_ERROR") from None

    conv = _touch(db, conv_id, body.content)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    return SendMessageOut(
        user_message=ChatMessageOut(**asdict(user_msg)),
        assistant_message=ChatMessageOut(**asdict(bot_msg)),
        conversation=ConversationOut.model_validate(conv),
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: uuid.UUID,
    body: SendMessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    graph=Depends(get_chat_graph),
    sessionmaker=Depends(get_sessionmaker),
):
    """Gửi tin và nhận câu trả lời dạng stream (Server-Sent Events).

    Sự kiện: `start` {user_message} → nhiều `token` {text} → `done` {assistant_message, conversation}.
    Lỗi giữa chừng: `error` {code, retry_after?} với code LLM_RATE_LIMITED | LLM_NOT_CONFIGURED | LLM_ERROR | INTERNAL_ERROR.
    Kiểm tra quyền sở hữu, nội dung và giới hạn tốc độ được làm TRƯỚC khi bắt đầu stream nên các lỗi đó
    vẫn là HTTP 404/422/429 bình thường.
    """
    conv = _owned(db, user, conversation_id)
    conv_id = conv.id
    db.rollback()
    hit = suggested.lookup(body.content)  # câu hỏi gợi ý: trả lời có sẵn, không gọi LLM, không tính giới hạn chat
    if hit is None:
        _enforce_rate_limit(user)

    def events() -> Iterator[str]:
        try:
            if hit is not None:
                turn = stream_cached_turn(graph, conv_id, body.content, hit)
            else:
                turn = stream_turn(graph, conv_id, body.content)
            for event in turn:
                kind = event["type"]
                if kind == "user_message":
                    yield _sse("start", {"user_message": ChatMessageOut(**asdict(event["message"])).model_dump()})
                elif kind == "token":
                    yield _sse("token", {"text": event["text"]})
                elif kind == "done":
                    with sessionmaker() as session:
                        conv_row = _touch(session, conv_id, body.content)
                        conv_out = ConversationOut.model_validate(conv_row).model_dump(mode="json") if conv_row else None
                    yield _sse(
                        "done",
                        {
                            "assistant_message": ChatMessageOut(**asdict(event["message"])).model_dump(),
                            "conversation": conv_out,
                        },
                    )
        except LLMNotConfigured:
            yield _sse("error", {"code": "LLM_NOT_CONFIGURED"})
        except LLMUnavailable as exc:
            yield _sse("error", {"code": "LLM_RATE_LIMITED", "retry_after": exc.retry_after})
        except LLMError:
            yield _sse("error", {"code": "LLM_ERROR"})
        except Exception:  # noqa: BLE001 - không để stream đứt không báo gì cho client
            logger.exception("Lỗi không mong đợi khi stream câu trả lời")
            yield _sse("error", {"code": "INTERNAL_ERROR"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    graph=Depends(get_chat_graph),
):
    conv = _owned(db, user, conversation_id)
    delete_thread(graph, conv.id)  # xoá cả lịch sử trong checkpoint
    db.delete(conv)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
