"""Phép tính ĐTBCTL / hạng tốt nghiệp / khả năng đạt mục tiêu: số học chính xác, không phụ thuộc LLM."""

import uuid

import pytest
from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.services.chat.gpa_assist import build_gpa_report, looks_like_gpa_question, parse_facts
from app.services.chat.graph import build_chat_graph
from app.services.grades import GpaFacts, analyze, format_report, rank_of


def check(**kwargs):
    result = analyze(GpaFacts(**kwargs))
    assert result is not None
    return result


# ---- hạng ----


@pytest.mark.parametrize(
    "gpa,expected",
    [(4.0, "xuất sắc"), (3.60, "xuất sắc"), (3.599, "xuất sắc"), (3.59, "giỏi"), (3.20, "giỏi"), (3.19, "khá"),
     (2.50, "khá"), (2.49, "trung bình"), (2.00, "trung bình"), (1.99, None), (0.0, None)],
)
def test_rank_boundaries_follow_article_34(gpa, expected):
    assert rank_of(gpa) == expected


# ---- ví dụ của sinh viên: 151 TC, đã học 100 TC, ĐTBCTL 3,2 ----


def test_cannot_reach_excellent_from_3_2_with_100_of_151_credits():
    r = check(total_credits=151, done_credits=100, current_gpa=3.2, target_rank="xuất sắc")
    assert r.remaining == 51
    assert r.points_now == pytest.approx(320)
    assert r.max_gpa == pytest.approx(524 / 151)  # 3,4702...
    assert round(r.max_gpa, 2) == 3.47
    assert r.max_rank == "giỏi"
    assert r.target.achievable is False
    assert r.target.needed_average == pytest.approx((3.6 * 151 - 320) / 51)  # 4,38 > 4
    assert r.target.needed_average > 4.0


def test_exactly_reaching_the_threshold_counts_as_possible():
    # 100 TC x 3,4 = 340; 51 TC toàn A -> 544/151 = 3,6026: đủ 3,60 (trường hợp mà LLM nhỏ từng nói "không thể")
    r = check(total_credits=151, done_credits=100, current_gpa=3.4, target_rank="xuất sắc")
    assert r.max_gpa == pytest.approx(544 / 151)
    assert r.target.achievable is True
    assert r.target.needed_average == pytest.approx((3.6 * 151 - 340) / 51)
    assert 3.99 < r.target.needed_average <= 4.0  # gần như phải toàn A


def test_credits_without_grade_points_change_the_answer():
    # 100 TC đã học gồm 30 TC điều kiện; tổng TC điều kiện của chương trình cũng 30 -> C = 70, T = 121
    r = check(total_credits=151, done_credits=100, current_gpa=3.5, target_rank="xuất sắc",
              excluded_done=30, excluded_total=30)
    assert (r.counted_done, r.counted_total, r.remaining) == (70, 121, 51)
    assert r.max_gpa == pytest.approx((70 * 3.5 + 51 * 4) / 121)  # 3,711
    assert r.target.needed_average == pytest.approx((3.6 * 121 - 70 * 3.5) / 51)  # 3,737
    assert r.target.achievable is True


def test_remaining_credits_unchanged_when_excluded_credits_are_all_done():
    r = check(total_credits=151, done_credits=100, current_gpa=3.0, excluded_done=10, excluded_total=10)
    assert r.remaining == 51  # (151-10) - (100-10)


def test_excluded_credits_not_yet_studied_increase_the_remaining_count_correctly():
    # tổng điều kiện 20 nhưng mới học 8 -> phần còn lại tính điểm = (151-20) - (100-8) = 39
    r = check(total_credits=151, done_credits=100, current_gpa=3.0, excluded_done=8, excluded_total=20)
    assert (r.counted_done, r.counted_total, r.remaining) == (92, 131, 39)


def test_graduation_floor_of_2_00_is_the_lowest_plan():
    r = check(total_credits=120, done_credits=100, current_gpa=1.5, target_rank="trung bình")
    assert r.target.threshold == 2.0
    assert r.max_gpa == pytest.approx((150 + 80) / 120)  # 1,92 < 2,00
    assert r.target.achievable is False


def test_all_credits_done_means_final_gpa_is_current():
    r = check(total_credits=120, done_credits=120, current_gpa=3.61, target_rank="xuất sắc")
    assert r.remaining == 0
    assert r.max_gpa == pytest.approx(3.61)
    assert r.target.achievable is True and r.target.needed_average is None


def test_numeric_target_is_supported():
    r = check(total_credits=100, done_credits=50, current_gpa=3.0, target_gpa=3.5)
    assert r.target.needed_average == pytest.approx((3.5 * 100 - 150) / 50)  # 4,0
    assert r.target.achievable is True  # đúng bằng 4,0: phải toàn A


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(total_credits=100, done_credits=120, current_gpa=3.0),  # học nhiều hơn tổng
        dict(total_credits=100, done_credits=50, current_gpa=4.5),  # điểm ngoài thang 4
        dict(total_credits=100, done_credits=50, current_gpa=-1),
        dict(total_credits=100, done_credits=50, current_gpa=3.0, excluded_done=60, excluded_total=10),
        dict(total_credits=0, done_credits=0, current_gpa=3.0),
    ],
)
def test_impossible_inputs_are_rejected(kwargs):
    assert analyze(GpaFacts(**kwargs)) is None


def test_report_has_two_decimals_and_clear_verdict():
    facts = GpaFacts(151, 100, 3.2, target_rank="xuất sắc")
    text = format_report(facts, analyze(facts))
    assert "TỐI ĐA = (320 + 51 x 4,0) / 151 = 3,47" in text
    assert "từ 3,60" in text and "từ 3,20" in text  # không phải 3,6 / 3,2
    assert "kết luận = KHÔNG THỂ" in text
    assert "GIẢ ĐỊNH" in text  # chưa biết số TC điều kiện -> phải nói rõ giả định và hỏi lại


def test_report_without_assumption_when_user_gave_excluded_credits():
    facts = GpaFacts(151, 100, 3.5, target_rank="xuất sắc", excluded_done=30, excluded_total=30)
    text = format_report(facts, analyze(facts))
    assert "GIẢ ĐỊNH" not in text
    assert "kết luận = CÓ THỂ" in text and "3,71" in text and "3,74" in text


# ---- trích số liệu từ LLM ----


def test_parse_facts_accepts_code_fences_and_decimal_commas():
    raw = '```json\n{"total_credits": 151, "done_credits": "100", "current_gpa": "3,2", "target_rank": "Xuất sắc", "excluded_done": null}\n```'
    facts = parse_facts(raw)
    assert facts == GpaFacts(151, 100, 3.2, None, "xuất sắc", None, None)


@pytest.mark.parametrize(
    "raw", ["", "không có số liệu", '{"total_credits": 151}', '{"total_credits": null, "done_credits": 1, "current_gpa": 3}', "[1, 2]"]
)
def test_parse_facts_returns_none_without_core_numbers(raw):
    assert parse_facts(raw) is None


def test_gate_requires_keyword_and_digit():
    assert looks_like_gpa_question([HumanMessage(content="Chương trình 151 chỉ, đã học 100 chỉ, điểm tb 3.2")])
    assert not looks_like_gpa_question([HumanMessage(content="Điểm trung bình chung tích lũy là gì?")])  # không có số
    assert not looks_like_gpa_question([HumanMessage(content="Học phí 2 học kỳ liên tiếp thì sao?")])  # không có từ khoá điểm


class ScriptedLLM:
    """Lượt gọi đầu (trích số liệu) trả JSON; lượt sau (trả lời) ghi lại prompt hệ thống."""

    def __init__(self, extraction: str):
        self.extraction = extraction
        self.calls: list[list[BaseMessage]] = []

    def stream(self, messages):
        self.calls.append(list(messages))
        is_extraction = "bộ trích xuất số liệu" in str(messages[0].content)
        yield AIMessageChunk(content=self.extraction if is_extraction else "ok")


def test_graph_puts_the_computed_result_into_the_prompt():
    llm = ScriptedLLM('{"total_credits": 151, "done_credits": 100, "current_gpa": 3.2, "target_rank": "xuất sắc"}')
    graph = build_chat_graph(llm, InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    graph.invoke({"messages": [HumanMessage(content="CT 151 TC, đã học 100 TC, ĐTBCTL 3,2, có đạt xuất sắc không?")]}, config)

    assert len(llm.calls) == 2  # 1 lần trích số liệu + 1 lần trả lời
    answer_prompt = str(llm.calls[1][0].content)
    assert "đã tính bằng máy tính, chính xác" in answer_prompt
    assert "= 3,47" in answer_prompt and "kết luận = KHÔNG THỂ" in answer_prompt


def test_graph_skips_extraction_for_ordinary_questions():
    llm = ScriptedLLM("{}")
    graph = build_chat_graph(llm, InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    graph.invoke({"messages": [HumanMessage(content="Học kỳ 1 bắt đầu tuần nào?")]}, config)
    assert len(llm.calls) == 1
    assert "đã tính bằng máy tính, chính xác" not in str(llm.calls[0][0].content)


def test_graph_survives_garbage_extraction():
    llm = ScriptedLLM("xin lỗi mình không hiểu")
    graph = build_chat_graph(llm, InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = graph.invoke({"messages": [HumanMessage(content="Mình học 100 TC, điểm tb 3.2")]}, config)
    assert result["messages"][-1].content == "ok"
    assert "đã tính bằng máy tính, chính xác" not in str(llm.calls[1][0].content)


def test_extraction_failure_does_not_break_the_chat():
    class Boom(ScriptedLLM):
        def stream(self, messages):
            self.calls.append(list(messages))
            if "bộ trích xuất số liệu" in str(messages[0].content):
                raise RuntimeError("429")
            yield AIMessageChunk(content="ok")

    llm = Boom("")
    assert build_gpa_report(llm, [HumanMessage(content="đã học 100 TC, ĐTBCTL 3.2")]) == ""
