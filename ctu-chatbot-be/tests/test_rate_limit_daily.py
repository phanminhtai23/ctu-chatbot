import pytest

from app.services.rate_limit import MultiWindowLimiter, RateLimit, describe_window, parse_rate_limit, parse_rate_limits


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_parse_daily_and_multiple_windows():
    assert parse_rate_limit("40/1d") == RateLimit(40, 86400)
    assert parse_rate_limits("10/5m,40/1d") == [RateLimit(10, 300), RateLimit(40, 86400)]
    assert parse_rate_limits(" 10/5m , 40/1d ") == [RateLimit(10, 300), RateLimit(40, 86400)]
    assert parse_rate_limits("off") == []
    assert describe_window(86400) == {"amount": 1, "unit": "d"}


@pytest.mark.parametrize("bad", ["10/5m,off", "10/5x", "abc", "10/5m;40/1d"])
def test_parse_rejects_bad_specs(bad):
    with pytest.raises(ValueError):
        parse_rate_limits(bad)


def test_both_windows_must_have_room():
    clock = FakeClock()
    limiter = MultiWindowLimiter(parse_rate_limits("2/1m,3/1d"), clock)
    assert limiter.hit("u")[0] and limiter.hit("u")[0]
    allowed, retry, blocked = limiter.hit_detail("u")
    assert not allowed and blocked == RateLimit(2, 60) and 1 <= retry <= 61  # cửa sổ phút chặn trước

    clock.now += 61  # hết cửa sổ phút, còn 1 lượt trong ngày
    assert limiter.hit("u")[0]
    clock.now += 61
    allowed, retry, blocked = limiter.hit_detail("u")
    assert not allowed and blocked == RateLimit(3, 86400) and retry > 3600  # hết lượt trong ngày

    clock.now += 86400  # sang ngày mới (cửa sổ trượt 24 giờ)
    assert limiter.hit("u")[0]


def test_rejected_attempt_does_not_use_the_daily_budget():
    clock = FakeClock()
    limiter = MultiWindowLimiter(parse_rate_limits("1/1m,3/1d"), clock)
    assert limiter.hit("u")[0]
    for _ in range(10):
        assert not limiter.hit("u")[0]  # bị chặn bởi cửa sổ phút, không được trừ vào ngày
    clock.now += 61
    assert limiter.hit("u")[0]
    clock.now += 61
    assert limiter.hit("u")[0]  # lượt thứ 3 trong ngày vẫn còn


def test_each_user_has_own_daily_budget():
    limiter = MultiWindowLimiter(parse_rate_limits("5/1m,1/1d"), FakeClock())
    assert limiter.hit("a")[0] and not limiter.hit("a")[0]
    assert limiter.hit("b")[0]


def test_api_reports_the_daily_window(client, auth_headers, monkeypatch):
    from app.api.v1 import conversations
    from app.services import rate_limit

    monkeypatch.setattr(conversations, "chat_limiter", MultiWindowLimiter(parse_rate_limits("100/5m,2/1d")))
    conv_id = client.post("/api/v1/conversations", headers=auth_headers).json()["id"]
    url = f"/api/v1/conversations/{conv_id}/messages"
    assert client.post(url, headers=auth_headers, json={"content": "hỏi 1"}).status_code == 200
    assert client.post(url, headers=auth_headers, json={"content": "hỏi 2"}).status_code == 200
    res = client.post(url, headers=auth_headers, json={"content": "hỏi 3"})
    assert res.status_code == 429
    detail = res.json()["detail"]
    assert detail["limit"] == 2 and detail["window"] == {"amount": 1, "unit": "d"} and detail["retry_after"] > 3600
    assert rate_limit  # silence unused import
