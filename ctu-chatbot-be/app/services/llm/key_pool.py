import threading
import time
from collections.abc import Callable, Iterator


class KeyPool:
    """Danh sách API key, bỏ qua key đang trong thời gian nghỉ.

    Key bị "nghỉ" (cooldown) sẽ bị bỏ qua cho đến khi hết thời gian nghỉ. Thread-safe vì FastAPI
    chạy các endpoint đồng bộ trong thread pool. Lớp này không giữ/ghi log giá trị key.
    """

    def __init__(self, keys: list[str], clock: Callable[[], float] = time.monotonic):
        self._keys = list(keys)
        self._clock = clock
        self._lock = threading.Lock()
        self._current = 0
        self._blocked_until: dict[int, float] = {}

    def __len__(self) -> int:
        return len(self._keys)

    def candidates(self, *, round_robin: bool = False) -> Iterator[tuple[int, str]]:
        """Lần lượt các key dùng được; round_robin phân phối điểm bắt đầu giữa các lượt."""
        with self._lock:
            start = self._current
            if round_robin and self._keys:
                self._current = (start + 1) % len(self._keys)
        for offset in range(len(self._keys)):
            idx = (start + offset) % len(self._keys)
            with self._lock:
                blocked = self._blocked_until.get(idx, 0) > self._clock()
            if not blocked:
                yield idx, self._keys[idx]

    def mark_ok(self, idx: int) -> None:
        """Không xóa cooldown do một request khác vừa ghi nhận."""

    def block(self, idx: int, seconds: float) -> None:
        """Cho key nghỉ `seconds` giây và chuyển key hiện tại sang key kế tiếp."""
        with self._lock:
            self._blocked_until[idx] = max(self._blocked_until.get(idx, 0), self._clock() + seconds)
            if self._current == idx and self._keys:
                self._current = (idx + 1) % len(self._keys)

    def seconds_until_available(self) -> float:
        """Còn bao lâu nữa thì có ít nhất một key dùng lại được (0 nếu đã có)."""
        with self._lock:
            now = self._clock()
            waits = [max(0.0, self._blocked_until.get(i, 0) - now) for i in range(len(self._keys))]
        return min(waits) if waits else 0.0
