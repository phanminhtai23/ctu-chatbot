"""Đưa tệp đính kèm (PDF / ảnh) cho Gemini đọc cùng câu hỏi.

Checkpoint của cuộc trò chuyện chỉ giữ THAM CHIẾU tới tệp (id, tên, URL) trong `additional_kwargs["attachments"]`; nội dung tệp được
tải từ Cloudinary ngay lúc gọi LLM và gửi dạng base64 trong khối nội dung của tin nhắn (không lưu vào checkpoint, nếu không
Postgres phình to và mỗi lượt lại ghi lại cả tệp).
"""

import base64
import logging
from collections import OrderedDict

import requests
from langchain_core.messages import BaseMessage, HumanMessage

from app.services.chat.text import message_text

logger = logging.getLogger("app.chat")

RECENT_WITH_FILES = 3  # chỉ các tin gần nhất có tệp mới gửi lại nội dung tệp cho LLM (mỗi lượt gửi lại đều tốn token)
FETCH_TIMEOUT_SECONDS = 30
MAX_FILE_BYTES = 8 * 1024 * 1024  # trần an toàn (giới hạn tải lên là 5 MB)
CACHE_BYTES = 32 * 1024 * 1024  # bộ nhớ đệm nội dung tệp để các lượt hỏi tiếp không tải lại từ Cloudinary

ATTACHMENT_INTRO = (
    "NGƯỜI DÙNG ĐÍNH KÈM TỆP (PDF / ảnh) trong tin nhắn của họ; nội dung tệp nằm ngay trong tin nhắn đó. Hãy đọc kỹ tệp để làm "
    "đúng yêu cầu (tóm tắt, giải thích, trích thông tin, so sánh...). Nếu nội dung tệp liên quan tới quy chế học vụ thì đối chiếu "
    "với NGỮ CẢNH ở trên và nêu Điều tương ứng; nếu không liên quan học vụ vẫn hỗ trợ theo yêu cầu về tệp. Chỉ nêu những gì có "
    "trong tệp, không bịa; nếu tệp mờ / không đọc được thì nói rõ."
)


class _Cache:
    def __init__(self, limit: int):
        self._limit, self._size, self._data = limit, 0, OrderedDict()

    def get(self, key: str) -> bytes | None:
        data = self._data.get(key)
        if data is not None:
            self._data.move_to_end(key)
        return data

    def put(self, key: str, data: bytes) -> None:
        if len(data) > self._limit:
            return
        self._data[key] = data
        self._size += len(data)
        while self._size > self._limit:
            _, old = self._data.popitem(last=False)
            self._size -= len(old)


_cache = _Cache(CACHE_BYTES)


def fetch_bytes(url: str) -> bytes | None:
    """Nội dung tệp từ URL Cloudinary; None nếu không tải được (đã bị xoá, lỗi mạng, quá lớn)."""
    cached = _cache.get(url)
    if cached is not None:
        return cached
    try:
        res = requests.get(url, timeout=FETCH_TIMEOUT_SECONDS)
    except requests.RequestException:
        logger.warning("Không tải được tệp đính kèm (mạng)")
        return None
    if res.status_code != 200 or len(res.content) > MAX_FILE_BYTES:
        logger.warning("Không tải được tệp đính kèm: HTTP %s, %d byte", res.status_code, len(res.content))
        return None
    _cache.put(url, res.content)
    return res.content


def attachments_of(message: BaseMessage) -> list[dict]:
    return list(message.additional_kwargs.get("attachments") or []) if isinstance(message, HumanMessage) else []


def has_attachments(history: list[BaseMessage]) -> bool:
    """Tin nhắn mới nhất của người dùng có đính kèm tệp không."""
    humans = [m for m in history if isinstance(m, HumanMessage)]
    return bool(humans and attachments_of(humans[-1]))


def _block(item: dict, data: bytes) -> dict:
    kind = "file" if item.get("content_type") == "application/pdf" else "image"
    return {"type": kind, "base64": base64.b64encode(data).decode("ascii"), "mime_type": item["content_type"]}


def build_llm_history(history: list[BaseMessage], fetch=None) -> list[BaseMessage]:
    """Bản lịch sử để gửi cho LLM: tin có tệp được thay bằng [chữ + khối PDF/ảnh]. Chỉ `RECENT_WITH_FILES` tin gần nhất có tệp
    được gửi nội dung tệp; các tin cũ hơn chỉ còn ghi chú tên tệp. Tệp không tải được thì ghi chú để LLM nói rõ với người dùng."""
    fetch = fetch or fetch_bytes
    with_files = [i for i, m in enumerate(history) if attachments_of(m)]
    keep = set(with_files[-RECENT_WITH_FILES:])
    result: list[BaseMessage] = []
    for i, message in enumerate(history):
        files = attachments_of(message)
        if not files:
            result.append(message)
            continue
        blocks: list[dict] = []
        notes: list[str] = []
        for item in files:
            data = fetch(item["url"]) if i in keep else None
            if data is None:
                reason = "không đọc được tệp" if i in keep else "không còn trong ngữ cảnh"
                notes.append(f"[Tệp đính kèm \"{item['filename']}\": {reason}]")
            else:
                blocks.append(_block(item, data))
                notes.append(f"[Tệp đính kèm: {item['filename']}]")
        text = "\n".join([message_text(message), *notes])
        result.append(
            HumanMessage(
                content=[{"type": "text", "text": text}, *blocks],
                id=message.id,
                additional_kwargs=message.additional_kwargs,
            )
        )
    return result
