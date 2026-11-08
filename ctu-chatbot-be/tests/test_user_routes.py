"""Người dùng chọn tài liệu / nguồn muốn hỏi (mặc định: tất cả)."""

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import settings
from app.services.chat import graph as graph_module
from app.services.chat.graph import build_chat_graph
from app.services.rag.store import Hit

HIT = Hit(article=14, title="Cảnh báo học tập", chapter="", text="Điều 14. Cảnh báo học tập ...", score=0.5)


class Retriever:
    def retrieve(self, q, **_):
        return [HIT]


class Spy:
    supports_tools = False

    def __init__(self):
        self.classify_prompts: list[str] = []

    def stream(self, messages, tools=None):
        system = messages[0].content if isinstance(messages[0], SystemMessage) else ""
        if system.startswith("Phân loại"):
            self.classify_prompts.append(system)
            yield AIMessageChunk(content="regulation")
            return
        yield AIMessageChunk(content="Trả lời.")


def _ask(monkeypatch, allowed):
    monkeypatch.setattr(settings, "web_search_enabled", True)
    monkeypatch.setattr(graph_module, "build_gpa_report", lambda *_: "")
    llm = Spy()
    graph = build_chat_graph(llm, InMemorySaver(), Retriever())
    configurable = {"thread_id": "t", **({"allowed_routes": allowed} if allowed else {})}
    graph.invoke({"messages": [HumanMessage(content="Học phí một tín chỉ năm nay là bao nhiêu?")]}, {"configurable": configurable})
    return llm.classify_prompts[0]


def test_default_offers_every_route(monkeypatch):
    prompt = _ask(monkeypatch, None)
    assert "- regulation:" in prompt and "- external:" in prompt


def test_chosen_routes_hide_the_others_but_keep_smalltalk_and_offtopic(monkeypatch):
    prompt = _ask(monkeypatch, ["regulation"])
    assert "- regulation:" in prompt
    assert "- external:" not in prompt
    assert "- smalltalk:" in prompt and "- offtopic:" in prompt


def test_stale_selection_falls_back_to_all_routes(monkeypatch):
    prompt = _ask(monkeypatch, ["da-bi-xoa"])
    assert "- regulation:" in prompt and "- external:" in prompt


def test_user_can_save_and_clear_route_choice(client, auth_headers):
    assert client.get("/api/v1/me", headers=auth_headers).json()["document_routes"] is None
    saved = client.patch("/api/v1/me", headers=auth_headers, json={"document_routes": ["regulation", "regulation", "external"]})
    assert saved.status_code == 200 and saved.json()["document_routes"] == ["regulation", "external"]
    assert client.get("/api/v1/me", headers=auth_headers).json()["document_routes"] == ["regulation", "external"]
    assert client.patch("/api/v1/me", headers=auth_headers, json={"name": "Bạn"}).json()["document_routes"] == ["regulation", "external"]
    cleared = client.patch("/api/v1/me", headers=auth_headers, json={"document_routes": None})
    assert cleared.json()["document_routes"] is None


@pytest.mark.parametrize("bad", [[], ["Không Hợp Lệ"], ["a"] * 0 + ["x"]])
def test_route_choice_is_validated(client, auth_headers, bad):
    assert client.patch("/api/v1/me", headers=auth_headers, json={"document_routes": bad}).status_code == 422


def test_selectable_routes_lists_documents_and_web(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", True)
    routes = client.get("/api/v1/documents/catalog/routes", headers=auth_headers).json()
    kinds = {r["id"]: r["kind"] for r in routes}
    assert kinds.get("regulation") == "document" and kinds.get("external") == "web"
    assert "smalltalk" not in kinds and "offtopic" not in kinds
    assert client.get("/api/v1/documents/catalog/routes").status_code == 401


def test_public_catalog_summary_counts_enabled_documents(client):
    summary = client.get("/api/v1/documents/catalog/summary")  # không cần đăng nhập
    assert summary.status_code == 200
    body = summary.json()
    assert body["count"] == len(body["documents"]) >= 1
    assert any(doc["id"] == "regulation" for doc in body["documents"])
    assert set(body["documents"][0]) == {"id", "label", "decision_no", "description", "official_url"}
