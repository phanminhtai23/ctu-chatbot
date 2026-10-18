"""Các tình huống khó của máy tính điểm (không cần LLM). Đáp án tính độc lập, khớp với tests/rag_cases_hard.py."""

import pytest

from app.services.grades import GpaFacts, analyze
from app.services.grades_courses import averages, make_course, semester_rank


def course(credits, letter=None, **kw):
    made = make_course(credits, letter, **kw)
    assert made is not None
    return made


# ---- b01 / b02: GDTC bị loại khỏi ĐTBCHK; F và học phần điều kiện khác vẫn tính; ĐTBCTL bỏ cả F lẫn điều kiện ----


def test_b01_b02_semester_and_cumulative_with_f_condition_and_gdtc():
    courses = [
        course(3, "A"),
        course(3, "B+"),
        course(1, "A", is_gdtc=True),
        course(3, "C", is_condition=True),  # Ngoại ngữ căn bản
        course(2, "F"),
    ]
    result = averages(courses)
    assert result.semester_credits == 11
    assert result.semester_gpa == pytest.approx(28.5 / 11)
    assert round(result.semester_gpa, 2) == 2.59
    assert semester_rank(result.semester_gpa) == "Khá"
    assert result.cumulative_gpa == pytest.approx(22.5 / 6)  # 3,75
    assert round(result.cumulative_gpa, 2) == 3.75


def test_b03_withdrawn_and_incomplete_courses_are_ignored():
    result = averages([course(3, "A"), course(2, "W"), course(3, "I"), course(4, "B")])
    assert result.semester_credits == 7
    assert round(result.semester_gpa, 2) == 3.43


def test_b04_ten_point_scores_are_converted_before_averaging():
    courses = [course(3, None, score10=8.4), course(2, None, score10=6.9), course(4, None, score10=5.4)]
    assert [c.letter for c in courses] == ["B+", "C+", "D+"]
    result = averages(courses)
    assert round(result.semester_gpa, 2) == 2.39
    assert semester_rank(result.semester_gpa) == "Trung bình"


# ---- k01..k08: còn lại bao nhiêu chỉ, khả năng đạt loại ----


def test_k03_excluded_credits_change_both_c_and_t():
    r = analyze(GpaFacts(151, 100, 3.5, target_rank="xuất sắc", excluded_done=30, excluded_total=30))
    assert r.remaining == 51
    assert round(r.max_gpa, 2) == 3.71
    assert round(r.target.needed_average, 2) == 3.74
    assert r.target.achievable


def test_k02_remaining_credits_when_excluded_courses_are_already_done():
    r = analyze(GpaFacts(140, 90, 3.0, excluded_done=8, excluded_total=8))
    assert r.remaining == 50  # (140 - 8) - (90 - 8)


def test_k04_giỏi_is_possible_but_needs_3_8():
    r = analyze(GpaFacts(120, 90, 3.0, target_rank="giỏi"))
    assert round(r.max_gpa, 2) == 3.25
    assert round(r.target.needed_average, 2) == 3.80
    assert r.target.achievable


def test_k05_excellent_is_out_of_reach():
    r = analyze(GpaFacts(130, 120, 3.5, target_rank="xuất sắc"))
    assert round(r.max_gpa, 2) == 3.54
    assert r.target.achievable is False


def test_k06_needed_average_to_graduate():
    r = analyze(GpaFacts(150, 100, 1.8, target_rank="trung bình"))
    assert round(r.target.needed_average, 2) == 2.40
    assert r.target.achievable


def test_k07_keeping_excellent_needs_3_3_so_not_yet_certain():
    r = analyze(GpaFacts(120, 60, 3.9, target_rank="xuất sắc"))
    assert round(r.target.needed_average, 2) == 3.30
    assert r.target.needed_average > 0  # chưa "chắc chắn": vẫn phải giữ điểm


def test_k08_early_stage_with_perfect_gpa():
    r = analyze(GpaFacts(120, 20, 4.0, target_rank="xuất sắc"))
    assert round(r.target.needed_average, 2) == 3.52


def test_b07_exactly_all_a_is_still_possible():
    # (3,2 x 75 - 60 x 3,0) / 15 = 4,0: phải được toàn A nhưng vẫn khả thi
    r = analyze(GpaFacts(75, 60, 3.0, target_gpa=3.2))
    assert round(r.target.needed_average, 2) == 4.00
    assert r.target.achievable is True


def test_a_certain_rank_when_enough_points_are_already_banked():
    # 100/101 TC đã học với ĐTBCTL 3,9: dù 1 TC còn lại được điểm D vẫn xuất sắc
    r = analyze(GpaFacts(101, 100, 3.9, target_rank="xuất sắc"))
    assert r.target.needed_average < 1.0


# ---- "đã chắc chắn" hay "chưa chắc chắn" (k07) ----


def test_k07_not_yet_certain_when_remaining_credits_could_drag_the_average_down():
    r = analyze(GpaFacts(120, 60, 3.9, target_rank="xuất sắc"))
    assert round(r.min_gpa, 2) == 2.45  # (234 + 60 x 1,0) / 120: phần còn lại chỉ được điểm D
    assert r.target.achievable and not r.target.guaranteed


def test_certain_when_even_the_lowest_passing_grade_keeps_the_rank():
    r = analyze(GpaFacts(101, 100, 3.9, target_rank="xuất sắc"))
    assert round(r.min_gpa, 2) == 3.87 and r.target.guaranteed


def test_certain_when_no_credits_remain_and_the_rank_is_reached():
    assert analyze(GpaFacts(120, 120, 3.61, target_rank="xuất sắc")).target.guaranteed
    assert not analyze(GpaFacts(120, 120, 3.59, target_rank="xuất sắc")).target.guaranteed


def test_report_says_certainty_in_words():
    from app.services.grades import format_report

    facts = GpaFacts(120, 60, 3.9, target_rank="xuất sắc")
    assert "CHƯA CHẮC CHẮN" in format_report(facts, analyze(facts))
    facts = GpaFacts(101, 100, 3.9, target_rank="xuất sắc")
    assert "ĐÃ CHẮC CHẮN đạt loại xuất sắc" in format_report(facts, analyze(facts))
