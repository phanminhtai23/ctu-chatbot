import hashlib
import re

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.api.v1.admin_knowledge import get_knowledge_store_optional
from app.core.config import settings
from app.main import app
from app.services.chat import graph as graph_module
from app.services.chat import scope
from app.services.chat.graph import build_chat_graph, build_system_prompt
from app.services.rag.embeddings import CachedQueryEmbedder, EmbeddingError
from app.services.rag.knowledge import KbHit, KnowledgeStore
from app.services.rag.store import Hit, Retriever, VectorStore

URL = "/api/v1/admin/knowledge"


class HashEmbedder:
    """Túi từ băm vào 256 chiều: câu chung nhiều từ thì giống nhau, đủ để thử cơ chế tra cứu."""

    DIM = 256

    def __init__(self):
        self.calls = {"docs": 0, "query": 0}
        self.fail = False

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.DIM
        for word in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        if self.fail:
            raise EmbeddingError("hết hạn mức")
        self.calls["docs"] += len(texts)
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        if self.fail:
            raise EmbeddingError("hết hạn mức")
        self.calls["query"] += 1
        return self._vec(text)


@pytest.fixture()
def embedder():
    return HashEmbedder()


@pytest.fixture()
def store(client, embedder):
    kb = KnowledgeStore(embedder)  # bộ nhớ trong
    app.dependency_overrides[get_knowledge_store_optional] = lambda: kb
    return kb


def _add(client, headers, question="Ký túc xá khu A có bao nhiêu phòng?", answer="Khu A có 400 phòng."):
    return client.post(URL, headers=headers, json={"question": question, "answer": answer})


# ---- quyền ----


def test_admin_only(client, store, auth_headers):
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers=auth_headers).status_code == 403
    assert client.post(URL, headers=auth_headers, json={"question": "a", "answer": "b"}).status_code == 403
    assert client.post(f"{URL}/embed", headers=auth_headers).status_code == 403
    assert client.post(f"{URL}/test", headers=auth_headers, json={"query": "x"}).status_code == 403


# ---- nhập / sửa / xoá ----


def test_create_list_and_reject_duplicates_and_bad_input(client, store, admin_headers):
    res = _add(client, admin_headers)
    assert res.status_code == 201
    entry = res.json()
    assert entry["status"] == "pending" and entry["embedded_at"] is None

    # trùng câu hỏi (không phân biệt hoa thường, khoảng trắng, dấu hỏi cuối)
    dup = _add(client, admin_headers, question="  ký túc xá khu a có bao nhiêu   phòng ")
    assert dup.status_code == 409 and dup.json()["detail"] == "DUPLICATE_QUESTION"

    assert _add(client, admin_headers, question="   ").status_code == 422
    assert _add(client, admin_headers, answer="").status_code == 422
    assert _add(client, admin_headers, question="x" * 501).status_code == 422
    assert _add(client, admin_headers, question="y", answer="z" * 4001).status_code == 422

    body = client.get(URL, headers=admin_headers).json()
    assert body["total"] == 1 and body["items"][0]["id"] == entry["id"]
    assert body["stats"] == {"total": 1, "embedded": 0, "pending": 1, "vector_count": 0}


def test_search_and_state_filter(client, store, admin_headers):
    _add(client, admin_headers, "Học phí một tín chỉ?", "500 nghìn")
    _add(client, admin_headers, "Giờ mở cửa thư viện?", "7h đến 21h")
    assert client.get(URL, headers=admin_headers, params={"q": "thư viện"}).json()["total"] == 1
    assert client.get(URL, headers=admin_headers, params={"q": "21h"}).json()["total"] == 1  # tìm cả trong câu trả lời
    assert client.get(URL, headers=admin_headers, params={"state": "embedded"}).json()["total"] == 0
    assert client.get(URL, headers=admin_headers, params={"state": "pending"}).json()["total"] == 2


def test_embedding_moves_entries_into_the_vector_db(client, store, embedder, admin_headers):
    _add(client, admin_headers, "Học phí một tín chỉ?", "500 nghìn")
    _add(client, admin_headers, "Giờ mở cửa thư viện?", "7h đến 21h")

    res = client.post(f"{URL}/embed", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["embedded"] == 2
    assert res.json()["stats"] == {"total": 2, "embedded": 2, "pending": 0, "vector_count": 2}
    assert store.count() == 2
    assert all(i["status"] == "embedded" and i["embedded_at"] for i in client.get(URL, headers=admin_headers).json()["items"])

    again = client.post(f"{URL}/embed", headers=admin_headers).json()  # không còn gì chờ: không tốn lượt embedding
    assert again["embedded"] == 0 and embedder.calls["docs"] == 2


def test_editing_makes_an_entry_pending_again_and_reembedding_updates_the_answer(client, store, admin_headers):
    entry = _add(client, admin_headers, "Học phí một tín chỉ?", "500 nghìn").json()
    client.post(f"{URL}/embed", headers=admin_headers)

    patched = client.patch(f"{URL}/{entry['id']}", headers=admin_headers, json={"answer": "550 nghìn"})
    assert patched.status_code == 200 and patched.json()["status"] == "pending"
    assert store.search("Học phí một tín chỉ?", 1)[0].answer == "500 nghìn"  # chưa embedding lại thì vector DB vẫn giữ bản cũ

    assert client.post(f"{URL}/{entry['id']}/embed", headers=admin_headers).json()["embedded"] == 1
    assert store.search("Học phí một tín chỉ?", 1)[0].answer == "550 nghìn"
    assert client.get(URL, headers=admin_headers).json()["items"][0]["status"] == "embedded"


def test_patch_validation_and_duplicates(client, store, admin_headers):
    a = _add(client, admin_headers, "Câu A", "đáp A").json()
    b = _add(client, admin_headers, "Câu B", "đáp B").json()
    assert client.patch(f"{URL}/{b['id']}", headers=admin_headers, json={"question": "câu a"}).status_code == 409
    assert client.patch(f"{URL}/{a['id']}", headers=admin_headers, json={}).status_code == 422
    assert client.patch(f"{URL}/{a['id']}", headers=admin_headers, json={"answer": "  "}).status_code == 422
    assert client.patch("/api/v1/admin/knowledge/00000000-0000-0000-0000-000000000000", headers=admin_headers, json={"answer": "x"}).status_code == 404


def test_delete_removes_the_vector_too(client, store, admin_headers):
    entry = _add(client, admin_headers).json()
    client.post(f"{URL}/embed", headers=admin_headers)
    assert store.count() == 1
    assert client.delete(f"{URL}/{entry['id']}", headers=admin_headers).status_code == 204
    assert store.count() == 0 and client.get(URL, headers=admin_headers).json()["total"] == 0
    assert client.delete(f"{URL}/{entry['id']}", headers=admin_headers).status_code == 404


def test_force_reembeds_everything_after_the_vector_db_was_lost(client, store, embedder, admin_headers):
    _add(client, admin_headers, "Câu A", "đáp A")
    _add(client, admin_headers, "Câu B", "đáp B")
    client.post(f"{URL}/embed", headers=admin_headers)
    store.clear()  # giả lập mất thư mục ChromaDB
    stats = client.get(URL, headers=admin_headers).json()["stats"]
    assert stats["embedded"] == 2 and stats["vector_count"] == 0  # lệch nhau: giao diện cảnh báo

    res = client.post(f"{URL}/embed", headers=admin_headers, params={"force": "true"}).json()
    assert res["embedded"] == 2 and res["stats"]["vector_count"] == 2


def test_embedding_failure_returns_503_and_keeps_entries_pending(client, store, embedder, admin_headers):
    _add(client, admin_headers)
    embedder.fail = True
    res = client.post(f"{URL}/embed", headers=admin_headers)
    assert res.status_code == 503 and res.json()["detail"] == "EMBEDDING_UNAVAILABLE"
    assert client.get(URL, headers=admin_headers).json()["items"][0]["status"] == "pending"
    embedder.fail = False
    assert client.post(f"{URL}/embed", headers=admin_headers).json()["embedded"] == 1


def test_without_a_vector_store_listing_works_but_embedding_is_unavailable(client, admin_headers):
    app.dependency_overrides[get_knowledge_store_optional] = lambda: None
    _add(client, admin_headers)
    body = client.get(URL, headers=admin_headers).json()
    assert body["total"] == 1 and body["stats"]["vector_count"] is None
    res = client.post(f"{URL}/embed", headers=admin_headers)
    assert res.status_code == 503 and res.json()["detail"] == "KNOWLEDGE_UNAVAILABLE"


def test_try_query_shows_scores_and_which_hits_would_be_used(client, store, admin_headers):
    _add(client, admin_headers, "Ký túc xá khu A có bao nhiêu phòng", "400 phòng")
    _add(client, admin_headers, "Giờ mở cửa thư viện", "7h đến 21h")
    client.post(f"{URL}/embed", headers=admin_headers)
    res = client.post(f"{URL}/test", headers=admin_headers, json={"query": "Ký túc xá khu A có bao nhiêu phòng"}).json()
    assert res["hits"][0]["question"].startswith("Ký túc xá khu A") and res["hits"][0]["score"] > 0.99
    assert res["hits"][0]["used"] is True
    assert res["hits"][-1]["used"] is False and res["hits"][-1]["score"] < res["min_score"]
    assert client.post(f"{URL}/test", headers=admin_headers, json={"query": "  "}).status_code == 422


# ---- kho vector và bộ tra cứu ----


def test_store_search_orders_by_similarity_and_applies_min_score(embedder):
    kb = KnowledgeStore(embedder)
    kb.upsert([("1", "Học phí một tín chỉ bao nhiêu", "500k"), ("2", "Giờ mở cửa thư viện", "7h-21h")])
    hits = kb.search("học phí một tín chỉ", 5)
    assert [h.id for h in hits] == ["1", "2"] and hits[0].answer == "500k"
    assert [h.id for h in kb.search("học phí một tín chỉ", 5, min_score=0.5)] == ["1"]
    kb.delete(["1"])
    assert kb.ids() == {"2"}


def test_retriever_exposes_knowledge_hits_only_above_the_threshold(embedder, monkeypatch):
    monkeypatch.setattr(settings, "kb_min_score", 0.6)
    kb = KnowledgeStore(embedder)
    kb.upsert([("1", "Học phí một tín chỉ bao nhiêu", "500k")])
    retriever = Retriever(VectorStore(embedder), knowledge=kb)
    assert [h.id for h in retriever.retrieve_knowledge("học phí một tín chỉ bao nhiêu")] == ["1"]
    assert retriever.retrieve_knowledge("thời tiết hôm nay thế nào") == []
    assert Retriever(VectorStore(embedder)).retrieve_knowledge("học phí") == []  # chưa gắn kho kiến thức


def test_cached_query_embedder_embeds_each_question_once():
    inner = HashEmbedder()
    cached = CachedQueryEmbedder(inner, size=2)
    cached.embed_query("a")
    cached.embed_query("a")
    cached.embed_query("b")
    cached.embed_query("c")  # đẩy "a" ra khỏi cache (size=2)
    cached.embed_query("a")
    assert inner.calls["query"] == 4


# ---- đưa vào chatbot ----

KB_HIT = KbHit("e1", "Ký túc xá khu A có bao nhiêu phòng?", "Khu A có 400 phòng.", 0.9)
ART = Hit(article=14, title="Cảnh báo học tập", chapter="", text="Điều 14. Cảnh báo học tập ...", score=0.5)


class FakeRetriever:
    def __init__(self, kb_hits, hits=(ART,), kb_error=False):
        self.kb_hits, self.hits, self.kb_error = list(kb_hits), list(hits), kb_error

    def retrieve(self, q):
        return self.hits

    def retrieve_knowledge(self, q):
        if self.kb_error:
            raise RuntimeError("chroma down")
        return self.kb_hits


class RoutedLLM:
    supports_tools = True

    def __init__(self, route=scope.EXTERNAL):
        self.route, self.systems = route, []

    def stream(self, messages, tools=None):
        system = messages[0].content if isinstance(messages[0], SystemMessage) else ""
        if system.startswith("Phân loại"):
            yield AIMessageChunk(content=self.route)
            return
        self.systems.append(system)
        yield AIMessageChunk(content="Khu A có 400 phòng.")


def _chat(llm, retriever, monkeypatch, web=True):
    monkeypatch.setattr(settings, "web_search_enabled", web)
    monkeypatch.setattr(graph_module, "build_gpa_report", lambda *_: "")
    g = build_chat_graph(llm, InMemorySaver(), retriever)
    out = g.invoke({"messages": [HumanMessage(content="Ký túc xá khu A có bao nhiêu phòng?")]}, {"configurable": {"thread_id": "t"}})
    return out["messages"][-1]


def test_matching_knowledge_goes_into_the_prompt_and_skips_the_web(monkeypatch):
    monkeypatch.setattr(settings, "kb_strong_score", 0.72)
    llm = RoutedLLM(route=scope.EXTERNAL)  # nếu phân loại thì sẽ ra "external"; khớp rõ kiến thức bổ sung thì không được phân loại
    reply = _chat(llm, FakeRetriever([KB_HIT]), monkeypatch)
    assert reply.additional_kwargs["route"] == scope.REGULATION
    assert "KIẾN THỨC BỔ SUNG" in llm.systems[0] and "Khu A có 400 phòng." in llm.systems[0]
    assert "[Mục 1] Hỏi: Ký túc xá khu A có bao nhiêu phòng?" in llm.systems[0]
    assert reply.additional_kwargs["knowledge"] == [{"id": "e1", "question": KB_HIT.question, "score": 0.9}]


def test_weak_knowledge_match_is_added_but_does_not_force_the_route(monkeypatch):
    weak = KbHit("e2", "Câu gần giống", "đáp", 0.65)
    llm = RoutedLLM(route=scope.REGULATION)
    reply = _chat(llm, FakeRetriever([weak]), monkeypatch)
    assert reply.additional_kwargs["route"] == scope.REGULATION  # do bộ phân loại chọn
    assert "Câu gần giống" in llm.systems[0]


def test_no_knowledge_means_the_prompt_is_unchanged(monkeypatch):
    llm = RoutedLLM(route=scope.REGULATION)
    reply = _chat(llm, FakeRetriever([]), monkeypatch)
    assert "KIẾN THỨC BỔ SUNG" not in llm.systems[0] and reply.additional_kwargs["knowledge"] == []


def test_knowledge_lookup_failure_does_not_break_the_chat(monkeypatch):
    llm = RoutedLLM(route=scope.REGULATION)
    reply = _chat(llm, FakeRetriever([KB_HIT], kb_error=True), monkeypatch)
    assert reply.content == "Khu A có 400 phòng." and reply.additional_kwargs["knowledge"] == []


def test_non_regulation_routes_do_not_get_the_knowledge(monkeypatch):
    weak = KbHit("e2", "Câu gần giống", "đáp", 0.65)
    llm = RoutedLLM(route=scope.OFFTOPIC)
    reply = _chat(llm, FakeRetriever([weak]), monkeypatch)
    assert reply.additional_kwargs["route"] == scope.OFFTOPIC
    assert "Câu gần giống" not in llm.systems[0] and reply.additional_kwargs["knowledge"] == []


def test_build_system_prompt_lists_every_entry():
    prompt = build_system_prompt([ART], "", [KB_HIT, KbHit("e3", "Câu 3", "Đáp 3", 0.7)])
    assert prompt.index("[Mục 1]") < prompt.index("[Mục 2]") and "Đáp: Đáp 3" in prompt
    assert "KIẾN THỨC BỔ SUNG" not in build_system_prompt([ART])
