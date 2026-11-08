import threading
import time

import pytest

from app.services.chat import queue as queue_module
from app.services.chat.queue import QueueFull, QueueTimeout, TurnQueue, UserBusy


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _drain(q, ticket):
    return list(q.wait(ticket))


def test_admits_immediately_when_free():
    q = TurnQueue(max_concurrent=2, max_waiting=2)
    t = q.enter("a")
    assert _drain(q, t) == []  # không phải xếp hàng thì không có sự kiện vị trí
    assert q.running == 1 and q.waiting == 0
    q.release(t)
    assert q.running == 0


def test_user_cannot_have_two_turns_at_once():
    q = TurnQueue(max_concurrent=2, max_waiting=2)
    t = q.enter("a")
    with pytest.raises(UserBusy):
        q.enter("a")
    q.release(t)
    q.enter("a")  # trả chỗ rồi thì vào lại được


def test_busy_user_waits_for_orphaned_turn_to_release():
    q = TurnQueue(max_concurrent=2, max_waiting=2, poll_seconds=0.05)
    old = q.enter("a")
    threading.Timer(0.2, q.release, args=(old,)).start()
    started = time.monotonic()
    new = q.enter("a", busy_wait=3)  # lượt cũ nhả chỗ sau 0,2 giây nên không bị UserBusy
    assert 0.1 < time.monotonic() - started < 2
    q.release(new)


def test_busy_user_still_rejected_when_old_turn_outlasts_wait():
    q = TurnQueue(max_concurrent=2, max_waiting=2, poll_seconds=0.05)
    q.enter("a")
    with pytest.raises(UserBusy):
        q.enter("a", busy_wait=0.2)


def test_full_queue_rejects_instead_of_growing():
    q = TurnQueue(max_concurrent=1, max_waiting=1)
    running = q.enter("a")
    _drain(q, running)
    q.enter("b")  # chiếm chỗ chờ duy nhất
    with pytest.raises(QueueFull) as err:
        q.enter("c")
    assert err.value.retry_after >= 5
    assert q.waiting == 1


def test_waiting_turn_gets_position_then_runs_in_fifo_order():
    q = TurnQueue(max_concurrent=1, max_waiting=5, poll_seconds=0.01)
    first = q.enter("a")
    _drain(q, first)
    second, third = q.enter("b"), q.enter("c")

    order: list[str] = []
    positions: dict[str, list[int]] = {}

    def worker(name, ticket):
        positions[name] = []
        for pos in q.wait(ticket):
            positions[name].append(pos)
        order.append(name)
        time.sleep(0.02)
        q.release(ticket)

    threads = [threading.Thread(target=worker, args=("b", second)), threading.Thread(target=worker, args=("c", third))]
    for th in threads:
        th.start()
    time.sleep(0.1)
    assert order == []  # còn bị chặn bởi lượt đang chạy
    q.release(first)
    for th in threads:
        th.join(timeout=5)
    assert order == ["b", "c"]
    assert positions["b"][0] == 1 and positions["c"][0] == 2
    assert q.running == 0 and q.waiting == 0


def test_wait_times_out_and_frees_slot():
    clock = FakeClock()
    q = TurnQueue(max_concurrent=1, max_waiting=3, wait_seconds=30, poll_seconds=0.001, clock=clock)
    _drain(q, q.enter("a"))
    waiter = q.enter("b")
    gen = q.wait(waiter)
    assert next(gen) == 1
    clock.now += 31
    with pytest.raises(QueueTimeout):
        next(gen)
    assert q.waiting == 0
    q.enter("b")  # vé hết hạn đã trả chỗ của người dùng


def test_abandoned_waiting_ticket_is_purged():
    clock = FakeClock()
    q = TurnQueue(max_concurrent=1, max_waiting=1, wait_seconds=30, clock=clock)
    _drain(q, q.enter("a"))
    q.enter("b")  # không bao giờ gọi wait/release (client biến mất)
    with pytest.raises(QueueFull):
        q.enter("c")
    clock.now += 60
    q.enter("c")  # vé của b bị dọn nên có chỗ


def test_hung_running_turn_is_eventually_released():
    clock = FakeClock()
    q = TurnQueue(max_concurrent=1, max_waiting=0, clock=clock)
    _drain(q, q.enter("a"))
    with pytest.raises(QueueFull):
        q.enter("b")
    clock.now += queue_module.STALE_RUNNING_SECONDS + 1
    q.enter("b")


def test_release_is_idempotent_and_works_while_waiting():
    q = TurnQueue(max_concurrent=1, max_waiting=2)
    _drain(q, q.enter("a"))
    waiting = q.enter("b")
    q.release(waiting)
    q.release(waiting)
    assert q.waiting == 0 and q.running == 1


# ---- qua API ----


def _new_conversation(client, headers) -> str:
    return client.post("/api/v1/conversations", headers=headers).json()["id"]


def test_server_busy_returns_503_and_does_not_use_rate_limit_quota(client, auth_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "chat_max_concurrent", 1)
    monkeypatch.setattr(settings, "chat_queue_max_waiting", 0)
    q = queue_module.get_turn_queue()
    _drain(q, q.enter("someone-else"))  # chiếm chỗ duy nhất

    conv_id = _new_conversation(client, auth_headers)
    res = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers, json={"content": "hỏi gì đó"})
    assert res.status_code == 503
    assert res.json()["detail"] == "SERVER_BUSY"
    assert int(res.headers["Retry-After"]) >= 5

    # người dùng bị từ chối vì hàng đầy không bị trừ lượt: còn đủ 10 lượt khi hàng rảnh trở lại
    q.release(next(iter(q._by_user.values())))
    for i in range(10):
        assert client.post(
            f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers, json={"content": f"câu {i}"}
        ).status_code == 200


def test_slot_is_released_after_turn_and_after_llm_error(client, auth_headers, fake_llm):
    conv_id = _new_conversation(client, auth_headers)
    url = f"/api/v1/conversations/{conv_id}/messages"
    assert client.post(url, headers=auth_headers, json={"content": "một"}).status_code == 200
    assert queue_module.get_turn_queue().running == 0

    fake_llm.error = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        client.post(url, headers=auth_headers, json={"content": "hai"})
    assert queue_module.get_turn_queue().running == 0
    assert queue_module.get_turn_queue().waiting == 0


def test_stream_releases_slot_when_done(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    res = client.post(f"/api/v1/conversations/{conv_id}/messages/stream", headers=auth_headers, json={"content": "điểm D có đậu không"})
    assert res.status_code == 200
    assert "event: done" in res.text
    assert queue_module.get_turn_queue().running == 0


def test_stream_emits_queued_event_while_waiting(client, auth_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "chat_max_concurrent", 1)
    monkeypatch.setattr(settings, "chat_queue_max_waiting", 3)
    q = queue_module.get_turn_queue()
    blocker = q.enter("someone-else")
    _drain(q, blocker)
    q._poll = 0.01
    threading.Timer(0.3, q.release, args=(blocker,)).start()

    conv_id = _new_conversation(client, auth_headers)
    res = client.post(f"/api/v1/conversations/{conv_id}/messages/stream", headers=auth_headers, json={"content": "điểm D có đậu không"})
    assert res.text.index("event: queued") < res.text.index("event: start") < res.text.index("event: done")
    assert '"position": 1' in res.text
