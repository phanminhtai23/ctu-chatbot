"""ĐTBCHK / ĐTBCTL tính từ danh sách học phần: số học chính xác theo Điều 22 và 24."""

import uuid

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.services.chat.gpa_assist import parse_courses
from app.services.chat.graph import build_chat_graph
from app.services.grades_courses import (
    Course,
    averages,
    format_courses_report,
    make_course,
    score10_to_letter,
    semester_rank,
)


def c(credits, letter, **kw):
    course = make_course(credits, letter, **kw)
    assert course is not None
    return course


# ---- quy đổi điểm (Điều 22) ----


@pytest.mark.parametrize(
    "score,letter",
    [(10, "A"), (9.0, "A"), (8.9, "B+"), (8.0, "B+"), (7.9, "B"), (7.0, "B"), (6.9, "C+"), (6.5, "C+"), (6.4, "C"),
     (5.5, "C"), (5.4, "D+"), (5.0, "D+"), (4.9, "D"), (4.0, "D"), (3.9, "F"), (0, "F")],
)
def test_score10_to_letter_matches_article_22_table(score, letter):
    assert score10_to_letter(score) == letter


def test_score_outside_scale_is_rejected():
    assert score10_to_letter(10.5) is None
    assert score10_to_letter(-1) is None


# ---- ĐTBCHK (Điều 24 khoản 2) ----


def test_semester_gpa_weighted_by_credits():
    # 3 TC điểm A, 2 TC điểm B+, 4 TC điểm C -> (12 + 7 + 8) / 9 = 3,0
    result = averages([c(3, "A"), c(2, "B+"), c(4, "C")])
    assert result.semester_points == pytest.approx(27)
    assert result.semester_credits == 9
    assert result.semester_gpa == pytest.approx(3.0)


def test_semester_gpa_with_uneven_division():
    # 2 TC điểm B + 3 TC điểm C + 1 TC điểm D = (6 + 6 + 1) / 6 = 13/6 = 2,1667 (không phải 2,33)
    result = averages([c(2, "B"), c(3, "C"), c(1, "D")])
    assert result.semester_gpa == pytest.approx(13 / 6)
    assert round(result.semester_gpa, 2) == 2.17


def test_failed_course_counts_in_semester_gpa_but_not_cumulative():
    result = averages([c(3, "A"), c(3, "F")])
    assert result.semester_gpa == pytest.approx(2.0)  # F vẫn tính vào ĐTBCHK
    assert result.cumulative_gpa == pytest.approx(4.0)  # nhưng không tính vào ĐTBCTL
    assert result.cumulative_credits == 3


def test_gdtc_is_excluded_from_semester_gpa_but_other_condition_courses_are_included():
    gdtc = c(1, "A", is_gdtc=True)
    english = c(3, "C", is_condition=True)  # Ngoại ngữ căn bản: vào ĐTBCHK, không vào ĐTBCTL
    major = c(3, "A")
    result = averages([gdtc, english, major])
    assert result.semester_credits == 6  # GDTC bị loại
    assert result.semester_gpa == pytest.approx((3 * 2.0 + 3 * 4.0) / 6)
    assert result.cumulative_gpa == pytest.approx(4.0)  # điều kiện bị loại khỏi ĐTBCTL


def test_m_i_w_are_not_counted_anywhere():
    result = averages([c(3, "A"), c(2, "M"), c(2, "I"), c(2, "W")])
    assert result.semester_credits == 3
    assert result.cumulative_credits == 3


def test_d_is_the_lowest_accumulated_grade():
    result = averages([c(3, "D"), c(3, "F")])
    assert result.cumulative_credits == 3 and result.cumulative_gpa == pytest.approx(1.0)


def test_only_unaccumulated_courses_means_no_cumulative_gpa():
    assert averages([c(3, "F")]).cumulative_gpa is None


def test_score10_input_is_converted():
    course = c(3, None, score10=7.2)
    assert course.letter == "B" and course.point == 3.0


@pytest.mark.parametrize("gpa,rank", [(3.6, "Xuất sắc"), (3.59, "Giỏi"), (3.25, "Giỏi"), (2.5, "Khá"), (2.4, "Trung bình"),
                                      (1.99, "Yếu"), (1.0, "Yếu"), (0.95, "Kém")])
def test_semester_rank_table(gpa, rank):
    assert semester_rank(gpa) == rank


# ---- dữ liệu sai ----


@pytest.mark.parametrize("kwargs", [dict(credits=0, letter="A"), dict(credits=-1, letter="A"), dict(credits=3, letter="Z"),
                                    dict(credits=3, letter=None, score10=None), dict(credits=None, letter="A"),
                                    dict(credits=3, letter=None, score10=11)])
def test_invalid_course_is_rejected(kwargs):
    assert make_course(**kwargs) is None


def test_parse_courses_all_or_nothing():
    good = '{"courses": [{"credits": 3, "letter": "A"}, {"credits": 2, "letter": "B+", "name": "Toán"}]}'
    assert [x.letter for x in parse_courses(good)] == ["A", "B+"]
    bad = '{"courses": [{"credits": 3, "letter": "A"}, {"credits": 2, "letter": "ZZ"}]}'
    assert parse_courses(bad) == []  # có một môn sai thì không tính bừa phần còn lại
    assert parse_courses('{"courses": []}') == []
    assert parse_courses("không phải json") == []


# ---- báo cáo đưa cho LLM ----


def test_report_states_the_exact_division():
    text = format_courses_report([c(2, "B"), c(3, "C"), c(1, "D")])
    assert "13 / 6 = 2,17" in text
    assert "Trung bình" in text


def test_report_mentions_f_rule_and_condition_rule():
    text = format_courses_report([c(3, "A"), c(3, "F"), c(1, "A", is_gdtc=True)])
    assert "= 2,00" in text and "Học phần F vẫn được tính vào ĐTBCHK" in text
    assert "GDTC: không vào ĐTBCHK/ĐTBCTL" in text


# ---- tích hợp với đồ thị ----


class ScriptedLLM:
    def __init__(self, extraction: str):
        self.extraction = extraction
        self.calls = []

    def stream(self, messages):
        self.calls.append(list(messages))
        yield AIMessageChunk(content=self.extraction if "bộ trích xuất số liệu" in str(messages[0].content) else "ok")


def test_graph_injects_semester_gpa_into_the_prompt():
    extraction = (
        '{"courses": [{"name": "X", "credits": 2, "letter": "B"}, {"name": "Y", "credits": 3, "letter": "C"},'
        ' {"name": "Z", "credits": 1, "letter": "D"}]}'
    )
    llm = ScriptedLLM(extraction)
    graph = build_chat_graph(llm, InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    graph.invoke(
        {"messages": [HumanMessage(content="Môn X 2 tín chỉ điểm B, môn Y 3 tín chỉ điểm C, môn Z 1 tín chỉ điểm D. ĐTBCHK là bao nhiêu?")]},
        config,
    )
    prompt = str(llm.calls[1][0].content)
    assert "13 / 6 = 2,17" in prompt
