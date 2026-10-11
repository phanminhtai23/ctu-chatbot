import logging
import math
import time
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger("app.rag")

_BATCH = 16


class Embedder(Protocol):
    """Thứ duy nhất kho vector cần từ embedding; GeminiEmbedder và bản giả trong test đều đáp ứng."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class EmbeddingError(Exception):
    pass


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class GeminiEmbedder:
    """Embedding Gemini. `gemini-embedding-2` không dùng `task_type`: chỉ dẫn nằm ngay trong nội dung."""

    def __init__(self, api_key: str, model: str, dim: int):
        if not api_key:
            raise EmbeddingError("Chưa có EMBEDDING_MODEL_API_KEY (hoặc GEMINI_API_KEY_1) để tạo embedding")
        from google import genai  # import muộn: test không cần SDK nếu dùng embedder giả

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._dim = dim

    @classmethod
    def from_settings(cls) -> "GeminiEmbedder":
        keys = settings.gemini_api_keys
        api_key = settings.embedding_model_api_key.strip() or (keys[0] if keys else "")
        return cls(api_key, settings.embedding_model, settings.embedding_dim)

    def _embed(self, contents: list[str]) -> list[list[float]]:
        from google.genai import types

        config = types.EmbedContentConfig(output_dimensionality=self._dim)
        # gemini-embedding-2 gộp một list chuỗi thành MỘT vector; bọc từng text trong Content để mỗi text một vector.
        wrapped = [types.Content(parts=[types.Part(text=text)]) for text in contents]
        for attempt in range(5):
            try:
                result = self._client.models.embed_content(model=self._model, contents=wrapped, config=config)
                vectors = [_normalize(list(e.values)) for e in result.embeddings]
                if len(vectors) != len(contents):
                    raise EmbeddingError(f"Nhận {len(vectors)} vector cho {len(contents)} đoạn văn bản")
                return vectors
            except EmbeddingError:
                raise
            except Exception as exc:  # noqa: BLE001
                text = str(exc).lower()
                retryable = "429" in text or "resource_exhausted" in text or "503" in text or "unavailable" in text
                if not retryable or attempt == 4:
                    raise EmbeddingError(f"{type(exc).__name__}: {exc}") from exc
                wait = 5 * (attempt + 1)
                logger.warning("Embedding bị giới hạn, chờ %ds rồi thử lại", wait)
                time.sleep(wait)
        raise EmbeddingError("unreachable")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            vectors.extend(self._embed([f"title: none | text: {t}" for t in texts[start : start + _BATCH]]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([f"task: question answering | query: {text}"])[0]
