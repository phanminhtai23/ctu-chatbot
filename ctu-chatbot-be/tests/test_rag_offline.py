"""RAG kiểm thử không cần mạng: chunker, ChromaDB (embedding giả) và việc đồ thị đưa ngữ cảnh cho LLM."""

import hashlib
import re
import uuid

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.services.chat.graph import SYSTEM_PROMPT, build_chat_graph, build_system_prompt
from app.services.rag.chunker import split_into_articles
from app.services.rag.store import Retriever, VectorStore, default_source_path, ensure_index
from tests.fakes import FakeLLM
from tests.rag_cases import ARTICLE_CASES, FORMULA_CASES

SOURCE = default_source_path()
pytestmark = pytest.mark.skipif(not SOURCE.exists(), reason=f"thiếu file nguồn {SOURCE}")


class HashEmbedder:
    """Embedding giả: túi từ băm vào 256 chiều. Đủ để kiểm tra cơ chế lưu/truy xuất, không đánh giá chất lượng."""

    DIM = 256

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.DIM
        for word in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


@pytest.fixture(scope="module")
def chunks():
    return split_into_articles(SOURCE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def store(chunks):
    s = VectorStore(HashEmbedder())
    s.index(chunks)
    return s


# ---- chunker ----


def test_each_article_is_one_chunk_36_in_total(chunks):
    assert [c.article for c in chunks] == list(range(1, 37))
    assert len({c.id for c in chunks}) == 36


def test_chunks_carry_chapter_and_heading(chunks):
    by_article = {c.article: c for c in chunks}
    assert by_article[1].chapter.startswith("Chương I.")
    assert by_article[14].chapter.startswith("Chương II.")
    assert by_article[24].chapter.startswith("Chương III.")
    assert by_article[32].chapter.startswith("Chương IV.")
    assert by_article[14].title == "Số tín chỉ đăng ký trong một học kỳ"
    assert "Điều 14. Số tín chỉ đăng ký trong một học kỳ" in by_article[14].text


def test_chunks_do_not_leak_into_each_other(chunks):
    for chunk in chunks:
        other_headings = re.findall(r"^### Điều (\d+)\.", chunk.text, flags=re.M)
        assert other_headings == [], f"Điều {chunk.article} chứa tiêu đề Điều khác: {other_headings}"
        assert "## Chương" not in chunk.text.replace(chunk.chapter, "")


def test_tables_and_formula_stay_inside_their_article(chunks):
    by_article = {c.article: c for c in chunks}
    assert "| 9,0 – 10,0 | A | 4,0 |" in by_article[22].text  # bảng quy đổi điểm
    assert "\\sum" in by_article[24].text and "ĐTBCHK" in by_article[24].text  # công thức
    assert "Từ 106 đến 141" in by_article[30].text  # bảng xếp trình độ năm
    assert "07:00 – 07:50" in by_article[19].text  # thời khóa biểu
    assert "| 4 năm | 8 năm |" in by_article[5].text


def test_every_article_fits_in_one_embedding_call(chunks):
    # gemini-embedding-2 nhận tối đa 8192 token; tiếng Việt ~ 2-3 ký tự/token là ước lượng rất thận trọng.
    assert max(len(c.text) for c in chunks) < 8192 * 2


def test_editorial_note_is_not_indexed(chunks):
    assert all("không ghi" not in c.text.lower() or c.article != 19 or "*(Các ô" not in c.text for c in chunks)
    assert "*(Các ô" not in "\n".join(c.text for c in chunks)


# ---- ChromaDB ----


def test_index_and_fetch_article_by_number(store):
    assert store.count() == 36
    hit = store.get_article(24)
    assert hit.article == 24 and "ĐTBCHK" in hit.text
    assert store.get_article(99) is None


def test_search_returns_scored_hits(store):
    hits = store.search("Điều kiện nhận học bổng khuyến khích học tập", 3)
    assert len(hits) == 3
    assert hits[0].score >= hits[1].score >= hits[2].score
    assert 9 in [h.article for h in hits]


def test_reindexing_replaces_instead_of_duplicating(chunks):
    s = VectorStore(HashEmbedder())
    s.index(chunks)
    s.index(chunks[:5])
    assert s.count() == 5


def test_persistent_store_survives_reopen(tmp_path, chunks):
    path = tmp_path / "chroma"
    VectorStore(HashEmbedder(), path=path, collection="test-col").index(chunks, source_hash="abc")
    reopened = VectorStore(HashEmbedder(), path=path, collection="test-col")
    assert reopened.count() == 36
    assert reopened.source_hash == "abc"


def test_ensure_index_skips_work_when_source_unchanged(tmp_path):
    class CountingEmbedder(HashEmbedder):
        calls = 0

        def embed_documents(self, texts):
            CountingEmbedder.calls += 1
            return super().embed_documents(texts)

    s = VectorStore(CountingEmbedder(), path=tmp_path / "c", collection="test-col")
    assert ensure_index(s, SOURCE) == 36
    assert ensure_index(s, SOURCE) == 36
    assert CountingEmbedder.calls == 1  # lần hai không gọi embedding nữa


def test_ensure_index_rebuilds_when_source_changes(tmp_path):
    s = VectorStore(HashEmbedder(), path=tmp_path / "c", collection="test-col")
    ensure_index(s, SOURCE)
    edited = tmp_path / "edited.md"
    edited.write_text(SOURCE.read_text(encoding="utf-8").split("### Điều 3.")[0], encoding="utf-8")
    assert ensure_index(s, edited) == 2


# ---- Retriever ----


def test_explicit_article_mention_is_always_retrieved(store):
    hits = Retriever(store, top_k=3).retrieve("Điều 30 nói gì vậy?")
    assert hits[0].article == 30 and hits[0].explicit
    assert len(hits) == 4  # 1 điều nêu thẳng + top_k điều giống nhất


def test_retriever_does_not_duplicate_articles(store):
    hits = Retriever(store, top_k=5).retrieve("Điều 24 và Điều 24 tính ĐTBCHK thế nào")
    articles = [h.article for h in hits]
    assert len(articles) == len(set(articles))


def test_unknown_article_number_is_ignored(store):
    hits = Retriever(store, top_k=3).retrieve("Điều 99 quy định gì?")
    assert len(hits) == 3 and not any(h.explicit for h in hits)


# ---- đồ thị chat + RAG ----


def _ask(graph, text, thread=None):
    config = {"configurable": {"thread_id": thread or str(uuid.uuid4())}}
    return graph.invoke({"messages": [HumanMessage(content=text)]}, config)


def test_graph_puts_retrieved_articles_into_system_prompt(store):
    llm = FakeLLM()
    graph = build_chat_graph(llm, InMemorySaver(), Retriever(store, top_k=2))
    result = _ask(graph, "Theo Điều 14, tối đa bao nhiêu tín chỉ?")

    system = llm.calls[0][0]
    assert isinstance(system, SystemMessage)
    assert "NGỮ CẢNH" in system.content
    assert "Sinh viên được đăng ký tối đa 20 TC/HK" in system.content
    sources = result["messages"][-1].additional_kwargs["sources"]
    assert sources[0]["article"] == 14


def test_follow_up_question_is_searched_together_with_previous_question(store):
    llm = FakeLLM()
    graph = build_chat_graph(llm, InMemorySaver(), Retriever(store, top_k=1))
    thread = str(uuid.uuid4())
    _ask(graph, "Điều 24 nói về điều gì?", thread)
    _ask(graph, "Còn xếp loại thì sao?", thread)  # câu thứ hai không nhắc Điều 24

    second_system = llm.calls[1][0].content
    assert "Điều 24." in second_system


def test_graph_works_without_retriever_and_says_no_context():
    llm = FakeLLM()
    graph = build_chat_graph(llm, InMemorySaver())
    result = _ask(graph, "Xin chào")
    assert "Không tìm thấy Điều nào liên quan" in llm.calls[0][0].content
    assert result["messages"][-1].additional_kwargs["sources"] == []


def test_retrieval_failure_does_not_break_the_chat():
    class BrokenRetriever:
        def retrieve(self, question):
            raise RuntimeError("embedding 429")

    llm = FakeLLM()
    graph = build_chat_graph(llm, InMemorySaver(), BrokenRetriever())
    result = _ask(graph, "Xin chào")
    assert result["messages"][-1].content.startswith("trả lời #1")


# ---- prompt ----


def test_system_prompt_asks_for_cute_easy_answers_and_plain_formulas():
    prompt = build_system_prompt([])
    for needle in ("dễ thương", "dễ hiểu", "emoji", "KHÔNG dùng LaTeX", "tính từng bước", "KHÔNG bịa"):
        assert needle in prompt
    assert "Always reply in English" in prompt  # luật ngôn ngữ cũ vẫn còn
    assert "\x0c" not in SYSTEM_PROMPT  # \f trong chuỗi thường là lỗi escape (\frac)


# ---- bộ câu hỏi ----


def test_question_bank_covers_every_article():
    covered = {case.article for case in ARTICLE_CASES}
    assert covered == set(range(1, 37)), f"thiếu Điều: {sorted(set(range(1, 37)) - covered)}"


def test_question_bank_has_many_formula_cases():
    assert len(FORMULA_CASES) >= 20
    assert {case.article for case in FORMULA_CASES} >= {5, 8, 18, 19, 22, 24, 25, 28, 30, 34}
