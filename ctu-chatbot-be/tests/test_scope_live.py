"""Kiểm thử guardrail phạm vi + tìm web với dịch vụ THẬT (Gemini + embedding + DuckDuckGo).

Chạy: `pytest -m live tests/test_scope_live.py -v`. Mỗi câu phân loại tốn tối đa một lần gọi LLM (đã giãn cách).
Bộ câu gán nhãn tay: câu thuộc quy chế KHÔNG được bị đẩy sang tìm web (sai kiểu này nguy hiểm nhất vì bot sẽ bỏ
quy chế để tin web), câu ngoài quy chế phải ra `external`, câu lạc đề phải bị từ chối không tìm web.
"""

import uuid

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import settings
from app.services.chat import scope
from app.services.chat.graph import build_chat_graph
from app.services.llm.gemini import GeminiClient
from app.services.rag.embeddings import EmbeddingError, GeminiEmbedder
from app.services.rag.store import Retriever, VectorStore, default_source_path, ensure_index
from tests.live_gemini import CachedEmbedder, ThrottledLLM
from tests.rag_cases import ARTICLE_CASES, FORMULA_CASES

pytestmark = pytest.mark.live

EXTERNAL = [
    "Học phí một tín chỉ ở CTU năm 2025 là bao nhiêu?",
    "Ký túc xá CTU khu B có bao nhiêu phòng và giá thế nào?",
    "Lịch thi học kỳ này của trường như thế nào?",
    "Ngành Công nghệ thông tin CTU lấy bao nhiêu điểm chuẩn năm nay?",
    "Cách lấy lại mật khẩu email sinh viên CTU?",
    "Thư viện trường mở cửa mấy giờ?",
    "Số điện thoại phòng Đào tạo CTU là gì?",
    "Địa chỉ khoa Công nghệ thông tin ở đâu?",
]
OFFTOPIC = [
    "Viết giúp mình một bài thơ lục bát về mùa thu",
    "Cách nấu phở bò ngon?",
    "Viết hàm Python sắp xếp mảng",
    "Giá vàng hôm nay bao nhiêu?",
]
SMALLTALK = ["hi", "cảm ơn bạn nhé", "bạn là ai vậy?"]
REGULATION_SAMPLE = 12  # lấy mẫu rải đều từ bộ câu hỏi quy chế đã có


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    source = default_source_path()
    if not source.exists():
        pytest.skip(f"thiếu file nguồn {source}")
    try:
        store = VectorStore(CachedEmbedder(GeminiEmbedder.from_settings()), path=tmp_path_factory.mktemp("chroma"))
        ensure_index(store, source)
    except EmbeddingError as exc:
        pytest.skip(f"không tạo được embedding: {exc}")
    return Retriever(store)


@pytest.fixture(scope="module")
def llm():
    if not settings.gemini_api_keys:
        pytest.skip("chưa có GEMINI_API_KEY_* trong .env")
    return ThrottledLLM(GeminiClient.from_settings(), min_interval=4.0)


def route_of(llm, retriever, question: str) -> str:
    hits = retriever.retrieve(question)
    semantic = [h.score for h in hits if not h.explicit]
    return scope.classify(llm, [HumanMessage(content=question)], max(semantic) if semantic else None)


_regulation = [c.question for c in ARTICLE_CASES + FORMULA_CASES]
_regulation = _regulation[:: max(1, len(_regulation) // REGULATION_SAMPLE)][:REGULATION_SAMPLE]


@pytest.mark.parametrize("question", _regulation)
def test_regulation_questions_are_never_sent_to_the_web(llm, retriever, question):
    assert route_of(llm, retriever, question) == scope.REGULATION, question


@pytest.mark.parametrize("question", EXTERNAL)
def test_questions_outside_the_regulation_go_to_web_search(llm, retriever, question):
    assert route_of(llm, retriever, question) == scope.EXTERNAL, question


@pytest.mark.parametrize("question", OFFTOPIC)
def test_unrelated_questions_are_refused_without_searching(llm, retriever, question):
    assert route_of(llm, retriever, question) == scope.OFFTOPIC, question


@pytest.mark.parametrize("question", SMALLTALK)
def test_small_talk_is_detected(llm, retriever, question):
    assert route_of(llm, retriever, question) == scope.SMALLTALK, question


def test_external_question_end_to_end_cites_web_sources(llm, retriever, monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", True)  # conftest tắt mặc định cho test offline
    graph = build_chat_graph(llm, InMemorySaver(), retriever)
    question = "Học phí một tín chỉ của Trường Đại học Cần Thơ hiện nay là bao nhiêu?"
    result = graph.invoke({"messages": [HumanMessage(content=question)]}, {"configurable": {"thread_id": str(uuid.uuid4())}})
    reply = result["messages"][-1]
    extra = reply.additional_kwargs
    assert extra["route"] == scope.EXTERNAL
    assert [t["name"] for t in extra["tools"]].count("web_search") >= 1, "bot phải gọi web_search"
    assert extra["sources"] and all(s["url"].startswith("http") for s in extra["sources"])
    assert "Điều" not in str(reply.content) or "web" in str(reply.content).lower()  # không lôi quy chế vào câu hỏi học phí
