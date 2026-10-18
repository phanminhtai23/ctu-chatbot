import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import settings


_UNITS = {"s": 1, "m": 60, "h": 3600}
_SPEC = re.compile(r"^\s*(\d+)\s*/\s*(\d+)?\s*([smh])\s*$", re.IGNORECASE)
_OFF = {"off", "none", "unlimited", "0", ""}


@dataclass(frozen=True)
class RateLimit:
    max_events: int
    window_seconds: int


def parse_rate_limit(text: str) -> RateLimit | None:
    """"10/5m" -> 10 tin mỗi 300 giây; "30/1h"; "5/30s"; "off" -> None (không giới hạn). Sai định dạng thì ném ValueError
    (để app báo lỗi rõ ngay khi khởi động thay vì chạy với giới hạn không như ý)."""
    value = (text or "").strip().lower()
    if value in _OFF:
        return None
    match = _SPEC.match(value)
    if not match:
        raise ValueError(f'CHAT_RATE_LIMIT không hợp lệ: {text!r}. Dạng đúng: "10/5m", "30/1h", "5/30s" hoặc "off".')
    count, amount, unit = int(match.group(1)), int(match.group(2) or 1), match.group(3)
    if count < 1 or amount < 1:
        raise ValueError(f"CHAT_RATE_LIMIT phải lớn hơn 0: {text!r}")
    return RateLimit(count, amount * _UNITS[unit])


def describe_window(seconds: int) -> dict:
    """Khoảng thời gian dạng dễ đọc cho giao diện: {"amount": 5, "unit": "m"}."""
    for unit, size in (("h", 3600), ("m", 60)):
        if seconds % size == 0:
            return {"amount": seconds // size, "unit": unit}
    return {"amount": seconds, "unit": "s"}


class SlidingWindowLimiter:
    """Mỗi khoá (user) tối đa `max_events` lần trong `window_seconds` giây gần nhất.

    Lưu trong bộ nhớ của process, đủ cho một worker. Chạy nhiều worker thì mỗi worker đếm riêng,
    khi đó cần chuyển sang kho dùng chung (Redis/DB). Thread-safe vì FastAPI chạy endpoint đồng bộ trong thread pool.
    """

    def __init__(self, max_events: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._max = max_events
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = defaultdict(deque)

    @property
    def max_events(self) -> int:
        return self._max

    @property
    def window_seconds(self) -> float:
        return self._window

    def hit(self, key: str) -> tuple[bool, int]:
        """Ghi nhận một lần dùng. Trả về (được phép, số giây phải chờ nếu bị từ chối)."""
        now = self._clock()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - self._window:
                events.popleft()
            if len(events) >= self._max:
                retry_after = int(events[0] + self._window - now) + 1
                return False, max(1, retry_after)
            events.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_limit = parse_rate_limit(settings.chat_rate_limit)
# Không giới hạn thì không có bộ đếm: `chat_limiter is None`.
chat_limiter: SlidingWindowLimiter | None = SlidingWindowLimiter(_limit.max_events, _limit.window_seconds) if _limit else None
