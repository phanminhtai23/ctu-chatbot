import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.services.llm import gemini as gemini_module
from app.services.llm.gemini import (
    GeminiClient,
    LLMError,
    LLMNotConfigured,
    LLMUnavailable,
    classify_error,
    retry_delay_seconds,
)
from app.services.llm.key_pool import KeyPool
from tests.fakes import FakeApiError

RATE_LIMIT = FakeApiError(429, "429 RESOURCE_EXHAUSTED. Quota exceeded for metric")
BAD_KEY = FakeApiError(400, "400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key. API_KEY_INVALID")
SERVER_ERROR = FakeApiError(500, "500 INTERNAL. Something broke")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeModel:
    """Thay ChatGoogleGenerativeAI: mỗi key có một kịch bản (lỗi hoặc trả lời)."""

    def __init__(self, key: str, script: dict[str, Exception | str], log: list[str]):
        self.key, self.script, self.log = key, script, log

    def invoke(self, messages):
        self.log.append(self.key)
        outcome = self.script[self.key]
        if isinstance(outcome, Exception):
            raise outcome
        return AIMessage(content=outcome)

    def stream(self, messages):
        # Hàm sinh: lỗi chỉ nổ ra khi lấy đoạn đầu tiên, giống SDK thật. `outcome` là chuỗi, lỗi,
        # hoặc danh sách đoạn (phần tử là Exception thì nổ giữa chừng).
        self.log.append(self.key)
        outcome = self.script[self.key]
        if isinstance(outcome, Exception):
            raise outcome
        for item in outcome if isinstance(outcome, list) else [outcome]:
            if isinstance(item, Exception):
                raise item
            yield AIMessageChunk(content=item)


def make_client(monkeypatch, keys, script, clock=None, cooldown=60):  # script: key -> chuỗi | lỗi | [đoạn, ...]
    log: list[str] = []
    client = GeminiClient(keys=keys, model="m", timeout=5, cooldown=cooldown)
    if clock is not None:
        client._pool = KeyPool(keys, clock=clock)
    monkeypatch.setattr(client, "_client", lambda idx, key: FakeModel(key, script, log))
    return client, log


MESSAGES = [HumanMessage("xin chào")]


def test_classify_error():
    assert classify_error(RATE_LIMIT) == "rate_limited"
    assert classify_error(FakeApiError(0, "You exceeded your current quota")) == "rate_limited"
    assert classify_error(BAD_KEY) == "invalid_key"
    assert classify_error(FakeApiError(403, "PERMISSION_DENIED")) == "invalid_key"
    assert classify_error(SERVER_ERROR) == "other"
    assert classify_error(ValueError("lỗi lạ")) == "other"


def test_classify_looks_through_wrapped_exceptions():
    try:
        try:
            raise RATE_LIMIT
        except FakeApiError as inner:
            raise RuntimeError("wrapped by langchain") from inner
    except RuntimeError as wrapped:
        assert classify_error(wrapped) == "rate_limited"


def test_retry_delay_parsing():
    assert retry_delay_seconds(FakeApiError(429, "Please retry in 34.5s."), default=60) == 35
    assert retry_delay_seconds(FakeApiError(429, "{'retryDelay': '12s'}"), default=60) == 13
    assert retry_delay_seconds(FakeApiError(429, "no hint here"), default=60) == 60
    assert retry_delay_seconds(FakeApiError(429, "GenerateRequestsPerDayPerProjectPerModel"), default=60) == 3600


def test_not_configured_without_keys():
    client = GeminiClient(keys=[], model="m", timeout=5, cooldown=60)
    with pytest.raises(LLMNotConfigured):
        client.invoke(MESSAGES)


def test_uses_first_key_and_sticks_to_it(monkeypatch):
    client, log = make_client(monkeypatch, ["k1", "k2"], {"k1": "ok1", "k2": "ok2"})
    assert client.invoke(MESSAGES).content == "ok1"
    assert client.invoke(MESSAGES).content == "ok1"
    assert log == ["k1", "k1"]


def test_rotates_to_next_key_when_rate_limited_and_stays_there(monkeypatch):
    client, log = make_client(monkeypatch, ["k1", "k2", "k3"], {"k1": RATE_LIMIT, "k2": "ok2", "k3": "ok3"})
    assert client.invoke(MESSAGES).content == "ok2"
    assert log == ["k1", "k2"]
    log.clear()
    assert client.invoke(MESSAGES).content == "ok2"  # k1 đang nghỉ nên không gọi lại
    assert log == ["k2"]


def test_skips_invalid_key(monkeypatch):
    client, log = make_client(monkeypatch, ["bad", "good"], {"bad": BAD_KEY, "good": "ok"})
    assert client.invoke(MESSAGES).content == "ok"
    assert log == ["bad", "good"]


def test_all_keys_exhausted_raises_with_retry_after(monkeypatch):
    client, log = make_client(monkeypatch, ["k1", "k2"], {"k1": RATE_LIMIT, "k2": RATE_LIMIT}, cooldown=45)
    with pytest.raises(LLMUnavailable) as info:
        client.invoke(MESSAGES)
    assert 1 <= info.value.retry_after <= 46
    assert log == ["k1", "k2"]

    log.clear()
    with pytest.raises(LLMUnavailable):  # đều đang nghỉ: không gọi Gemini nữa
        client.invoke(MESSAGES)
    assert log == []


def test_key_comes_back_after_cooldown(monkeypatch):
    clock = Clock()
    script: dict[str, Exception | str] = {"k1": RATE_LIMIT, "k2": "ok2"}
    client, log = make_client(monkeypatch, ["k1", "k2"], script, clock=clock, cooldown=60)
    assert client.invoke(MESSAGES).content == "ok2"

    script["k1"] = "ok1"  # k1 hết limit
    clock.now += 61
    log.clear()
    # k2 vẫn là key hiện tại nên được dùng tiếp; khi k2 lỗi thì quay lại k1 vừa hết thời gian nghỉ.
    script["k2"] = RATE_LIMIT
    assert client.invoke(MESSAGES).content == "ok1"
    assert log == ["k2", "k1"]


def test_non_key_errors_do_not_burn_other_keys(monkeypatch):
    client, log = make_client(monkeypatch, ["k1", "k2"], {"k1": SERVER_ERROR, "k2": "ok2"})
    with pytest.raises(LLMError):
        client.invoke(MESSAGES)
    assert log == ["k1"]  # không thử k2 vì lỗi này không phải do key


def test_empty_and_duplicate_keys_are_ignored(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key_1", "A")
    monkeypatch.setattr(settings, "gemini_api_key_2", "")
    monkeypatch.setattr(settings, "gemini_api_key_3", "A")
    monkeypatch.setattr(settings, "gemini_api_key_4", " B ")
    assert settings.gemini_api_keys == ["A", "B"]


def test_module_exposes_logger_without_leaking_keys():
    assert gemini_module.logger.name == "app.llm"


def collect(client) -> str:
    return "".join(chunk.content for chunk in client.stream(MESSAGES))


def test_stream_rotates_when_first_chunk_is_rate_limited(monkeypatch):
    client, log = make_client(monkeypatch, ["k1", "k2"], {"k1": RATE_LIMIT, "k2": ["xin ", "chào"]})
    assert collect(client) == "xin chào"
    assert log == ["k1", "k2"]
    log.clear()
    assert collect(client) == "xin chào"
    assert log == ["k2"]  # k1 đang nghỉ


def test_stream_skips_invalid_key(monkeypatch):
    client, log = make_client(monkeypatch, ["bad", "good"], {"bad": BAD_KEY, "good": ["ok"]})
    assert collect(client) == "ok"
    assert log == ["bad", "good"]


def test_stream_all_keys_exhausted(monkeypatch):
    client, _ = make_client(monkeypatch, ["k1", "k2"], {"k1": RATE_LIMIT, "k2": RATE_LIMIT})
    with pytest.raises(LLMUnavailable):
        collect(client)


def test_stream_non_key_error_does_not_rotate(monkeypatch):
    client, log = make_client(monkeypatch, ["k1", "k2"], {"k1": SERVER_ERROR, "k2": ["ok"]})
    with pytest.raises(LLMError):
        collect(client)
    assert log == ["k1"]


def test_stream_error_after_first_chunk_cannot_rotate_but_blocks_exhausted_key(monkeypatch):
    client, log = make_client(monkeypatch, ["k1", "k2"], {"k1": ["một ", RATE_LIMIT], "k2": ["hai"]})
    got = []
    with pytest.raises(LLMError):
        for chunk in client.stream(MESSAGES):
            got.append(chunk.content)
    assert got == ["một "]  # đã lỡ gửi một phần nên không đổi key giữa chừng được
    log.clear()
    assert collect(client) == "hai"  # nhưng lần sau k1 đã bị cho nghỉ
    assert log == ["k2"]


def test_stream_not_configured():
    client = GeminiClient(keys=[], model="m", timeout=5, cooldown=60)
    with pytest.raises(LLMNotConfigured):
        collect(client)
