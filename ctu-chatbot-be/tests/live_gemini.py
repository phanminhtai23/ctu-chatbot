"""Tiện ích cho test live bằng Gemini thật mà KHÔNG vượt quota free.

- `ThrottledLLM`: giãn cách tối thiểu giữa 2 lần gọi (mặc định 7s ~ 8 lần/phút, thấp hơn nhiều so với 15 RPM của free tier),
  trần số lần gọi mỗi lượt chạy và mỗi ngày (lưu trong `tests/.live_quota.json`). Hết trần hoặc bị 429 thì dừng (skip),
  không cố gọi tiếp.
- `CachedEmbedder`: cùng một câu hỏi chỉ embed một lần trong cả phiên test.
"""

import json
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from langchain_core.messages import AIMessageChunk, BaseMessage

from app.services.llm.gemini import LLMError, LLMUnavailable

QUOTA_FILE = Path(__file__).with_name(".live_quota.json")
MIN_INTERVAL_SECONDS = 7.0
MAX_CALLS_PER_RUN = 90
MAX_CALLS_PER_DAY = 250


def _load_daily_count() -> int:
    try:
        data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        return int(data["count"]) if data.get("date") == date.today().isoformat() else 0
    except (OSError, ValueError, KeyError):
        return 0


def _save_daily_count(count: int) -> None:
    try:
        QUOTA_FILE.write_text(json.dumps({"date": date.today().isoformat(), "count": count}), encoding="utf-8")
    except OSError:
        pass  # không ghi được thì chỉ mất phần đếm theo ngày, trần theo lượt chạy vẫn còn


class ThrottledLLM:
    def __init__(self, inner, min_interval: float = MIN_INTERVAL_SECONDS):
        self._inner = inner
        self._min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0
        self._stopped: str | None = None

    def stream(self, messages: list[BaseMessage]) -> Iterator[AIMessageChunk]:
        if self._stopped:
            pytest.skip(self._stopped)
        if self.calls >= MAX_CALLS_PER_RUN:
            self._stopped = f"đã đủ {MAX_CALLS_PER_RUN} lần gọi LLM trong lượt chạy này (trần bảo vệ quota free)"
            pytest.skip(self._stopped)
        daily = _load_daily_count()
        if daily >= MAX_CALLS_PER_DAY:
            self._stopped = f"đã gọi {daily} lần hôm nay (trần {MAX_CALLS_PER_DAY}/ngày bảo vệ quota free)"
            pytest.skip(self._stopped)

        for attempt in range(3):
            wait = self._last_call + self._min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            self.calls += 1
            daily += 1
            _save_daily_count(daily)

            try:
                yield from self._inner.stream(messages)
                return
            except LLMUnavailable as exc:
                self._stopped = f"Gemini báo hết hạn mức (429), dừng để không gọi thêm; thử lại sau {exc.retry_after}s"
                pytest.skip(self._stopped)
            except LLMError as exc:
                text = str(exc).lower()
                if "429" in text or "quota" in text or "resource_exhausted" in text:
                    self._stopped = "Gemini báo hết hạn mức, dừng để không gọi thêm"
                    pytest.skip(self._stopped)
                # 503 "high demand" là quá tải tạm thời phía Google, không liên quan quota: chờ rồi thử lại tối đa 2 lần.
                if ("503" in text or "unavailable" in text) and attempt < 2:
                    time.sleep(20)
                    continue
                raise


EMBED_CACHE_FILE = Path(__file__).with_name(".live_embed_cache.json")
EMBED_MIN_INTERVAL_SECONDS = 2.0  # ~30 RPM, thấp hơn nhiều so với trần 100 RPM của gemini-embedding-2 (free tier)
MAX_EMBED_CALLS_PER_RUN = 120


class CachedEmbedder:
    """Embedding có điều tiết: giãn cách giữa các lần gọi, trần mỗi lượt chạy, và cache câu hỏi lên đĩa
    để chạy lại test không tốn thêm quota (câu hỏi cố định nên vector không đổi)."""

    def __init__(self, inner, cache_file: Path = EMBED_CACHE_FILE, min_interval: float = EMBED_MIN_INTERVAL_SECONDS):
        self._inner = inner
        self._cache_file = cache_file
        self._min_interval = min_interval
        self._last_call = 0.0
        self.calls = 0
        try:
            self._queries: dict[str, list[float]] = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._queries = {}

    def _throttle(self) -> None:
        if self.calls >= MAX_EMBED_CALLS_PER_RUN:
            pytest.skip(f"đã đủ {MAX_EMBED_CALLS_PER_RUN} lần gọi embedding trong lượt chạy này (trần bảo vệ quota free)")
        wait = self._last_call + self._min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()
        self.calls += 1

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._throttle()
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if text not in self._queries:
            self._throttle()
            self._queries[text] = self._inner.embed_query(text)
            try:
                self._cache_file.write_text(json.dumps(self._queries), encoding="utf-8")
            except OSError:
                pass
        return self._queries[text]
