import random
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage

from app.services.chat import suggested
from app.services.chat.graph import now_iso
from app.services.chat.text import message_text


CACHED_DELAY_SECONDS = (1.0, 3.0)  # câu trả lời có sẵn cũng "trả lời" mất 1-3 giây để trông như bot đang gõ
_sleep = time.sleep  # test thay bằng hàm không làm gì


def _mentioned_sources(stored: list, text: str) -> list[dict]:
    """Chỉ giữ tham chiếu mà câu trả lời thực sự nhắc tới ("Điều N").

    Tin nhắn lưu từ phiên bản cũ ghi mọi Điều đã tra cứu làm tham chiếu; lọc lại ở đây để mở lại cuộc
    trò chuyện cũ không hiện những chip không liên quan.
    """
    kept = []
    for item in stored:
        if isinstance(item, dict) and isinstance(item.get('url'), str) and item.get('title'):
            kept.append({"title": item["title"], "url": item["url"], "n": item.get("n")})  # nguồn web: đã lọc theo [n] lúc tạo câu trả lời
            continue
        if not isinstance(item, dict) or not isinstance(item.get('article'), int):
            continue
        if re.search(rf'điều\s+{item["article"]}\b', text, flags=re.IGNORECASE):
            kept.append(item)
    return kept


@dataclass
class ChatMessage:
    id: str
    role: str  # 'user' | 'assistant'
    content: str
    created_at: str | None
    duration_seconds: float | None = None  # chỉ có ở tin của bot: thời gian chờ chatbot trả lời
    sources: list[dict] = field(default_factory=list)  # chỉ có ở tin của bot: [{article, title}] hoặc [{title, url}]
    cached: bool = False  # chỉ có ở tin của bot: câu trả lời có sẵn của câu hỏi gợi ý (không gọi LLM)
    author_name: str | None = None  # chỉ có ở tin của người dùng khi người gửi KHÔNG phải chủ cuộc trò chuyện


def to_chat_message(message: BaseMessage) -> ChatMessage | None:
    if isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, AIMessage):
        role = "assistant"
    else:
        return None  # system/tool không hiển thị cho người dùng
    text = message_text(message)
    if role == "assistant" and not text.strip():
        return None
    extra = message.additional_kwargs
    return ChatMessage(
        id=str(message.id),
        role=role,
        content=text,
        created_at=extra.get("created_at"),
        duration_seconds=extra.get("duration_seconds"),
        sources=_mentioned_sources(list(extra.get("sources") or []), text) if role == "assistant" else [],
        cached=bool(extra.get("cached")) if role == "assistant" else False,
        author_name=extra.get("author_name") if role == "user" else None,
    )


def _config(conversation_id: uuid.UUID) -> dict:
    return {"configurable": {"thread_id": str(conversation_id)}}


def _new_human_message(text: str, author_name: str | None = None) -> HumanMessage:
    extra: dict = {"created_at": now_iso()}
    if author_name:
        extra["author_name"] = author_name  # chỉ ghi khi người gửi không phải chủ cuộc trò chuyện
    return HumanMessage(content=text, id=str(uuid.uuid4()), additional_kwargs=extra)


def get_history(graph, conversation_id: uuid.UUID) -> list[ChatMessage]:
    state = graph.get_state(_config(conversation_id))
    messages = (state.values or {}).get("messages", [])
    return [m for m in (to_chat_message(msg) for msg in messages) if m is not None]


def find_exchange(graph, conversation_id: str | None, message_id: str | None) -> tuple[str | None, str | None]:
    """(câu hỏi, câu trả lời) của tin bot `message_id`; (None, None) nếu không tìm thấy (đã xoá, id sai...)."""
    if not conversation_id or not message_id:
        return None, None
    try:
        history = get_history(graph, uuid.UUID(conversation_id))
    except Exception:  # id không hợp lệ / checkpoint lỗi: phản hồi vẫn phải lưu được
        return None, None
    for i, msg in enumerate(history):
        if msg.id == message_id and msg.role == "assistant":
            question = next((m.content for m in reversed(history[:i]) if m.role == "user"), None)
            return question, msg.content
    return None, None


def run_turn(graph, conversation_id: uuid.UUID, text: str, author_name: str | None = None) -> tuple[ChatMessage, ChatMessage]:
    """Thêm tin của người dùng, chạy đồ thị, trả về (tin người dùng, câu trả lời của bot).

    Lịch sử lấy từ checkpoint của `thread_id`, nên bot nhớ các lượt trước kể cả sau khi khởi động lại server.
    Nếu LLM lỗi, tin của người dùng bị gỡ khỏi lịch sử để gửi lại không bị trùng.
    """
    config = _config(conversation_id)
    human = _new_human_message(text, author_name)
    try:
        result = graph.invoke({"messages": [human]}, config)
    except Exception:
        _remove_message(graph, config, human.id)
        raise

    reply = result["messages"][-1]
    user_msg, bot_msg = to_chat_message(human), to_chat_message(reply)
    if bot_msg is None:
        _remove_message(graph, config, human.id)
        raise RuntimeError("LLM returned an empty reply")
    return user_msg, bot_msg  # type: ignore[return-value]


def cached_turn(
    graph,
    conversation_id: uuid.UUID,
    text: str,
    hit: suggested.SuggestedAnswer,
    duration: float | None = None,
    author_name: str | None = None,
) -> tuple[ChatMessage, ChatMessage]:
    """Trả lời câu hỏi gợi ý bằng câu trả lời có sẵn: KHÔNG gọi LLM, embedding hay công cụ.

    Hai tin nhắn vẫn được ghi vào checkpoint của cuộc trò chuyện như một lượt chat bình thường, nên mở lại
    cuộc trò chuyện vẫn thấy đủ, và các câu hỏi sau đó (gọi LLM) vẫn nhớ ngữ cảnh.
    """
    human = _new_human_message(text, author_name)
    reply = AIMessage(
        content=hit.answer,
        id=str(uuid.uuid4()),
        additional_kwargs={
            "created_at": now_iso(),
            "duration_seconds": round(duration, 1) if duration is not None else None,
            "retrieved": [],
            "sources": list(hit.sources),
            "tools": [],
            "cached": True,
        },
    )
    graph.update_state(_config(conversation_id), {"messages": [human, reply]}, as_node="generate")
    return to_chat_message(human), to_chat_message(reply)  # type: ignore[return-value]


def stream_cached_turn(
    graph, conversation_id: uuid.UUID, text: str, hit: suggested.SuggestedAnswer, author_name: str | None = None
) -> Iterator[dict]:
    """Như cached_turn nhưng trả các sự kiện giống stream_turn (user_message, nhiều token, done) để FE không phải khác đi."""
    duration = random.uniform(*CACHED_DELAY_SECONDS)
    user_msg, bot_msg = cached_turn(graph, conversation_id, text, hit, duration, author_name)
    yield {"type": "user_message", "message": user_msg}
    pieces = suggested.chunks(hit.answer)
    for piece in pieces:
        _sleep(duration / len(pieces))  # rải đều trong 1-3 giây, giống đang stream thật
        yield {"type": "token", "text": piece}
    yield {"type": "done", "message": bot_msg}


def stream_turn(graph, conversation_id: uuid.UUID, text: str, author_name: str | None = None) -> Iterator[dict]:
    """Như run_turn nhưng trả từng sự kiện: user_message, rồi nhiều token, cuối cùng done.

    Nếu LLM lỗi hoặc client ngắt kết nối giữa chừng, tin của người dùng bị gỡ khỏi lịch sử
    (không để lại tin "mồ côi" không có câu trả lời).
    """
    config = _config(conversation_id)
    human = _new_human_message(text, author_name)
    yield {"type": "user_message", "message": to_chat_message(human)}

    completed = False
    stream = graph.stream({"messages": [human]}, config, stream_mode="custom")
    try:
        for chunk in stream:
            token = chunk.get("token") if isinstance(chunk, dict) else None
            if token:
                yield {"type": "token", "text": token}

        messages = (graph.get_state(config).values or {}).get("messages", [])
        bot_msg = to_chat_message(messages[-1]) if messages else None
        if bot_msg is None or bot_msg.role != "assistant":
            raise RuntimeError("LLM returned an empty reply")
        completed = True
        yield {"type": "done", "message": bot_msg}
    finally:
        if not completed:
            stream.close()
            _remove_message(graph, config, human.id)


def _remove_message(graph, config: dict, message_id: str) -> None:
    state = graph.get_state(config)
    present = {m.id for m in (state.values or {}).get("messages", [])}
    if message_id in present:
        graph.update_state(config, {"messages": [RemoveMessage(id=message_id)]})


def delete_thread(graph, conversation_id: uuid.UUID) -> None:
    graph.checkpointer.delete_thread(str(conversation_id))
