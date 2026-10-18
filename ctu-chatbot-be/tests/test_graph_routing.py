"""Đồ thị chat chọn đúng tuyến: quy chế -> RAG, ngoài quy chế -> tìm web, lạc đề -> từ chối không tra cứu."""

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import settings
from app.services.chat import graph as graph_module
from app.services.chat import scope
from app.services.chat.graph import build_chat_graph
from app.services.rag.store import Hit
from app.services.tools.web_search import WebResult, WebSearcher, WebSearchSession, _MinuteBudget, _TtlCache
from tests.test_web_search import FakeBackend

HIT = Hit(article=14, title="Cảnh báo học tập", chapter="", text="Điều 14. Cảnh báo học tập ...", score=0.5)
OFFICIAL = WebResult("Học phí CTU", "https://ctu.edu.vn/hoc-phi", "Học phí 2025: 500.000đ/tín chỉ")


@pytest.fixture(autouse=True)
def _scope_enabled(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", True)


class Retriever:
    def __init__(self, hits):
        self.hits, self.calls = hits, 0

    def retrieve(self, q):
        self.calls += 1
        return self.hits


class RoutedLLM:
    """Phân loại theo `route`, gọi web_search ở lượt đầu nếu có công cụ, rồi trả lời."""

    supports_tools = True

    def __init__(self, route):
        self.route = route
        self.systems: list[str] = []
        self.tool_names: list[list[str]] = []

    def stream(self, messages, tools=None):
        system = messages[0].content if isinstance(messages[0], SystemMessage) else ""
        if system.startswith("Phân loại"):
            yield AIMessageChunk(content=self.route)
            return
        self.systems.append(system)
        names = [t.name for t in tools or []]
        self.tool_names.append(names)
        if "web_search" in names and not any(m.type == "tool" for m in messages):
            yield AIMessageChunk(content="", tool_calls=[{"name": "web_search", "args": {"query": "học phí CTU"}, "id": "1"}])
            return
        yield AIMessageChunk(content="Học phí 500.000đ/tín chỉ [1].")


def _run(llm, monkeypatch, hits=(HIT,), text="Học phí một tín chỉ năm nay là bao nhiêu?"):
    session = WebSearchSession(WebSearcher(FakeBackend([OFFICIAL]), _TtlCache(), _MinuteBudget(100)))
    monkeypatch.setattr(graph_module, "WebSearchSession", lambda: session)
    monkeypatch.setattr(graph_module, "build_gpa_report", lambda *_: "")
    retriever = Retriever(list(hits))
    g = build_chat_graph(llm, InMemorySaver(), retriever)
    out = g.invoke({"messages": [HumanMessage(content=text)]}, {"configurable": {"thread_id": "t"}})
    return out["messages"][-1], session, retriever


def test_external_question_uses_web_search_and_returns_web_sources(monkeypatch):
    llm = RoutedLLM(scope.EXTERNAL)
    reply, session, _ = _run(llm, monkeypatch)
    assert reply.additional_kwargs["route"] == scope.EXTERNAL
    assert reply.additional_kwargs["sources"] == [{"title": "Học phí CTU", "url": OFFICIAL.url, "n": 1}]
    assert llm.tool_names[0] == ["web_search"]
    assert "Điều 14. Cảnh báo" not in llm.systems[0]  # không nhồi ngữ cảnh quy chế vào câu hỏi ngoài quy chế
    assert len(session.results) == 1


def test_regulation_question_keeps_rag_and_calculator_without_web(monkeypatch):
    llm = RoutedLLM(scope.REGULATION)
    reply, _, _ = _run(llm, monkeypatch, text="Mình bị cảnh báo học tập thì sao?")
    assert reply.additional_kwargs["route"] == scope.REGULATION
    assert "Điều 14. Cảnh báo" in llm.systems[0]
    assert "web_search" not in llm.tool_names[0]


def test_offtopic_question_gets_no_tools_and_no_context(monkeypatch):
    llm = RoutedLLM(scope.OFFTOPIC)
    reply, session, _ = _run(llm, monkeypatch, text="Viết bài thơ về mùa thu")
    assert reply.additional_kwargs["route"] == scope.OFFTOPIC
    assert llm.tool_names[0] == []
    assert session.results == []
    assert reply.additional_kwargs["sources"] == []


def test_web_search_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", False)
    llm = RoutedLLM(scope.EXTERNAL)
    reply, _, _ = _run(llm, monkeypatch, text="Mình bị cảnh báo học tập thì sao?")
    assert reply.additional_kwargs["route"] == scope.REGULATION
    assert "web_search" not in llm.tool_names[0]


class QueryAwareRetriever:
    """Câu ghép (có câu quy chế phía trước) giống quy chế rất nhiều; riêng câu ký túc xá thì giống rất ít."""

    def retrieve(self, q):
        high = "học bổng" in q
        return [Hit(article=9, title="Học bổng", chapter="", text="Điều 9. Học bổng ...", score=0.82 if high else 0.58)]


def test_follow_up_that_changes_topic_is_routed_by_the_latest_question_alone(monkeypatch):
    session = WebSearchSession(WebSearcher(FakeBackend([OFFICIAL]), _TtlCache(), _MinuteBudget(100)))
    monkeypatch.setattr(graph_module, "WebSearchSession", lambda: session)
    monkeypatch.setattr(graph_module, "build_gpa_report", lambda *_: "")
    llm = RoutedLLM(scope.EXTERNAL)
    g = build_chat_graph(llm, InMemorySaver(), QueryAwareRetriever())
    config = {"configurable": {"thread_id": "t2"}}
    g.invoke({"messages": [HumanMessage(content="Học bổng xét theo ĐTBCHK thế nào?")]}, config)
    out = g.invoke({"messages": [HumanMessage(content="Ký túc xá giá phòng bao nhiêu một tháng?")]}, config)
    assert out["messages"][-1].additional_kwargs["route"] == scope.EXTERNAL
