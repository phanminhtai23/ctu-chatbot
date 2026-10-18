"""Công cụ tìm kiếm web cho câu hỏi NGOÀI văn bản quy chế (học phí, lịch thi, ký túc xá, thông báo của Trường...).

Dùng DuckDuckGo (gói `ddgs`, không cần key; tìm kiếm có căn cứ của Gemini bị 429 ở gói miễn phí). Kết quả của
`ctu.edu.vn` và các trang con được xếp lên đầu vì đó là nguồn chính thức. Nội dung web là DỮ LIỆU KHÔNG TIN CẬY:
được bọc trong khối riêng và prompt dặn model không làm theo chỉ dẫn nằm trong đó.

Mỗi lượt chat tạo một `WebSearchSession` riêng: nó giới hạn số lần tìm và gom các nguồn đã dùng để hiện cho
người dùng. Cache và giới hạn tốc độ thì dùng chung cho cả server (một process).
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from langchain_core.tools import StructuredTool

logger = logging.getLogger("app.chat")

OFFICIAL_DOMAIN = "ctu.edu.vn"
MAX_RESULTS = 5
MAX_SEARCHES_PER_TURN = 2
SNIPPET_CHARS = 400
CACHE_TTL_SECONDS = 600
CACHE_MAX_ENTRIES = 200
GLOBAL_MAX_PER_MINUTE = 20  # trần tìm kiếm của cả server, tránh bị DuckDuckGo chặn


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str

    @property
    def official(self) -> bool:
        return is_official(self.url)


class Searcher(Protocol):
    def search(self, query: str, max_results: int) -> list[WebResult]: ...


def is_official(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == OFFICIAL_DOMAIN or host.endswith("." + OFFICIAL_DOMAIN)


def rank_results(results: list[WebResult], limit: int = MAX_RESULTS) -> list[WebResult]:
    """Bỏ trùng URL, đưa trang chính thức của Trường lên trước (giữ nguyên thứ tự trong mỗi nhóm)."""
    seen: set[str] = set()
    unique = []
    for r in results:
        if r.url.startswith(("http://", "https://")) and r.url not in seen:
            seen.add(r.url)
            unique.append(r)
    unique.sort(key=lambda r: not r.official)  # sort ổn định
    return unique[:limit]


class DuckDuckGoSearcher:
    def search(self, query: str, max_results: int) -> list[WebResult]:
        from ddgs import DDGS  # import muộn: gói chỉ cần khi thật sự tìm web

        raw = DDGS(timeout=10).text(query, region="vn-vi", max_results=max_results * 2)
        return [
            WebResult(title=str(r.get("title") or ""), url=str(r.get("href") or ""), snippet=str(r.get("body") or ""))
            for r in raw or []
        ]


class _TtlCache:
    def __init__(self, ttl: float = CACHE_TTL_SECONDS, size: int = CACHE_MAX_ENTRIES, clock=time.monotonic):
        self._ttl, self._size, self._clock = ttl, size, clock
        self._data: dict[str, tuple[float, list[WebResult]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> list[WebResult] | None:
        with self._lock:
            item = self._data.get(key)
            if item is None or self._clock() - item[0] > self._ttl:
                self._data.pop(key, None)
                return None
            return item[1]

    def put(self, key: str, value: list[WebResult]) -> None:
        with self._lock:
            if len(self._data) >= self._size:
                self._data.pop(next(iter(self._data)))
            self._data[key] = (self._clock(), value)


class _MinuteBudget:
    def __init__(self, per_minute: int, clock=time.monotonic):
        self._max, self._clock = per_minute, clock
        self._stamps: list[float] = []
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            now = self._clock()
            self._stamps = [t for t in self._stamps if now - t < 60]
            if len(self._stamps) >= self._max:
                return False
            self._stamps.append(now)
            return True


class WebSearcher:
    """Tìm web có cache + trần tốc độ toàn server; dùng chung giữa các lượt chat."""

    def __init__(self, backend: Searcher | None = None, cache: _TtlCache | None = None, budget: _MinuteBudget | None = None):
        self._backend = backend or DuckDuckGoSearcher()
        self._cache = cache or _TtlCache()
        self._budget = budget or _MinuteBudget(GLOBAL_MAX_PER_MINUTE)

    def search(self, query: str) -> list[WebResult]:
        key = " ".join(query.lower().split())
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if not self._budget.take():
            raise RuntimeError("Đang tìm web quá nhiều, thử lại sau ít phút.")
        results = rank_results(self._backend.search(query, MAX_RESULTS))
        self._cache.put(key, results)
        return results


_shared: WebSearcher | None = None


def shared_searcher() -> WebSearcher:
    global _shared
    if _shared is None:
        _shared = WebSearcher()
    return _shared


def format_results(results: list[WebResult], start: int = 1) -> str:
    if not results:
        return "Không tìm thấy kết quả nào."
    lines = []
    for i, r in enumerate(results, start):
        tag = " (trang chính thức của Trường)" if r.official else ""
        lines.append(f"[{i}] {r.title}{tag}\nURL: {r.url}\n{r.snippet[:SNIPPET_CHARS]}")
    return "\n\n".join(lines)


class WebSearchSession:
    """Một lượt chat: giới hạn số lần tìm và gom nguồn đã dùng (đánh số [n] liên tục giữa các lần tìm)."""

    def __init__(self, searcher: WebSearcher | None = None, max_searches: int = MAX_SEARCHES_PER_TURN):
        self._searcher = searcher or shared_searcher()
        self._max = max_searches
        self._count = 0
        self.results: list[WebResult] = []

    def search(self, query: str) -> str:
        if self._count >= self._max:
            return "LỖI: đã tìm đủ số lần cho phép trong lượt này; hãy trả lời dựa trên kết quả đã có."
        self._count += 1
        try:
            found = self._searcher.search(query)
        except Exception as exc:  # noqa: BLE001 - tìm web hỏng thì bot vẫn trả lời được (nói là chưa tra cứu được)
            logger.warning("Tìm web lỗi: %s", exc)
            return "LỖI: hiện không tìm được trên web. Hãy nói thật với người dùng là chưa tra cứu được và gợi ý xem website ctu.edu.vn."
        fresh = [r for r in found if all(r.url != old.url for old in self.results)]
        start = len(self.results) + 1
        self.results.extend(fresh)
        return format_results(fresh, start)

    def sources_for(self, answer: str) -> list[dict]:
        """Các nguồn web mà câu trả lời thực sự trích dẫn bằng [n]; nếu model không đánh số thì lấy các trang chính thức."""
        import re

        cited = sorted(
            {int(n) for group in re.findall(r"\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\]", answer) for n in re.findall(r"\d+", group)}
        )  # nhận cả "[1]" lẫn "[1, 2]"
        chosen = [self.results[n - 1] for n in cited if 1 <= n <= len(self.results)]
        if not chosen:
            chosen = [r for r in self.results if r.official][:3]
        return [{"title": r.title, "url": r.url} for r in chosen]

    def as_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.search,
            name="web_search",
            description=(
                "Tìm thông tin trên web (ưu tiên trang ctu.edu.vn). Dùng cho câu hỏi về Trường Đại học Cần Thơ NẰM NGOÀI "
                "văn bản quy chế học vụ: học phí, lịch thi/lịch học, ký túc xá, điểm chuẩn, thủ tục, liên hệ, thông báo. "
                "Truyền câu truy vấn ngắn gọn bằng tiếng Việt, nên có 'Đại học Cần Thơ' và năm nếu liên quan."
            ),
        )
