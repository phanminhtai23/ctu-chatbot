import json
import logging
import re
import uuid
from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_chat_graph, get_current_user
from app.db.session import get_db, get_sessionmaker
from app.models import Conversation, ConversationShare, User, UserFile
from app.schemas.conversation import (
    ChatMessageOut,
    ConversationDetail,
    ConversationOut,
    RenameConversationIn,
    SendMessageIn,
    SendMessageOut,
)
from app.services import sharing
from app.services.chat import smalltalk, suggested
from app.services.chat.moderation import is_profane
from app.services.chat.queue import QueueFull, QueueTimeout, Ticket, UserBusy, conversation_guard, get_turn_queue
from app.services.chat.service import cached_turn, delete_thread, get_history, run_turn, stream_cached_turn, stream_turn
from app.core.config import settings
from app.services.llm.gemini import LLMError, LLMNotConfigured, LLMUnavailable
from app.services.rate_limit import chat_limiter, describe_window
from app.services.usage import record_usage

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


def _accessible(db: Session, user: User, conversation_id: uuid.UUID, need: str = "view") -> tuple[Conversation, str]:
    """Cuộc trò chuyện của mình hoặc được chia sẻ cho mình. need='chat' đòi quyền chat tiếp; không đủ quyền thì 404/403."""
    conv = db.get(Conversation, conversation_id)
    level = sharing.access_level(db, user, conv) if conv is not None else None
    if level is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if need == "chat" and level == sharing.VIEW:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="READ_ONLY")
    return conv, level


def _author(user: User, level: str) -> str | None:
    """Tên người gửi để gắn vào tin nhắn khi KHÔNG phải chủ cuộc trò chuyện."""
    return None if level == sharing.OWNER else sharing.display_name(user)


def _record_abuse(db: Session, user: User, column) -> None:
    """Cộng 1 vào bộ đếm vi phạm của user (spam / chửi thề) để admin thống kê. Lỗi ghi thống kê không được chặn luồng chat."""
    try:
        db.execute(update(User).where(User.id == user.id).values({column: column + 1}))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("could not record abuse counter", exc_info=True)


def _enforce_rate_limit(db: Session, user: User) -> None:
    """Mỗi user tối đa N tin trong M giây (mặc định 10 tin / 5 phút). Quá thì 429 kèm Retry-After."""
    if chat_limiter is None:  # CHAT_RATE_LIMIT=off
        return
    allowed, retry_after, blocked = chat_limiter.hit_detail(str(user.id))
    if not allowed and blocked is not None:
        logger.warning("429 RATE_LIMITED user=%s limit=%s/%ss retry_after=%ss", user.id, blocked.max_events, blocked.window_seconds, retry_after)
        _record_abuse(db, user, User.spam_count)
        # `limit` và `window` cho giao diện hiện đúng "tối đa N tin trong M phút" theo cấu hình hiện tại.
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "limit": blocked.max_events,
                "window": describe_window(blocked.window_seconds),
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )


def _enter_queue(user: User) -> Ticket:
    """Xin chỗ trong hàng đợi lượt chat. Đầy thì 503, người dùng đang có lượt khác chạy thì 429."""
    try:
        return get_turn_queue().enter(str(user.id), busy_wait=settings.chat_busy_wait_seconds)
    except UserBusy:
        logger.warning("429 TURN_IN_PROGRESS user=%s (lượt trước của người này chưa trả chỗ trong hàng đợi)", user.id)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="TURN_IN_PROGRESS", headers={"Retry-After": "5"}) from None
    except QueueFull as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="SERVER_BUSY", headers={"Retry-After": str(exc.retry_after)}
        ) from None


def _resolve_attachments(db: Session, user: User, ids: list[uuid.UUID]) -> list[dict]:
    """Tệp đính kèm phải là tệp (attachment) của CHÍNH người gửi. Trả về dict thuần (không giữ đối tượng ORM) theo thứ tự đã chọn."""
    if not ids:
        return []
    unique = list(dict.fromkeys(ids))
    rows = {
        f.id: f
        for f in db.scalars(select(UserFile).where(UserFile.id.in_(unique), UserFile.user_id == user.id, UserFile.kind == "attachment"))
    }
    if len(rows) != len(unique):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ATTACHMENT_NOT_FOUND")
    return [
        {"id": str(f.id), "filename": f.filename, "content_type": f.content_type, "size_bytes": f.size_bytes, "url": f.url}
        for f in (rows[i] for i in unique)
    ]


def _pre_screen(db: Session, user: User, text: str, has_attachments: bool = False):
    """Bước lọc trước mọi thứ khác (không hàng đợi, không LLM, không lưu lịch sử):
    - chửi thề -> HTTP 422 PROFANITY (CÓ tính vào giới hạn tốc độ, để không ai spam được);
    - chào hỏi xã giao -> trả lời có sẵn, không gọi LLM (cũng tính vào giới hạn tốc độ);
    - câu hỏi gợi ý -> trả lời có sẵn, không tính giới hạn; còn lại -> None (đi đường bình thường)."""
    if is_profane(text):
        # Vẫn tính vào giới hạn, nhưng KHÔNG đổi thành 429: người dùng luôn thấy đúng lời cảnh báo chửi thề
        # (nếu đang bị giới hạn thì tin chửi không được ghi thêm, tin bình thường kế tiếp mới nhận 429).
        if chat_limiter is not None:
            chat_limiter.hit(str(user.id))
        _record_abuse(db, user, User.profanity_count)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PROFANITY")
    if has_attachments:
        return None  # có tệp đính kèm thì luôn do LLM đọc tệp trả lời (không dùng câu trả lời có sẵn)
    hit = suggested.lookup(text)
    if hit is None:
        hit = smalltalk.lookup(text)
        if hit is not None:
            _enforce_rate_limit(db, user)
    return hit


def _admit(db: Session, user: User, hit) -> Ticket | None:
    """Vào hàng đợi rồi kiểm tra giới hạn tốc độ (theo thứ tự này để lượt bị từ chối vì hàng đầy không mất lượt hỏi).
    Câu hỏi gợi ý có sẵn đáp án nên không cần hàng đợi và không tính giới hạn."""
    if hit is not None:
        return None
    ticket = _enter_queue(user)
    try:
        _enforce_rate_limit(db, user)
    except HTTPException:
        get_turn_queue().release(ticket)
        raise
    return ticket


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
    conv, level = _accessible(db, user, conversation_id)
    messages = get_history(graph, conv.id)
    owner = db.get(User, conv.user_id)
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[ChatMessageOut(**asdict(m)) for m in messages],
        access=level,
        owner_name=sharing.display_name(owner) if owner else "",
        shared=db.scalar(select(func.count()).select_from(ConversationShare).where(ConversationShare.conversation_id == conv.id)) > 0,
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
    conv, level = _accessible(db, user, conversation_id, need="chat")
    conv_id, user_id, author = conv.id, user.id, _author(user, level)
    text = body.text
    attachments = _resolve_attachments(db, user, body.attachment_ids)
    db.rollback()  # trả kết nối DB về pool trong lúc chờ LLM (có thể mất vài chục giây)
    # Câu hỏi gợi ý / chào hỏi: trả lời có sẵn, không gọi LLM và không tính vào giới hạn chat. Chửi thề: từ chối.
    hit = _pre_screen(db, user, text, bool(attachments))
    ticket = _admit(db, user, hit)

    holding = False
    try:
        if hit is not None:
            user_msg, bot_msg = cached_turn(graph, conv_id, text, hit, author_name=author)
        else:
            for _ in get_turn_queue().wait(ticket):  # chờ tới lượt (không có sự kiện để báo vì đây là request thường)
                pass
            holding = conversation_guard.acquire(conv_id)
            if not holding:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="CONVERSATION_BUSY")
            user_msg, bot_msg = run_turn(graph, conv_id, text, author, attachments)
    except QueueTimeout as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="SERVER_BUSY", headers={"Retry-After": str(exc.retry_after)}
        ) from None
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
    finally:
        if holding:
            conversation_guard.release(conv_id)
        if ticket is not None:
            get_turn_queue().release(ticket)

    conv = _touch(db, conv_id, text)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    record_usage(db, user_id, conv_id, cached=hit is not None)

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

    Sự kiện: (`queued` {position} nếu phải xếp hàng) → `start` {user_message} → nhiều `token` {text} → `done` {assistant_message, conversation}.
    Lỗi giữa chừng: `error` {code, retry_after?} với code LLM_RATE_LIMITED | SERVER_BUSY | CONVERSATION_BUSY | LLM_NOT_CONFIGURED | LLM_ERROR | INTERNAL_ERROR.
    Kiểm tra quyền truy cập, nội dung và giới hạn tốc độ được làm TRƯỚC khi bắt đầu stream nên các lỗi đó
    vẫn là HTTP 404/403/422/429 bình thường. Người được chia sẻ quyền 'chat' cũng gửi tin vào đây.
    """
    conv, level = _accessible(db, user, conversation_id, need="chat")
    return stream_response(db, user, conv, body, graph, sessionmaker, author=_author(user, level))


def stream_response(
    db: Session, user: User, conv: Conversation, body: SendMessageIn, graph, sessionmaker, author: str | None
) -> StreamingResponse:
    """Phần dùng chung của mọi cách gửi tin có stream (chủ sở hữu, được chia sẻ theo email, liên kết chia sẻ có quyền chat)."""
    conv_id, user_id = conv.id, user.id
    text = body.text
    attachments = _resolve_attachments(db, user, body.attachment_ids)
    db.rollback()
    hit = _pre_screen(db, user, text, bool(attachments))  # chửi: 422; chào hỏi: trả lời có sẵn (cả hai tính giới hạn); câu gợi ý: có sẵn, không tính giới hạn
    ticket = _admit(db, user, hit)

    def events() -> Iterator[str]:
        holding = False
        try:
            if hit is not None:
                turn = stream_cached_turn(graph, conv_id, text, hit, author_name=author)
            else:
                for position in get_turn_queue().wait(ticket):  # đông người thì xếp hàng, báo vị trí cho client
                    yield _sse("queued", {"position": position})
                holding = conversation_guard.acquire(conv_id)  # hai người cùng chat vào một cuộc trò chuyện: lần lượt
                if not holding:
                    yield _sse("error", {"code": "CONVERSATION_BUSY"})
                    return
                turn = stream_turn(graph, conv_id, text, author, attachments)
            for event in turn:
                kind = event["type"]
                if kind == "user_message":
                    yield _sse("start", {"user_message": ChatMessageOut(**asdict(event["message"])).model_dump()})
                elif kind == "token":
                    yield _sse("token", {"text": event["text"]})
                elif kind == "done":
                    with sessionmaker() as session:
                        conv_row = _touch(session, conv_id, text)
                        conv_out = ConversationOut.model_validate(conv_row).model_dump(mode="json") if conv_row else None
                        record_usage(session, user_id, conv_id, cached=hit is not None)
                    yield _sse(
                        "done",
                        {
                            "assistant_message": ChatMessageOut(**asdict(event["message"])).model_dump(),
                            "conversation": conv_out,
                        },
                    )
        except QueueTimeout as exc:
            yield _sse("error", {"code": "SERVER_BUSY", "retry_after": exc.retry_after})
        except LLMNotConfigured:
            yield _sse("error", {"code": "LLM_NOT_CONFIGURED"})
        except LLMUnavailable as exc:
            yield _sse("error", {"code": "LLM_RATE_LIMITED", "retry_after": exc.retry_after})
        except LLMError:
            yield _sse("error", {"code": "LLM_ERROR"})
        except Exception:  # noqa: BLE001 - không để stream đứt không báo gì cho client
            logger.exception("Lỗi không mong đợi khi stream câu trả lời")
            yield _sse("error", {"code": "INTERNAL_ERROR"})
        finally:
            if holding:
                conversation_guard.release(conv_id)
            if ticket is not None:
                get_turn_queue().release(ticket)  # luôn trả chỗ, kể cả khi client ngắt kết nối giữa chừng

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
    for share in db.scalars(select(ConversationShare).where(ConversationShare.conversation_id == conv.id)):
        db.delete(share)  # SQLite (test) không tự xoá dây chuyền như Postgres
    db.delete(conv)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
