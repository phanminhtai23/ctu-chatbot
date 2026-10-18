import logging
import math
import time
from collections.abc import Callable
from typing import Protocol

from app.core.config import settings
from app.services.llm.key_pool import KeyPool

logger = logging.getLogger("app.rag")

_BATCH = 16
RATE_LIMIT_COOLDOWN = 60  # key bị 429 thì nghỉ chừng này giây (hạn mức embedding tính theo phút)
INVALID_KEY_COOLDOWN = 3600
_MAX_WAIT_FOR_KEY = 20  # tất cả key cùng nghỉ: chờ tối đa chừng này giây rồi thử lại một lần


class Embedder(Protocol):
    """Thứ duy nhất kho vector cần từ embedding; GeminiEmbedder và bản giả trong test đều đáp ứng."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class EmbeddingError(Exception):
    pass


class CachedQueryEmbedder:
    """Bọc một embedder: nhớ vector của các câu hỏi vừa nhúng. Một lượt chat tra cứu cả văn bản quy chế lẫn kiến thức
    bổ sung (và có khi tra cứu lại riêng câu mới nhất để chọn tuyến), nên cùng một câu hỏi được nhúng nhiều lần;
    cache giúp chỉ tốn MỘT lần gọi API embedding cho mỗi câu."""

    def __init__(self, inner: Embedder, size: int = 64):
        self._inner = inner
        self._size = size
        self._cache: dict[str, list[float]] = {}

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        cached = self._cache.get(text)
        if cached is None:
            cached = self._inner.embed_query(text)
            if len(self._cache) >= self._size:
                self._cache.pop(next(iter(self._cache)))  # bỏ câu cũ nhất
            self._cache[text] = cached
        return cached


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _classify(exc: BaseException) -> str:
    """'rate_limited' | 'invalid_key' | 'transient' | 'other'."""
    text = str(exc).lower()
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429 or "429" in text or "resource_exhausted" in text or "quota" in text:
        return "rate_limited"
    if code in (401, 403) or "api key not valid" in text or "api_key_invalid" in text or "permission_denied" in text:
        return "invalid_key"
    if code in (500, 502, 503, 504) or "503" in text or "unavailable" in text or "overloaded" in text:
        return "transient"
    return "other"


class GeminiEmbedder:
    """Embedding Gemini, xoay nhiều API key: key nào hết hạn mức (429) thì nghỉ và chuyển sang key kế tiếp.

    `gemini-embedding-2` không dùng `task_type`: chỉ dẫn nằm ngay trong nội dung.
    """

    def __init__(
        self,
        api_keys: list[str] | str,
        model: str,
        dim: int,
        client_factory: Callable[[str], object] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        keys = [api_keys] if isinstance(api_keys, str) else list(api_keys)
        keys = list(dict.fromkeys(k.strip() for k in keys if k and k.strip()))
        if not keys:
            raise EmbeddingError("Chưa có EMBEDDING_MODEL_API_KEY (hoặc GEMINI_API_KEY_*) để tạo embedding")
        self._pool = KeyPool(keys)
        self._model = model
        self._dim = dim
        self._sleep = sleep
        self._client_factory = client_factory or self._default_client
        self._clients: dict[int, object] = {}

    @staticmethod
    def _default_client(api_key: str):
        from google import genai  # import muộn: test không cần SDK nếu dùng embedder giả

        return genai.Client(api_key=api_key)

    @classmethod
    def from_settings(cls) -> "GeminiEmbedder":
        # Key riêng cho embedding (nếu có) được ưu tiên, sau đó mới tới các key Gemini dùng chung với chat.
        keys = [settings.embedding_model_api_key, *settings.gemini_api_keys]
        return cls(keys, settings.embedding_model, settings.embedding_dim)

    def _client(self, idx: int, key: str):
        if idx not in self._clients:
            self._clients[idx] = self._client_factory(key)
        return self._clients[idx]

    def _call(self, idx: int, key: str, contents: list[str]) -> list[list[float]]:
        from google.genai import types

        config = types.EmbedContentConfig(output_dimensionality=self._dim)
        # gemini-embedding-2 gộp một list chuỗi thành MỘT vector; bọc từng text trong Content để mỗi text một vector.
        wrapped = [types.Content(parts=[types.Part(text=text)]) for text in contents]
        result = self._client(idx, key).models.embed_content(model=self._model, contents=wrapped, config=config)
        vectors = [_normalize(list(e.values)) for e in result.embeddings]
        if len(vectors) != len(contents):
            raise EmbeddingError(f"Nhận {len(vectors)} vector cho {len(contents)} đoạn văn bản")
        return vectors

    def _embed(self, contents: list[str]) -> list[list[float]]:
        last_error = ""
        for round_ in range(3):
            tried_any = False
            for idx, key in self._pool.candidates():
                tried_any = True
                try:
                    vectors = self._call(idx, key, contents)
                except EmbeddingError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    kind = _classify(exc)
                    last_error = f"{type(exc).__name__}: {exc}"
                    if kind == "rate_limited":
                        logger.warning("Embedding key #%d hết hạn mức, nghỉ %ds và chuyển key khác", idx + 1, RATE_LIMIT_COOLDOWN)
                        self._pool.block(idx, RATE_LIMIT_COOLDOWN)
                        continue
                    if kind == "invalid_key":
                        logger.error("Embedding key #%d bị từ chối, bỏ qua %ds", idx + 1, INVALID_KEY_COOLDOWN)
                        self._pool.block(idx, INVALID_KEY_COOLDOWN)
                        continue
                    if kind == "transient":
                        logger.warning("Embedding lỗi tạm thời (%s), thử lại", last_error[:120])
                        self._sleep(3 * (round_ + 1))
                        break  # thử lại từ vòng sau với cùng key
                    raise EmbeddingError(last_error) from exc
                self._pool.mark_ok(idx)
                return vectors
            if not tried_any:
                # mọi key đang nghỉ: chờ key sớm nhất dùng lại được (không chờ quá lâu)
                wait = self._pool.seconds_until_available()
                if wait > _MAX_WAIT_FOR_KEY or round_ == 2:
                    break
                self._sleep(wait + 0.5)
        raise EmbeddingError(f"Embedding thất bại, mọi key đều hết hạn mức hoặc lỗi: {last_error[:200]}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            vectors.extend(self._embed([f"title: none | text: {t}" for t in texts[start : start + _BATCH]]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([f"task: question answering | query: {text}"])[0]
