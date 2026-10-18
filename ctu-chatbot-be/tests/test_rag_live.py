"""Kiểm thử RAG đầu-cuối với dịch vụ THẬT: embedding Gemini + ChromaDB + LLM Gemini (`LLM_MODEL`).

Chạy: `pytest -m live -v` (mất ~10 phút vì giãn cách 7s/lần gọi để không vượt quota free).
Tự bỏ qua nếu thiếu key Gemini; tự dừng nếu chạm trần số lần gọi hoặc bị 429 (xem tests/live_gemini.py).
Mỗi Điều (1-36) có ít nhất một câu hỏi; các chỗ có công thức/bảng/phép tính được hỏi bằng nhiều con số cụ thể.
Câu trả lời được kiểm tra đúng nội dung (regex trên số liệu), đúng Điều được truy xuất, và đúng giọng (dễ thương, không LaTeX).
"""

import re
import uuid

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import settings
from app.services.chat.graph import build_chat_graph
from app.services.llm.gemini import GeminiClient
from app.services.rag.embeddings import EmbeddingError, GeminiEmbedder
from app.services.rag.store import Retriever, VectorStore, default_source_path, ensure_index
from tests.live_gemini import CachedEmbedder, ThrottledLLM
from tests.rag_cases import ARTICLE_CASES, FEASIBILITY_CASES, FORMULA_CASES, OFF_TOPIC, UNKNOWN_CASES, Case
from tests.rag_cases_scholarship import SCHOLARSHIP_CASES

pytestmark = pytest.mark.live

ALL_CASES = ARTICLE_CASES + FORMULA_CASES + UNKNOWN_CASES + FEASIBILITY_CASES + SCHOLARSHIP_CASES
EMOJI = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf\u2b50\u2728]")
LATEX = re.compile(r"\$\$|\\frac|\\sum|\\times|\\cdot|\\text|\\begin|\\\(|\\\[")
_answers: dict[str, tuple[str, list[int]]] = {}


@pytest.fixture(scope="session")
def retriever(tmp_path_factory):
    source = default_source_path()
    if not source.exists():
        pytest.skip(f"thiếu file nguồn {source}")
    try:
        embedder = CachedEmbedder(GeminiEmbedder.from_settings())
        store = VectorStore(embedder, path=tmp_path_factory.mktemp("chroma"))  # PersistentClient thật, không cần server
        ensure_index(store, source)
    except EmbeddingError as exc:
        pytest.skip(f"không tạo được embedding: {exc}")
    assert store.count() == 36
    return Retriever(store)


@pytest.fixture(scope="session")
def graph(retriever):
    if not settings.gemini_api_keys:
        pytest.skip("chưa có GEMINI_API_KEY_* trong .env")
    llm = ThrottledLLM(GeminiClient.from_settings())  # đúng lớp client dùng ở production
    return build_chat_graph(llm, InMemorySaver(), retriever)


def ask(graph, question: str) -> tuple[str, list[int]]:
    if question not in _answers:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        result = graph.invoke({"messages": [HumanMessage(content=question)]}, config)
        reply = result["messages"][-1]
        sources = [s["article"] for s in reply.additional_kwargs.get("retrieved", [])]
        _answers[question] = (str(reply.content), sources)
    return _answers[question]


def normalize(text: str) -> str:
    text = text.lower().replace("\u00a0", " ")
    return re.sub(r"[*_`]", "", text)


def assert_friendly(answer: str) -> None:
    assert not LATEX.search(answer), f"còn ký hiệu LaTeX trong câu trả lời:\n{answer}"
    assert re.search(r"\bbạn\b|\bmình\b", answer.lower()), f"giọng chưa thân thiện (không xưng mình/bạn):\n{answer}"
    assert len(answer) < 2500, "trả lời quá dài, khó đọc"


def assert_case(case: Case, answer: str) -> None:
    text = normalize(answer)
    if case.lead:
        assert re.search(case.lead, text[:260], flags=re.IGNORECASE), (
            f"[{case.id}] câu trả lời chưa mở đầu bằng Có/Không rõ ràng ({case.lead!r})\n--- trả lời:\n{answer}"
        )
    for group in case.must:
        assert any(re.search(p, text, flags=re.IGNORECASE) for p in group), (
            f"[{case.id}] thiếu một trong {group}\n--- câu hỏi: {case.question}\n--- trả lời:\n{answer}"
        )
    for pattern in case.forbid:
        assert not re.search(pattern, text, flags=re.IGNORECASE), (
            f"[{case.id}] có nội dung không được phép {pattern!r}\n--- trả lời:\n{answer}"
        )


# ---- 1. Truy xuất: Điều chứa đáp án phải nằm trong các Điều được lấy ra ----


@pytest.mark.parametrize("case", [c for c in ALL_CASES if c.article > 0], ids=lambda c: c.id)
def test_retrieval_returns_the_right_article(retriever, case):
    got = [h.article for h in retriever.retrieve(case.question)]
    assert case.article in got, f"[{case.id}] cần Điều {case.article} nhưng chỉ lấy được {got}\n{case.question}"


# ---- 2. Trả lời đúng ở TOÀN BỘ các Điều ----


@pytest.mark.parametrize("case", ARTICLE_CASES, ids=lambda c: c.id)
def test_answer_is_correct_for_every_article(graph, case):
    answer, sources = ask(graph, case.question)
    assert case.article in sources, f"[{case.id}] Điều {case.article} không nằm trong ngữ cảnh: {sources}"
    assert_case(case, answer)
    assert_friendly(answer)


# ---- 3. Công thức, bảng, phép tính ----


@pytest.mark.parametrize("case", FORMULA_CASES, ids=lambda c: c.id)
def test_formula_and_calculation_answers(graph, case):
    answer, sources = ask(graph, case.question)
    assert case.article in sources, f"[{case.id}] Điều {case.article} không nằm trong ngữ cảnh: {sources}"
    assert_case(case, answer)
    assert_friendly(answer)


def test_formula_answer_shows_the_steps(graph):
    answer, _ = ask(graph, FORMULA_CASES[0].question)
    # Có phép nhân tín chỉ × điểm và có tổng tín chỉ: sinh viên nhìn vào là hiểu cách ra kết quả.
    assert re.search(r"3\s*[x×*]\s*4", answer.lower()), f"chưa thể hiện phép nhân từng môn:\n{answer}"
    assert re.search(r"\b9\b", answer), f"chưa thể hiện tổng 9 tín chỉ:\n{answer}"


# ---- 3b. Câu hỏi "có đạt được mục tiêu không": trả lời Có/Không ngay và nêu mức tối đa ----


@pytest.mark.parametrize("case", FEASIBILITY_CASES, ids=lambda c: c.id)
def test_feasibility_questions_answer_yes_or_no_first(graph, case):
    answer, retrieved = ask(graph, case.question)
    assert 34 in retrieved, f"[{case.id}] Điều 34 không nằm trong ngữ cảnh: {retrieved}"
    assert_case(case, answer)
    assert_friendly(answer)


def test_feasibility_recomputes_after_user_gives_the_counted_credits(graph):
    """Lượt 1: chỉ có tổng TC -> trả lời theo giả định + hỏi số TC không tính điểm.
    Lượt 2: người dùng cho số TC học phần điều kiện -> bot phải TÍNH LẠI bằng C và T đã loại học phần điều kiện."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    def say(text: str) -> str:
        return str(graph.invoke({"messages": [HumanMessage(content=text)]}, config)["messages"][-1].content)

    first = say("Chương trình 151 tín chỉ, mình đã học 100 tín chỉ, ĐTBCTL 3,5. Mình có thể đạt xuất sắc không?")
    first_text = normalize(first)
    # 4 - 0,5 x 100/151 = 3,67 >= 3,60 -> CÓ THỂ; và phải hỏi lại số TC học phần điều kiện để tính chính xác
    assert re.search(r"\bcó\b", first_text[:260]), first
    assert re.search(r"3[,.]6\d", first_text), first
    assert re.search(r"điều kiện", first_text), f"chưa hỏi/nhắc tới học phần điều kiện:\n{first}"
    assert re.search(r"bao nhiêu", first_text), f"chưa hỏi số TC không tính điểm:\n{first}"

    second = say(
        "Trong 100 TC đã học có 30 TC là GDTC, GDQP&AN và các học phần điều kiện; "
        "tổng học phần điều kiện của cả chương trình cũng là 30 TC. Tính lại giúp mình nhé."
    )
    text = normalize(second)
    # C = 70, T = 121, còn lại 51 TC: tối đa (3,5x70 + 4x51)/121 = 3,71; cần trung bình 3,74 ở phần còn lại
    assert re.search(r"\b121\b", text), f"chưa dùng T = 151 - 30 = 121:\n{second}"
    assert re.search(r"3[,.]7[1-4]", text), f"chưa ra kết quả tính lại (3,71 / 3,74):\n{second}"
    assert_friendly(second)


# ---- 3c. Học bổng: xếp MỨC (ĐTBCHK và ĐRL) trước rồi mới so ĐTBCHK, rồi ĐRL ----


@pytest.mark.parametrize("case", SCHOLARSHIP_CASES, ids=lambda c: c.id)
def test_scholarship_ranking_follows_level_then_gpa_then_conduct(graph, case):
    answer, retrieved = ask(graph, case.question)
    assert 9 in retrieved, f"[{case.id}] Điều 9 không nằm trong ngữ cảnh: {retrieved}"
    assert_case(case, answer)
    assert_friendly(answer)


# ---- 4. Không bịa khi văn bản không có ----


@pytest.mark.parametrize("case", UNKNOWN_CASES, ids=lambda c: c.id)
def test_does_not_invent_what_the_regulation_does_not_say(graph, case):
    answer, _ = ask(graph, case.question)
    assert_case(case, answer)
    assert_friendly(answer)


# ---- 5. Giọng điệu, ngôn ngữ, phạm vi ----


def test_most_answers_have_a_friendly_emoji(graph):
    answers = [ask(graph, case.question)[0] for case in ARTICLE_CASES[:12]]
    with_emoji = sum(1 for a in answers if EMOJI.search(a))
    assert with_emoji >= len(answers) * 0.6, f"chỉ {with_emoji}/{len(answers)} câu trả lời có emoji"


def test_off_topic_request_is_declined_politely(graph):
    answer, _ = ask(graph, OFF_TOPIC)
    text = normalize(answer)
    assert re.search(r"học vụ|quy định|việc học|học tập|quy chế", text), f"chưa nói rõ phạm vi hỗ trợ:\n{answer}"
    assert len(answer) < 700, f"lẽ ra chỉ từ chối ngắn gọn, không làm theo yêu cầu:\n{answer}"
    short_lines = [line for line in answer.splitlines() if 0 < len(line.strip()) < 60]
    assert len(short_lines) < 5, f"có vẻ vẫn làm thơ:\n{answer}"


def test_replies_in_english_when_asked_in_english(graph):
    answer, sources = ask(graph, "How many credits can I register for in one semester?")
    text = normalize(answer)
    assert 14 in sources
    assert "20" in text and "credit" in text, answer
    # Chú thích thuật ngữ gốc như "credits (tín chỉ)" là chấp nhận được; câu văn phải là tiếng Anh.
    assert not re.search(r"\bbạn\b|\bmình\b", text), f"đáng lẽ phải trả lời tiếng Anh:\n{answer}"
    assert re.search(r"\b(the|you|your|is|are|can)\b", text), f"không giống câu tiếng Anh:\n{answer}"


def test_follow_up_question_uses_previous_turn(retriever, graph):
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    graph.invoke({"messages": [HumanMessage(content="Mình muốn hỏi về điểm trung bình chung học kỳ (ĐTBCHK).")]}, config)
    result = graph.invoke({"messages": [HumanMessage(content="Vậy bao nhiêu điểm thì xếp loại xuất sắc?")]}, config)
    reply = result["messages"][-1]
    assert re.search(r"3[,.]60?", normalize(str(reply.content))), str(reply.content)
    assert 24 in [s["article"] for s in reply.additional_kwargs["retrieved"]]
