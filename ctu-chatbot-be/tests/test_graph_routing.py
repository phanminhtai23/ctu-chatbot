"""Đồ thị chat chọn đúng tuyến: quy chế -> RAG, ngoài quy chế -> tìm web, lạc đề -> từ chối không tra cứu."""

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
import copy

from app.core.config import settings
from app.services.chat import graph as graph_module
from app.services.chat import route_catalog
from app.services.chat import scope
from app.services.chat.graph import build_chat_graph
from app.services.rag.store import Hit
from app.services.rag.chunker import split_into_articles
from app.services.rag.store import Retriever as VectorRetriever
from app.services.rag.store import VectorStore
from tests.test_ingest import FakeEmbedder
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


def test_custom_document_route_uses_its_prompt_and_does_not_enable_web(monkeypatch):
    config = copy.deepcopy(route_catalog.DEFAULT_CONFIG)
    node = {
        "id": "academic-calendar",
        "label": "Lịch học",
        "kind": "document",
        "prompt": "Câu hỏi về lịch học, lịch thi và lịch nghỉ học kỳ.",
        "collection": "doc-academic-calendar-v1",
        "source": "documents/20261018094500-a1b2c3/clean.md",
        "document_slug": "lich-hoc",
        "version": "v1",
    }
    config["nodes"].append(node)
    config["edges"].append({"from": "router", "to": node["id"], "enabled": True})
    monkeypatch.setattr(settings, "vector_docs_dir", str(route_catalog.vector_docs_root()))
    route_catalog.save_config(config)

    llm = RoutedLLM("academic-calendar")
    reply, session, _ = _run(llm, monkeypatch, text="Lịch thi học kỳ này khi nào?")
    assert reply.additional_kwargs["route"] == "academic-calendar"
    assert "lịch học, lịch thi" in llm.systems[0]
    assert "web_search" not in llm.tool_names[0]
    assert session.results == []


def test_disabled_route_edge_is_not_available_to_classifier(monkeypatch):
    config = copy.deepcopy(route_catalog.DEFAULT_CONFIG)
    config["edges"] = [
        {**edge, "enabled": False} if edge["to"] == scope.EXTERNAL else edge for edge in config["edges"]
    ]
    route_catalog.save_config(config)
    llm = RoutedLLM(scope.EXTERNAL)
    reply, _, _ = _run(llm, monkeypatch)
    assert reply.additional_kwargs["route"] == scope.REGULATION


def test_document_route_retrieves_from_selected_collection(monkeypatch):
    config = copy.deepcopy(route_catalog.DEFAULT_CONFIG)
    collection = "doc-academic-calendar"
    node = {
        "id": "academic-calendar",
        "label": "Lịch học",
        "kind": "document",
        "prompt": "Câu hỏi về lịch học và lịch thi.",
        "collection": collection,
        "source": "documents/20261018094500-a1b2c3/clean.md",
        "document_slug": "lich-hoc",
        "version": "20261018094500-a1b2c3",
        "status": "synced",
    }
    config["nodes"].append(node)
    config["edges"].append({"from": "router", "to": node["id"], "enabled": True})
    route_catalog.save_config(config)

    embedder = FakeEmbedder()
    base = VectorStore(embedder)
    base.for_collection(collection).index(
        split_into_articles(
            "# Lịch học\n\n### Điều 1. Lịch thi\nLịch thi học kỳ được công bố trên cổng thông tin đào tạo."
        )
    )
    class CitedRoutedLLM(RoutedLLM):
        def stream(self, messages, tools=None):
            system = messages[0].content if isinstance(messages[0], SystemMessage) else ""
            if system.startswith("Phân loại"):
                yield AIMessageChunk(content=self.route)
            else:
                self.systems.append(system)
                yield AIMessageChunk(content="Theo Điều 1, lịch thi được công bố trên cổng thông tin đào tạo.")

    llm = CitedRoutedLLM(node["id"])
    monkeypatch.setattr(graph_module, "build_gpa_report", lambda *_: "")
    graph = build_chat_graph(llm, InMemorySaver(), VectorRetriever(base))
    result = graph.invoke(
        {"messages": [HumanMessage(content="Lịch thi học kỳ khi nào?")]},
        {"configurable": {"thread_id": "custom-document"}},
    )

    assert result["messages"][-1].additional_kwargs["route"] == node["id"]
    assert "cổng thông tin đào tạo" in llm.systems[0]
    assert result["messages"][-1].additional_kwargs["sources"] == [
        {
            "article": 1,
            "title": "Lịch thi",
            "document_url": f"/api/v1/documents/catalog/{node['document_slug']}/{node['version']}/source",
        }
    ]
