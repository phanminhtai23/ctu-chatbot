import pytest

from app.services.tools.web_search import (
    WebResult,
    WebSearcher,
    WebSearchSession,
    _MinuteBudget,
    _TtlCache,
    is_official,
    rank_results,
)


class FakeBackend:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.queries: list[str] = []

    def search(self, query, max_results):
        self.queries.append(query)
        if self.error:
            raise self.error
        return list(self.results)


OFFICIAL = WebResult("Học phí", "https://dsa.ctu.edu.vn/hoc-phi", "Học phí 2025")
OTHER = WebResult("Blog", "https://blog.example.com/ctu", "bài viết")


def test_is_official_matches_domain_and_subdomains_only():
    assert is_official("https://ctu.edu.vn/x")
    assert is_official("https://dsa.ctu.edu.vn/x")
    assert not is_official("https://ctu.edu.vn.evil.com/x")
    assert not is_official("https://notctu.edu.vn/x")


def test_rank_puts_official_first_dedups_and_drops_non_http():
    ranked = rank_results([OTHER, OFFICIAL, OFFICIAL, WebResult("x", "javascript:alert(1)", ""), WebResult("y", "", "")])
    assert [r.url for r in ranked] == [OFFICIAL.url, OTHER.url]


def test_cache_avoids_second_backend_call_and_expires():
    now = [0.0]
    backend = FakeBackend([OFFICIAL])
    searcher = WebSearcher(backend, _TtlCache(ttl=10, clock=lambda: now[0]), _MinuteBudget(100))
    searcher.search("Học phí  CTU")
    searcher.search("học phí ctu")  # chuẩn hóa hoa thường/khoảng trắng
    assert len(backend.queries) == 1
    now[0] = 11
    searcher.search("học phí ctu")
    assert len(backend.queries) == 2


def test_global_budget_blocks_search_storm():
    backend = FakeBackend([OFFICIAL])
    searcher = WebSearcher(backend, _TtlCache(), _MinuteBudget(2))
    searcher.search("a")
    searcher.search("b")
    with pytest.raises(RuntimeError):
        searcher.search("c")
    searcher.search("a")  # đã có trong cache nên không tốn lượt


def _session(results=None, error=None, max_searches=2):
    backend = FakeBackend(results or [OFFICIAL, OTHER], error)
    return WebSearchSession(WebSearcher(backend, _TtlCache(), _MinuteBudget(100)), max_searches), backend


def test_session_limits_searches_per_turn():
    session, backend = _session(max_searches=2)
    session.search("một")
    session.search("hai")
    assert session.search("ba").startswith("LỖI")
    assert len(backend.queries) == 2


def test_session_returns_error_text_instead_of_raising():
    session, _ = _session(error=ConnectionError("down"))
    assert session.search("x").startswith("LỖI")


def test_session_numbers_continue_across_searches_without_duplicates():
    session, backend = _session()
    first = session.search("một")
    assert "[1]" in first and "[2]" in first and "trang chính thức" in first
    backend.results = [OFFICIAL, WebResult("Mới", "https://ctu.edu.vn/moi", "mới")]
    second = session.search("hai")
    assert "[3] Mới" in second and OFFICIAL.url not in second


def test_sources_follow_citations_and_fall_back_to_official():
    session, _ = _session()
    session.search("x")
    assert session.sources_for("Học phí là ... [2]") == [{"title": "Blog", "url": OTHER.url, "n": 2}]
    both = session.sources_for("Giá 220.000 [1, 2].")
    assert [(x["n"], x["url"]) for x in both] == [(1, OFFICIAL.url), (2, OTHER.url)]
    assert session.sources_for("Không đánh số") == [{"title": "Học phí", "url": OFFICIAL.url, "n": 1}]
    assert session.sources_for("Số lạ [9]") == [{"title": "Học phí", "url": OFFICIAL.url, "n": 1}]


def test_tool_is_named_web_search_and_runs():
    session, _ = _session()
    tool = session.as_tool()
    assert tool.name == "web_search"
    assert "URL:" in tool.invoke({"query": "học phí"})
