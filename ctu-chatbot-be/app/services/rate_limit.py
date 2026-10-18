import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import settings


_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_SPEC = re.compile(r"^\s*(\d+)\s*/\s*(\d+)?\s*([smhd])\s*$", re.IGNORECASE)
_OFF = {"off", "none", "unlimited", "0", ""}


@dataclass(frozen=True)
class RateLimit:
    max_events: int
    window_seconds: int


def parse_rate_limit(text: str) -> RateLimit | None:
    """"10/5m" -> 10 tin mỗi 300 giây; "30/1h"; "40/1d"; "5/30s"; "off" -> None (không giới hạn). Sai định dạng thì ném ValueError
    (để app báo lỗi rõ ngay khi khởi động thay vì chạy với giới hạn không như ý)."""
    value = (text or "").strip().lower()
    if value in _OFF:
        return None
    match = _SPEC.match(value)
    if not match:
        raise ValueError(f'CHAT_RATE_LIMIT không hợp lệ: {text!r}. Dạng đúng: "10/5m", "30/1h", "40/1d", "5/30s", nhiều cửa sổ cách nhau bằng dấu phẩy ("10/5m,40/1d") hoặc "off".')
    count, amount, unit = int(match.group(1)), int(match.group(2) or 1), match.group(3)
    if count < 1 or amount < 1:
        raise ValueError(f"CHAT_RATE_LIMIT phải lớn hơn 0: {text!r}")
    return RateLimit(count, amount * _UNITS[unit])


def describe_window(seconds: int) -> dict:
    """Khoảng thời gian dạng dễ đọc cho giao diện: {"amount": 5, "unit": "m"}."""
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
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

    def peek(self, key: str) -> tuple[bool, int]:
        """Như hit nhưng KHÔNG ghi nhận (để kiểm nhiều cửa sổ rồi mới ghi một lượt)."""
        now = self._clock()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - self._window:
                events.popleft()
            if len(events) >= self._max:
                return False, max(1, int(events[0] + self._window - now) + 1)
            return True, 0

    def record(self, key: str) -> None:
        with self._lock:
            self._events[key].append(self._clock())

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


def parse_rate_limits(text: str) -> list[RateLimit]:
    """"10/5m,40/1d" -> [10 tin / 5 phút, 40 tin / 1 ngày]; "off" -> []. Mọi cửa sổ phải cùng thoả thì tin mới được nhận."""
    parts = [p for p in (text or "").split(",") if p.strip()]
    limits = [parse_rate_limit(p) for p in parts] if parts else []
    if any(limit is None for limit in limits):
        if len(limits) > 1:
            raise ValueError(f'CHAT_RATE_LIMIT không hợp lệ: {text!r}. "off" không dùng chung với cửa sổ khác.')
        return []
    return [limit for limit in limits if limit is not None]


class MultiWindowLimiter:
    """Nhiều cửa sổ cùng lúc (ví dụ 10 tin / 5 phút VÀ 40 tin / ngày). Tin chỉ được nhận khi mọi cửa sổ còn chỗ;
    bị từ chối thì không cửa sổ nào bị tính thêm. Cửa sổ ngày là cửa sổ trượt 24 giờ và nằm trong bộ nhớ process
    (khởi động lại thì đếm lại từ đầu)."""

    def __init__(self, limits: list[RateLimit], clock: Callable[[], float] = time.monotonic):
        self.limits = limits
        self._windows = [SlidingWindowLimiter(lim.max_events, lim.window_seconds, clock) for lim in limits]
        self._lock = threading.Lock()

    def hit_detail(self, key: str) -> tuple[bool, int, RateLimit | None]:
        """(được phép, số giây phải chờ, cửa sổ làm bị từ chối). Bị từ chối bởi nhiều cửa sổ thì báo cửa sổ phải chờ lâu nhất."""
        with self._lock:
            blocked: tuple[int, RateLimit] | None = None
            for limit, window in zip(self.limits, self._windows):
                allowed, retry_after = window.peek(key)
                if not allowed and (blocked is None or retry_after > blocked[0]):
                    blocked = (retry_after, limit)
            if blocked is not None:
                return False, blocked[0], blocked[1]
            for window in self._windows:
                window.record(key)
            return True, 0, None

    def hit(self, key: str) -> tuple[bool, int]:
        allowed, retry_after, _ = self.hit_detail(key)
        return allowed, retry_after

    def reset(self) -> None:
        with self._lock:
            for window in self._windows:
                window.reset()


_limits = parse_rate_limits(settings.chat_rate_limit)
# Không giới hạn thì không có bộ đếm: `chat_limiter is None`.
chat_limiter: MultiWindowLimiter | None = MultiWindowLimiter(_limits) if _limits else None
