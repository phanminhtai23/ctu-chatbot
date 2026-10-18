"""Hàng đợi lượt chat: giữ server khỏi bị quá tải khi nhiều người hỏi cùng lúc.

Mỗi lượt chat giữ một luồng và gọi LLM (vài giây đến vài chục giây). Không giới hạn thì lúc đông người luồng cạn,
mọi request khác (đăng nhập, xem lịch sử...) cũng đứng theo, và các key Gemini bị đập 429. Hàng đợi này:
- cho tối đa `max_concurrent` lượt chạy cùng lúc, các lượt còn lại xếp hàng FIFO;
- hàng chờ có trần `max_waiting`: đầy thì từ chối ngay (QueueFull -> 503 + Retry-After) thay vì nhận vô hạn;
- mỗi người dùng chỉ có một lượt đang chờ/chạy (UserBusy -> 429) nên một người không chiếm hết chỗ;
- chờ quá `wait_seconds` thì bỏ cuộc (QueueTimeout);
- lượt bị bỏ giữa chừng (client ngắt kết nối) luôn trả chỗ; vé bị bỏ quên được dọn theo thời gian.

Hàng đợi nằm trong bộ nhớ của một process (đủ cho 1 instance uvicorn). Chạy nhiều worker/instance thì mỗi cái có
hàng riêng; muốn dùng chung cần đổi sang Redis.
"""

import threading
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

STALE_WAITING_GRACE = 15  # vé chờ quá hạn bao nhiêu giây thì coi là bị bỏ quên
STALE_RUNNING_SECONDS = 15 * 60  # lượt chạy quá lâu (treo) thì giải phóng chỗ


class QueueFull(Exception):
    def __init__(self, retry_after: int):
        super().__init__("queue full")
        self.retry_after = retry_after


class UserBusy(Exception):
    """Người dùng đã có một lượt đang chờ hoặc đang chạy."""


class QueueTimeout(Exception):
    def __init__(self, retry_after: int = 10):
        super().__init__("queue wait timed out")
        self.retry_after = retry_after


@dataclass
class Ticket:
    user: str
    created: float
    state: str = "waiting"  # waiting | running | done
    started: float = 0.0
    id: int = field(default=0)


class TurnQueue:
    def __init__(
        self,
        max_concurrent: int = 4,
        max_waiting: int = 30,
        wait_seconds: float = 120,
        poll_seconds: float = 1.0,
        clock=time.monotonic,
    ):
        self._max_concurrent = max(1, max_concurrent)
        self._max_waiting = max(0, max_waiting)
        self._wait_seconds = wait_seconds
        self._poll = poll_seconds
        self._clock = clock
        self._cond = threading.Condition()
        self._waiting: deque[Ticket] = deque()
        self._running: set[int] = set()
        self._by_user: dict[str, Ticket] = {}
        self._next_id = 0
        self._avg_seconds = 10.0  # ước lượng thời gian một lượt, dùng cho Retry-After

    # --- trạng thái (cho test và theo dõi) ---
    @property
    def running(self) -> int:
        with self._cond:
            return len(self._running)

    @property
    def waiting(self) -> int:
        with self._cond:
            return len(self._waiting)

    # --- nội bộ (gọi khi đang giữ lock) ---
    def _purge(self) -> None:
        now = self._clock()
        for ticket in list(self._waiting):
            if now - ticket.created > self._wait_seconds + STALE_WAITING_GRACE:
                self._finish(ticket)
        for ticket in list(self._by_user.values()):
            if ticket.state == "running" and now - ticket.started > STALE_RUNNING_SECONDS:
                self._finish(ticket)

    def _finish(self, ticket: Ticket) -> None:
        if ticket.state == "done":
            return
        if ticket.state == "running":
            self._running.discard(ticket.id)
            if ticket.started:
                self._avg_seconds = 0.8 * self._avg_seconds + 0.2 * max(1.0, self._clock() - ticket.started)
        else:
            try:
                self._waiting.remove(ticket)
            except ValueError:
                pass
        ticket.state = "done"
        if self._by_user.get(ticket.user) is ticket:
            del self._by_user[ticket.user]
        self._cond.notify_all()

    def _retry_after(self) -> int:
        ahead = len(self._waiting) + len(self._running)
        return max(5, min(120, int(self._avg_seconds * ahead / self._max_concurrent)))

    # --- API ---
    def enter(self, user: str) -> Ticket:
        """Xin một chỗ trong hàng. Ném UserBusy / QueueFull ngay nếu không nhận được."""
        with self._cond:
            self._purge()
            if user in self._by_user:
                raise UserBusy
            if len(self._running) >= self._max_concurrent and len(self._waiting) >= self._max_waiting:
                raise QueueFull(self._retry_after())
            self._next_id += 1
            ticket = Ticket(user=user, created=self._clock(), id=self._next_id)
            self._waiting.append(ticket)
            self._by_user[user] = ticket
            return ticket

    def wait(self, ticket: Ticket) -> Iterator[int]:
        """Chờ tới lượt. Mỗi lần vị trí trong hàng đổi thì yield vị trí mới (1 = kế tiếp); xong thì kết thúc,
        lúc đó vé đã ở trạng thái running. Quá hạn thì ném QueueTimeout (vé được trả lại)."""
        last = None
        while True:
            with self._cond:
                if ticket.state == "done":
                    raise QueueTimeout()
                if self._waiting and self._waiting[0] is ticket and len(self._running) < self._max_concurrent:
                    self._waiting.popleft()
                    ticket.state, ticket.started = "running", self._clock()
                    self._running.add(ticket.id)
                    return
                if self._clock() - ticket.created > self._wait_seconds:
                    retry = self._retry_after()
                    self._finish(ticket)
                    raise QueueTimeout(retry)
                position = list(self._waiting).index(ticket) + 1
                if position == last:
                    self._cond.wait(self._poll)
                    continue
            last = position
            yield position

    def release(self, ticket: Ticket) -> None:
        """Trả chỗ (an toàn khi gọi nhiều lần, kể cả khi vé còn đang chờ)."""
        with self._cond:
            self._finish(ticket)


turn_queue: TurnQueue | None = None


def get_turn_queue() -> TurnQueue:
    global turn_queue
    if turn_queue is None:
        from app.core.config import settings

        turn_queue = TurnQueue(
            max_concurrent=settings.chat_max_concurrent,
            max_waiting=settings.chat_queue_max_waiting,
            wait_seconds=settings.chat_queue_wait_seconds,
        )
    return turn_queue
