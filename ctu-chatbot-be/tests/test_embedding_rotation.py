"""Xoay API key cho embedding: key hết hạn mức (429) thì chuyển sang key kế tiếp."""

import pytest

from app.core.config import settings
from app.services.rag.embeddings import EmbeddingError, GeminiEmbedder


class FakeApiError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(f"{code} {message}")
        self.code = code


class _Embedding:
    def __init__(self, values):
        self.values = values


class _Result:
    def __init__(self, n: int):
        self.embeddings = [_Embedding([3.0, 4.0]) for _ in range(n)]  # độ dài 5 -> chuẩn hoá thành [0.6, 0.8]


class FakeClient:
    """Client giả theo từng key; `behaviour[key]` là một list lỗi/None được tiêu thụ lần lượt."""

    def __init__(self, key: str, behaviour: dict[str, list], log: list[str]):
        self._key, self._behaviour, self._log = key, behaviour, log
        self.models = self

    def embed_content(self, model, contents, config):
        self._log.append(self._key)
        queue = self._behaviour.get(self._key, [])
        outcome = queue.pop(0) if queue else None
        if outcome is not None:
            raise outcome
        return _Result(len(contents))


def make(keys, behaviour=None, sleeps=None):
    behaviour = behaviour or {}
    log: list[str] = []
    sleeps = sleeps if sleeps is not None else []
    embedder = GeminiEmbedder(
        keys,
        "models/gemini-embedding-2",
        768,
        client_factory=lambda key: FakeClient(key, behaviour, log),
        sleep=sleeps.append,
    )
    return embedder, log


def test_uses_first_key_when_it_works():
    embedder, log = make(["k1", "k2"])
    assert embedder.embed_query("hi") == [pytest.approx(0.6), pytest.approx(0.8)]
    assert log == ["k1"]


def test_rotates_to_next_key_on_429():
    embedder, log = make(["k1", "k2"], {"k1": [FakeApiError(429, "RESOURCE_EXHAUSTED quota")]})
    assert len(embedder.embed_query("hi")) == 2
    assert log == ["k1", "k2"]


def test_exhausted_key_is_skipped_on_next_calls():
    embedder, log = make(["k1", "k2"], {"k1": [FakeApiError(429, "quota")]})
    embedder.embed_query("a")
    embedder.embed_query("b")
    assert log == ["k1", "k2", "k2"]  # k1 đang nghỉ nên lần hai đi thẳng k2


def test_invalid_key_is_skipped_too():
    embedder, log = make(["bad", "good"], {"bad": [FakeApiError(403, "PERMISSION_DENIED api key not valid")]})
    assert len(embedder.embed_query("hi")) == 2
    assert log == ["bad", "good"]


def test_all_keys_exhausted_raises_embedding_error_without_hammering():
    behaviour = {k: [FakeApiError(429, "quota")] * 5 for k in ("k1", "k2")}
    embedder, log = make(["k1", "k2"], behaviour)
    with pytest.raises(EmbeddingError):
        embedder.embed_query("hi")
    assert len(log) <= 4  # mỗi key thử đúng một lần, rồi key nghỉ, không gọi dồn dập


def test_transient_503_retries_same_key():
    sleeps: list[float] = []
    embedder, log = make(["k1"], {"k1": [FakeApiError(503, "UNAVAILABLE high demand")]}, sleeps)
    assert len(embedder.embed_query("hi")) == 2
    assert log == ["k1", "k1"]
    assert sleeps  # có chờ trước khi thử lại


def test_unknown_error_is_not_retried_on_other_keys():
    embedder, log = make(["k1", "k2"], {"k1": [FakeApiError(400, "INVALID_ARGUMENT bad request")]})
    with pytest.raises(EmbeddingError):
        embedder.embed_query("hi")
    assert log == ["k1"]


def test_documents_are_batched_and_keep_order():
    embedder, log = make(["k1"])
    vectors = embedder.embed_documents([f"đoạn {i}" for i in range(40)])
    assert len(vectors) == 40
    assert len(log) == 3  # 16 + 16 + 8


def test_requires_at_least_one_key():
    with pytest.raises(EmbeddingError):
        GeminiEmbedder([" ", ""], "m", 768)


def test_from_settings_prefers_embedding_key_then_shared_gemini_keys(monkeypatch):
    monkeypatch.setattr(settings, "embedding_model_api_key", "EMB")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    for i in range(1, 10):
        monkeypatch.setattr(settings, f"gemini_api_key_{i}", "")
    monkeypatch.setattr(settings, "gemini_api_key_1", "G1")
    monkeypatch.setattr(settings, "gemini_api_key_2", "EMB")  # trùng thì bỏ
    monkeypatch.setattr(settings, "gemini_api_key_3", "G3")

    embedder = GeminiEmbedder.from_settings()
    assert embedder._pool._keys == ["EMB", "G1", "G3"]
