import logging
import math
import re
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings
from app.services.llm.key_pool import KeyPool

logger = logging.getLogger("app.llm")

INVALID_KEY_COOLDOWN = 3600  # key sai/bị thu hồi: bỏ qua 1 giờ rồi thử lại (phòng khi bạn vừa sửa key)
DAILY_QUOTA_MAX_COOLDOWN = 24 * 60 * 60


class LLMNotConfigured(Exception):
    """Chưa điền key Gemini nào trong .env."""


class LLMUnavailable(Exception):
    """Mọi key đều đang hết hạn mức / không dùng được."""

    def __init__(self, retry_after: int):
        super().__init__("All LLM API keys are rate limited")
        self.retry_after = retry_after


class LLMError(Exception):
    """Lỗi từ Gemini không phải do key (yêu cầu không hợp lệ, model không tồn tại, bị chặn nội dung...)."""


def _error_text(exc: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        parts.append(f"{type(exc).__name__}: {exc}")
        exc = exc.__cause__ or exc.__context__  # type: ignore[assignment]
    return " | ".join(parts)


def _status_code(exc: BaseException) -> int | None:
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        for attr in ("code", "status_code"):
            value = getattr(exc, attr, None)
            if isinstance(value, int):
                return value
        exc = exc.__cause__ or exc.__context__  # type: ignore[assignment]
    return None


def classify_error(exc: BaseException) -> str:
    """Phân loại lỗi để biết có nên đổi key không: 'rate_limited' | 'invalid_key' | 'other'."""
    text = _error_text(exc).lower()
    code = _status_code(exc)
    if code == 429 or "resource_exhausted" in text or "quota" in text or "rate limit" in text:
        return "rate_limited"
    if (
        "api_key_invalid" in text
        or "api key not valid" in text
        or "api key expired" in text
        or code in (401, 403)
        or "permission_denied" in text
    ):
        return "invalid_key"
    return "other"


def _daily_quota_cooldown(now: datetime | None = None) -> int:
    """Chờ tới lần reset quota ngày tiếp theo (00:00 giờ Pacific)."""
    pacific = ZoneInfo("America/Los_Angeles")
    current = (now or datetime.now(pacific)).astimezone(pacific)
    next_reset = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, math.ceil(next_reset.timestamp() - current.timestamp()))


def retry_delay_seconds(exc: BaseException, default: int) -> int:
    """Ưu tiên retryDelay của Gemini, nếu thiếu thì ước lượng theo cửa sổ quota."""
    text = _error_text(exc)
    match = re.search(r"retry(?:delay)?\W{1,6}(?:in\s+)?(\d+(?:\.\d+)?)\s*s", text, flags=re.IGNORECASE)
    if match:
        return max(1, min(DAILY_QUOTA_MAX_COOLDOWN, int(float(match.group(1))) + 1))
    metric = re.sub(r"[^a-z0-9]", "", text.lower())
    if "perday" in metric:
        return _daily_quota_cooldown()
    if "perhour" in metric:
        return 60 * 60
    if "perminute" in metric:
        return 60
    if "persecond" in metric:
        return 1
    return default


class GeminiClient:
    """Gọi Gemini bằng nhiều API key: hết hạn mức (429) thì xoay sang key kế tiếp rồi gọi lại."""

    def __init__(self, keys: list[str], model: str, timeout: float, cooldown: int):
        self._pool = KeyPool(keys)
        self._model = model
        self._timeout = timeout
        self._cooldown = cooldown
        self._clients: dict[int, ChatGoogleGenerativeAI] = {}

    @classmethod
    def from_settings(cls) -> "GeminiClient":
        return cls(
            keys=settings.gemini_api_keys,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            cooldown=settings.llm_key_cooldown_seconds,
        )

    def _client(self, idx: int, key: str) -> ChatGoogleGenerativeAI:
        if idx not in self._clients:
            # max_retries=0: tự xử lý 429 bằng cách đổi key, không để langchain ngủ rồi thử lại cùng key.
            self._clients[idx] = ChatGoogleGenerativeAI(
                model=self._model,
                google_api_key=key,
                max_retries=0,
                timeout=self._timeout,
                temperature=0.2,
            )
        return self._clients[idx]

    # Báo cho đồ thị chat biết client này gọi được công cụ (xem app.services.chat.tooling).
    supports_tools = True

    def stream(self, messages: Sequence[BaseMessage], tools: Sequence | None = None) -> Iterator[AIMessageChunk]:
        """Trả lời từng đoạn. Xoay key được khi lỗi xảy ra trước đoạn đầu tiên (lúc đó chưa gửi gì cho
        người dùng); lỗi giữa chừng thì không đổi key được nên báo LLMError."""
        if len(self._pool) == 0:
            raise LLMNotConfigured("No GEMINI_API_KEY_* is set")

        for idx, key in self._pool.candidates():
            model = self._client(idx, key)
            if tools:
                model = model.bind_tools(list(tools))
            chunks = model.stream(list(messages))
            try:
                first = next(chunks)
            except StopIteration:
                self._pool.mark_ok(idx)
                return
            except Exception as exc:  # noqa: BLE001
                if self._handle_key_error(idx, exc):
                    continue
                raise LLMError(_error_text(exc)) from exc

            self._pool.mark_ok(idx)
            yield first
            try:
                yield from chunks
            except Exception as exc:  # noqa: BLE001
                self._handle_key_error(idx, exc)  # nếu do hết hạn mức thì cho key nghỉ cho lần sau
                raise LLMError(_error_text(exc)) from exc
            return

        raise LLMUnavailable(retry_after=max(1, int(self._pool.seconds_until_available()) + 1))

    def _handle_key_error(self, idx: int, exc: Exception) -> bool:
        """Cho key nghỉ nếu lỗi do key. Trả True nếu nên thử key kế tiếp."""
        kind = classify_error(exc)
        if kind == "rate_limited":
            wait = retry_delay_seconds(exc, self._cooldown)
            logger.warning("Gemini key #%d hết hạn mức, nghỉ %ds và chuyển key khác", idx + 1, wait)
            self._pool.block(idx, wait)
            return True
        if kind == "invalid_key":
            logger.error("Gemini key #%d bị từ chối (sai/hết hạn/không đủ quyền), bỏ qua %ds", idx + 1, INVALID_KEY_COOLDOWN)
            self._pool.block(idx, INVALID_KEY_COOLDOWN)
            return True
        logger.exception("Gemini lỗi không liên quan tới key")
        return False

    def invoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        if len(self._pool) == 0:
            raise LLMNotConfigured("No GEMINI_API_KEY_* is set")

        for idx, key in self._pool.candidates():
            try:
                reply = self._client(idx, key).invoke(list(messages))
            except Exception as exc:  # noqa: BLE001 - phân loại rồi quyết định đổi key hay báo lỗi
                kind = classify_error(exc)
                if kind == "rate_limited":
                    wait = retry_delay_seconds(exc, self._cooldown)
                    logger.warning("Gemini key #%d hết hạn mức, nghỉ %ds và chuyển key khác", idx + 1, wait)
                    self._pool.block(idx, wait)
                    continue
                if kind == "invalid_key":
                    logger.error("Gemini key #%d bị từ chối (sai/hết hạn/không đủ quyền), bỏ qua %ds", idx + 1, INVALID_KEY_COOLDOWN)
                    self._pool.block(idx, INVALID_KEY_COOLDOWN)
                    continue
                logger.exception("Gemini lỗi không liên quan tới key")
                raise LLMError(_error_text(exc)) from exc
            self._pool.mark_ok(idx)
            if not isinstance(reply, AIMessage):
                raise LLMError(f"Unexpected reply type {type(reply).__name__}")
            return reply

        raise LLMUnavailable(retry_after=max(1, int(self._pool.seconds_until_available()) + 1))
