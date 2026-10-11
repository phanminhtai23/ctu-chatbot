import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from app.core.config import settings


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


chat_limiter = SlidingWindowLimiter(settings.chat_rate_limit_max, settings.chat_rate_limit_window_seconds)
