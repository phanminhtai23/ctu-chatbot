"""Bộ luật học vụ chạy bằng mã: hạng tốt nghiệp (Điều 34), cảnh báo học tập (Điều 18), học bổng (Điều 9).

Các tình huống t*, w*, s* khớp với tests/rag_cases_hard.py (nơi bot từng sai: mốc đúng bằng ngưỡng, giảm hạng
chồng hai lý do, xếp mức học bổng trước khi so điểm).
"""

import uuid

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.services.chat.gpa_assist import (
    build_report_from_extraction,
    looks_like_gpa_question,
    parse_graduation,
    parse_students,
    parse_warning,
)
from app.services.chat.graph import build_chat_graph
from app.services.rules import (
    GraduationFacts,
    Student,
    WarningFacts,
    conduct_rank,
    evaluate_graduation,
    evaluate_warning,
    format_graduation,
    format_scholarship,
    format_warning,
    rank_scholarship,
)

# =====================================================================================================
# Hạng tốt nghiệp (Điều 34)
# =====================================================================================================


def grad(gpa, total=None, f=None, severe=None):
    result = evaluate_graduation(GraduationFacts(gpa, total, f, severe))
    assert result is not None
    return result


def test_t01_exactly_five_percent_f_is_not_exceeding():
    r = grad(3.7, 120, 6, False)
    assert r.f_known and not r.f_exceeds
    assert (r.base_rank, r.final_rank, r.downgraded) == ("xuất sắc", "xuất sắc", False)


def test_t02_above_five_percent_f_downgrades_one_level():
    r = grad(3.7, 120, 7, False)
    assert r.f_exceeds and r.downgraded
    assert (r.base_rank, r.final_rank) == ("xuất sắc", "giỏi")


def test_t03_school_level_warning_discipline_downgrades_giỏi_to_khá():
    r = grad(3.3, severe=True)
    assert (r.base_rank, r.final_rank, r.downgraded) == ("giỏi", "khá", True)


def test_t04_reprimand_or_no_discipline_does_not_downgrade():
    r = grad(3.3, severe=False)
    assert (r.final_rank, r.downgraded) == ("giỏi", False)


def test_t05_only_normal_f_credits_count_so_improvement_f_is_excluded_by_extraction():
    # 4 TC F thường (3,3%) trên 120 TC; 5 TC F của học phần cải thiện đã bị loại ở bước trích số liệu
    r = grad(3.7, 120, 4, False)
    assert r.final_rank == "xuất sắc"


def test_t06_both_reasons_still_downgrade_only_one_level():
    r = grad(3.8, 120, 8, True)
    assert r.downgraded and r.final_rank == "giỏi"  # KHÔNG phải khá
    assert len(r.reasons) == 2


def test_t07_khá_is_never_downgraded():
    r = grad(3.0, 120, 10, True)
    assert (r.base_rank, r.final_rank, r.downgraded) == ("khá", "khá", False)


def test_t08_giỏi_with_f_over_five_percent_drops_to_khá():
    r = grad(3.5, 120, 8, False)
    assert (r.base_rank, r.final_rank) == ("giỏi", "khá")


@pytest.mark.parametrize(
    "gpa,expected",
    [(3.60, "xuất sắc"), (3.599, "xuất sắc"), (3.59, "giỏi"), (3.20, "giỏi"), (3.19, "khá"), (2.50, "khá"), (2.49, "trung bình"), (2.00, "trung bình")],
)
def test_t09_rank_boundaries(gpa, expected):
    assert grad(gpa).base_rank == expected


def test_t10_below_two_is_not_eligible_to_graduate():
    r = grad(1.95)
    assert r.base_rank is None and r.graduates is False and r.final_rank is None


def test_unknown_f_and_discipline_are_assumed_absent_but_flagged():
    facts = GraduationFacts(3.7)
    text = format_graduation(facts, evaluate_graduation(facts))
    assert "chưa nêu" in text and "tạm coi" in text
    assert "HẠNG CUỐI CÙNG: xuất sắc" in text


def test_report_for_downgrade_names_the_reason_and_single_level():
    facts = GraduationFacts(3.5, 120, 8, False)
    text = format_graduation(facts, evaluate_graduation(facts))
    assert "HẠNG CUỐI CÙNG: khá" in text and "VƯỢT quá 5%" in text
    assert "6,67%" in text and "ngưỡng 5% = 6 TC" in text


def test_invalid_gpa_is_rejected():
    assert evaluate_graduation(GraduationFacts(4.5)) is None


# =====================================================================================================
# Cảnh báo học tập, buộc thôi học (Điều 18)
# =====================================================================================================


def warn(**kw):
    return evaluate_warning(WarningFacts(**kw))


def test_w01_first_semester_below_080_is_warned():
    assert warn(semester_gpa=0.75, is_first_semester=True).warned


def test_w01b_first_semester_exactly_080_is_not_below():
    assert not warn(semester_gpa=0.80, is_first_semester=True).warned


def test_w02_exactly_100_in_later_semester_is_not_below():
    r = warn(semester_gpa=1.00, is_first_semester=False)
    assert not r.warned


def test_gpa_between_080_and_100_needs_to_know_if_first_semester():
    r = warn(semester_gpa=0.9)
    assert not r.warned
    assert any("học kỳ đầu" in m for m in r.missing) or r.missing


def test_gpa_below_080_is_a_violation_even_without_knowing_the_semester():
    assert warn(semester_gpa=0.7).warned


def test_w03_more_than_half_failed_is_warned_for_k47_plus():
    assert warn(cohort=48, registered_credits=16, failed_credits=9).warned


def test_w04_exactly_half_failed_is_not_exceeding():
    r = warn(cohort=48, registered_credits=16, failed_credits=8, semester_gpa=1.5)
    assert not r.warned
    assert "đúng bằng 50%" in "".join(c.detail for c in r.criteria)


def test_w05_owing_more_than_24_credits_is_warned_for_k47():
    assert warn(cohort=47, owed_credits=25).warned


def test_owing_exactly_24_credits_is_not_exceeding():
    assert not warn(cohort=47, owed_credits=24).warned


def test_w06_owing_credits_rule_does_not_apply_before_k47():
    r = warn(cohort=46, owed_credits=30, semester_gpa=2.0, is_first_semester=False)
    assert not r.warned
    assert any(c.status == "khong_ap_dung" for c in r.criteria)


@pytest.mark.parametrize(
    "year,cumulative,warned",
    [(1, 1.15, True), (1, 1.2, False), (2, 1.35, True), (2, 1.4, False), (2, 1.45, False), (3, 1.5, True), (3, 1.6, False), (4, 1.7, True), (5, 1.8, False)],
)
def test_w07_to_w09_cumulative_gpa_thresholds_by_year(year, cumulative, warned):
    assert warn(cohort=48, year_level=year, cumulative_gpa=cumulative).warned is warned


def test_w10_warned_before_and_gpa_below_100_means_expelled():
    r = warn(previously_warned=True, semester_gpa=0.95)
    assert r.expelled is True


def test_w11_warned_before_and_exactly_100_is_not_expelled():
    r = warn(previously_warned=True, semester_gpa=1.00)
    assert r.expelled is False


def test_not_previously_warned_means_no_expulsion_verdict():
    assert warn(previously_warned=False, semester_gpa=0.5).expelled is None


def test_skipping_registration_without_permission_is_a_violation():
    assert warn(skipped_registration=True).warned


def test_warning_report_flags_unchecked_criteria_instead_of_claiming_all_clear():
    text = format_warning(warn(cohort=48, registered_credits=16, failed_credits=8, semester_gpa=1.5))
    assert "KHÔNG bị cảnh báo học tập" in text and "chưa kiểm tra được" in text
    assert "đúng bằng 50%" in text


def test_warning_report_with_violation():
    text = format_warning(warn(cohort=48, registered_credits=16, failed_credits=9))
    assert "KẾT LUẬN: BỊ cảnh báo học tập" in text and "vượt quá 50%" in text


# =====================================================================================================
# Học bổng (Điều 9)
# =====================================================================================================


def names(students):
    return [r.student.name for r in rank_scholarship(students)]


def test_conduct_bands_from_circular_16():
    assert [conduct_rank(x) for x in (95, 90, 89, 80, 79, 65, 64, 50, 49, 35, 34)] == [
        "xuất sắc", "xuất sắc", "tốt", "tốt", "khá", "khá", "trung bình", "trung bình", "yếu", "yếu", "kém",
    ]


def test_h01_level_beats_gpa():
    # A: 3,8 / 89 (ĐRL tốt) -> mức giỏi; B: 3,6 / 90 -> mức xuất sắc => B được xét trước
    results = rank_scholarship([Student("A", 3.8, 89), Student("B", 3.6, 90)])
    assert [r.student.name for r in results] == ["B", "A"]
    assert [r.level for r in results] == ["xuất sắc", "giỏi"]


def test_h02_same_level_compares_gpa_first():
    assert names([Student("B", 3.7, 95), Student("A", 3.8, 92)]) == ["A", "B"]


def test_h03_same_level_and_gpa_compares_conduct():
    assert names([Student("A", 3.7, 91), Student("B", 3.7, 95)]) == ["B", "A"]


def test_s01_too_few_registered_credits_is_ineligible():
    r = rank_scholarship([Student("X", 3.7, 95, registered_credits=10)])[0]
    assert not r.eligible and "12 TC" in r.problems[0]


def test_s01b_credits_arranged_by_school_are_exempt():
    r = rank_scholarship([Student("X", 3.7, 95, registered_credits=10, credits_arranged_by_school=True)])[0]
    assert r.eligible


def test_s02_s03_f_grade_or_school_discipline_is_ineligible():
    assert not rank_scholarship([Student("X", 3.5, 85, has_f=True)])[0].eligible
    assert not rank_scholarship([Student("X", 3.9, 92, school_discipline=True)])[0].eligible


def test_s04_conduct_79_only_reaches_khá_level():
    r = rank_scholarship([Student("X", 3.3, 79)])[0]
    assert r.level == "khá"  # giỏi cần ĐRL từ 80


def test_s05_same_level_same_gpa_conduct_decides():
    assert names([Student("B", 3.5, 84), Student("A", 3.5, 88)]) == ["A", "B"]


def test_s08_three_students_ordered_by_level_then_gpa():
    # A: 3,65/91 xuất sắc; B: 3,9/88 giỏi; C: 3,3/80 giỏi
    results = rank_scholarship([Student("C", 3.3, 80), Student("B", 3.9, 88), Student("A", 3.65, 91)])
    assert [r.student.name for r in results] == ["A", "B", "C"]
    assert [r.level for r in results] == ["xuất sắc", "giỏi", "giỏi"]


def test_below_khá_reaches_no_level():
    r = rank_scholarship([Student("X", 2.3, 70)])[0]
    assert r.level is None and not r.eligible


def test_ineligible_students_are_listed_last_whatever_their_scores():
    assert names([Student("Giỏi nhưng nợ", 3.9, 95, has_f=True), Student("Khá", 2.6, 66)]) == ["Khá", "Giỏi nhưng nợ"]


def test_scholarship_report_states_order_and_levels():
    text = format_scholarship(rank_scholarship([Student("A", 3.8, 89), Student("B", 3.6, 90)]))
    assert "THỨ TỰ ƯU TIÊN XÉT HỌC BỔNG (từ trước đến sau): B > A" in text
    assert "đạt MỨC XUẤT SẮC" in text and "đạt MỨC GIỎI" in text and "loại tốt" in text


def test_identical_students_are_reported_as_tied():
    text = format_scholarship(rank_scholarship([Student("A", 3.7, 91), Student("B", 3.7, 91)]))
    assert "ngang hạng" in text


# =====================================================================================================
# Trích số liệu và tích hợp với đồ thị
# =====================================================================================================


def test_gate_fires_for_rule_questions_with_a_single_number():
    assert looks_like_gpa_question([HumanMessage(content="ĐTBCHK học kỳ đầu của mình là 0,75. Mình có bị cảnh báo học tập không?")])
    assert looks_like_gpa_question([HumanMessage(content="gpa 3,8 đrl 89 và gpa 3,6 đrl 90 thì ai được học bổng?")])
    assert not looks_like_gpa_question([HumanMessage(content="Theo Điều 9, học bổng được xét thế nào?")])  # chỉ "Điều 9"


def test_parse_graduation_and_warning_and_students():
    raw = (
        '{"graduation": {"gpa": "3,5", "total_credits": 120, "f_credits": 8, "improvement_f_credits": 5, "severe_discipline": false},'
        ' "warning": {"cohort": "K48", "semester_gpa": 1.5, "registered_credits": 16, "failed_credits": 8, "year_level": 2,'
        ' "is_first_semester": false, "previously_warned": null},'
        ' "scholarship": [{"name": "A", "gpa": 3.8, "conduct": 89}, {"gpa": 3.6, "conduct": 90}, {"name": "thiếu", "gpa": 3.0}]}'
    )
    assert parse_graduation(raw) == GraduationFacts(3.5, 120, 8, False)
    warning = parse_warning(raw.replace('"K48"', "48"))
    assert warning.cohort == 48 and warning.failed_credits == 8 and warning.year_level == 2
    students = parse_students(raw)
    assert [s.name for s in students] == ["A", "Người 2"]  # phần tử thiếu ĐRL bị bỏ qua


def test_parse_ignores_empty_or_garbage():
    assert parse_graduation("{}") is None and parse_warning("{}") is None and parse_students("{}") == []
    assert parse_graduation("không phải json") is None
    assert parse_warning('{"warning": {"cohort": 48}}') is None  # chỉ có khóa, chưa có số liệu nào để kiểm tra


def test_extraction_to_report_end_to_end():
    raw = '{"scholarship": [{"name": "A", "gpa": 3.8, "conduct": 89}, {"name": "B", "gpa": 3.6, "conduct": 90}]}'
    report = build_report_from_extraction(raw)
    assert "B > A" in report
    raw = '{"warning": {"cohort": 48, "registered_credits": 16, "failed_credits": 8, "semester_gpa": 1.5}}'
    assert "KHÔNG bị cảnh báo học tập" in build_report_from_extraction(raw)
    raw = '{"graduation": {"gpa": 3.5, "total_credits": 120, "f_credits": 8}}'
    assert "HẠNG CUỐI CÙNG: khá" in build_report_from_extraction(raw)


class ScriptedLLM:
    def __init__(self, extraction: str):
        self.extraction = extraction
        self.calls = []

    def stream(self, messages):
        self.calls.append(list(messages))
        yield AIMessageChunk(content=self.extraction if "bộ trích xuất số liệu" in str(messages[0].content) else "ok")


def test_graph_injects_the_scholarship_order_into_the_prompt():
    llm = ScriptedLLM('{"scholarship": [{"name": "A", "gpa": 3.8, "conduct": 89}, {"name": "B", "gpa": 3.6, "conduct": 90}]}')
    graph = build_chat_graph(llm, InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    graph.invoke({"messages": [HumanMessage(content="gpa 3,8 đrl 89, gpa 3,6 đrl 90 thì ai được học bổng?")]}, config)
    assert len(llm.calls) == 2
    prompt = str(llm.calls[1][0].content)
    assert "B > A" in prompt and "XÉT HỌC BỔNG" in prompt


def test_graph_keeps_working_when_extracted_values_have_wrong_types():
    llm = ScriptedLLM('{"graduation": {"gpa": "cao", "total_credits": "nhiều"}, "warning": {"semester_gpa": [1]}, "scholarship": "A"}')
    graph = build_chat_graph(llm, InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = graph.invoke({"messages": [HumanMessage(content="mình bị cảnh báo học tập, ĐTBCHK 0,9")]}, config)
    assert result["messages"][-1].content == "ok"
