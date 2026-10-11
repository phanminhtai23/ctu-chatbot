import pytest

from app.services import rate_limit
from app.services.rate_limit import SlidingWindowLimiter, chat_limiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# ---- bộ đếm ----


def test_allows_up_to_max_then_blocks():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(10, 300, clock)
    for _ in range(10):
        assert limiter.hit("u") == (True, 0)
    allowed, retry_after = limiter.hit("u")
    assert allowed is False
    assert retry_after == 301  # lượt đầu hết hạn sau đúng 300s (làm tròn lên)


def test_window_slides_instead_of_resetting_all_at_once():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(2, 300, clock)
    assert limiter.hit("u")[0]  # t=0
    clock.now += 100
    assert limiter.hit("u")[0]  # t=100
    assert not limiter.hit("u")[0]  # đã đủ 2 lượt trong 5 phút

    clock.now += 201  # t=301: lượt ở t=0 đã ra khỏi cửa sổ, lượt ở t=100 vẫn còn
    assert limiter.hit("u")[0]
    assert not limiter.hit("u")[0]


def test_each_user_has_own_budget():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, 300, clock)
    assert limiter.hit("a")[0]
    assert not limiter.hit("a")[0]
    assert limiter.hit("b")[0]


def test_blocked_attempts_do_not_extend_the_block():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, 300, clock)
    assert limiter.hit("u")[0]
    for _ in range(20):
        clock.now += 10
        assert not limiter.hit("u")[0]  # spam trong lúc bị chặn không làm cửa sổ dài thêm
    clock.now += 101  # tổng 301s kể từ lượt được chấp nhận duy nhất
    assert limiter.hit("u")[0]


def test_default_limit_is_10_per_5_minutes():
    assert chat_limiter._max == 10
    assert chat_limiter._window == 300


# ---- qua API ----


def _new_conversation(client, headers) -> str:
    return client.post("/api/v1/conversations", headers=headers).json()["id"]


def _send(client, headers, conv_id, text="Điều 14 nói gì?"):
    return client.post(f"/api/v1/conversations/{conv_id}/messages", headers=headers, json={"content": text})


def _other_headers(client):
    res = client.post("/api/v1/auth/dev-login", json={"email": "b2100002@student.ctu.edu.vn"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_11th_message_in_5_minutes_is_rejected(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    for i in range(10):
        assert _send(client, auth_headers, conv_id, f"câu hỏi {i}").status_code == 200

    res = _send(client, auth_headers, conv_id, "câu thứ 11")
    assert res.status_code == 429
    assert res.json()["detail"] == "RATE_LIMITED"
    assert 1 <= int(res.headers["Retry-After"]) <= 300


def test_rejected_message_is_not_saved_and_not_sent_to_llm(client, auth_headers, fake_llm):
    conv_id = _new_conversation(client, auth_headers)
    for i in range(10):
        _send(client, auth_headers, conv_id, f"câu hỏi {i}")
    calls_before = len(fake_llm.calls)

    assert _send(client, auth_headers, conv_id, "câu thứ 11").status_code == 429

    assert len(fake_llm.calls) == calls_before
    history = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()["messages"]
    assert len(history) == 20  # 10 hỏi + 10 đáp, không có tin thứ 11


def test_limit_is_per_user_not_global(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    for i in range(10):
        _send(client, auth_headers, conv_id, f"câu hỏi {i}")
    assert _send(client, auth_headers, conv_id).status_code == 429

    other = _other_headers(client)
    other_conv = _new_conversation(client, other)
    assert _send(client, other, other_conv).status_code == 200


def test_limit_spans_all_conversations_of_a_user(client, auth_headers):
    first = _new_conversation(client, auth_headers)
    second = _new_conversation(client, auth_headers)
    for i in range(5):
        assert _send(client, auth_headers, first, f"a{i}").status_code == 200
        assert _send(client, auth_headers, second, f"b{i}").status_code == 200
    assert _send(client, auth_headers, first).status_code == 429  # mở cuộc trò chuyện mới cũng không lách được


def test_streaming_endpoint_shares_the_same_budget(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    for i in range(10):
        res = client.post(
            f"/api/v1/conversations/{conv_id}/messages/stream", headers=auth_headers, json={"content": f"hỏi {i}"}
        )
        assert res.status_code == 200
    res = client.post(f"/api/v1/conversations/{conv_id}/messages/stream", headers=auth_headers, json={"content": "11"})
    assert res.status_code == 429
    assert res.json()["detail"] == "RATE_LIMITED"


def test_allowed_again_after_5_minutes(client, auth_headers, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(chat_limiter, "_clock", clock)
    conv_id = _new_conversation(client, auth_headers)
    for i in range(10):
        assert _send(client, auth_headers, conv_id, f"câu hỏi {i}").status_code == 200
    assert _send(client, auth_headers, conv_id).status_code == 429

    clock.now += 301
    assert _send(client, auth_headers, conv_id).status_code == 200


def test_not_found_and_invalid_requests_do_not_consume_budget(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    other_conv = _new_conversation(client, _other_headers(client))
    for _ in range(15):
        assert _send(client, auth_headers, other_conv).status_code == 404  # không phải cuộc trò chuyện của mình
        res = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers, json={"content": ""})
        assert res.status_code == 422
    for i in range(10):
        assert _send(client, auth_headers, conv_id, f"câu hỏi {i}").status_code == 200


def test_llm_failure_still_counts_so_errors_cannot_be_used_to_spam(client, auth_headers, fake_llm):
    from app.services.llm.gemini import LLMError

    fake_llm.error = LLMError("boom")
    conv_id = _new_conversation(client, auth_headers)
    statuses = [_send(client, auth_headers, conv_id, f"hỏi {i}").status_code for i in range(11)]
    assert statuses[:10] == [502] * 10
    assert statuses[10] == 429


def test_module_exposes_singleton():
    assert rate_limit.chat_limiter is chat_limiter
