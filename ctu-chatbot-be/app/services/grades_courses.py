"""Tính ĐTBCHK / ĐTBCTL từ danh sách học phần bằng số học chính xác.

Căn cứ QĐ 3266/QĐ-ĐHCT:
- Điều 22 khoản 2: bảng quy đổi điểm thang 10 -> điểm chữ -> thang 4. Khoản 3: chỉ tích lũy khi đạt từ D.
- Điều 22 khoản 5: điểm M, I, W không tính vào ĐTBCHK và ĐTBCTL.
- Điều 24 khoản 2: ĐTBCHK = tổng(TC x điểm hệ 4) / tổng TC, KỂ CẢ học phần F và học phần điều kiện, TRỪ GDTC.
- Điều 24 khoản 4: ĐTBCTL chỉ gồm học phần đã tích lũy, KHÔNG gồm F và học phần điều kiện.
- Điều 24 khoản 5: xếp loại học tập theo ĐTBCHK/ĐTBCNH.
"""

from dataclasses import dataclass

LETTER_POINTS: dict[str, float] = {"A": 4.0, "B+": 3.5, "B": 3.0, "C+": 2.5, "C": 2.0, "D+": 1.5, "D": 1.0, "F": 0.0}
NOT_COUNTED_LETTERS = {"M", "I", "W"}
# (ngưỡng dưới theo thang 10, điểm chữ), xét từ cao xuống thấp
_SCORE_TO_LETTER = [(9.0, "A"), (8.0, "B+"), (7.0, "B"), (6.5, "C+"), (5.5, "C"), (5.0, "D+"), (4.0, "D")]
SEMESTER_RANKS = [(3.60, "Xuất sắc"), (3.20, "Giỏi"), (2.50, "Khá"), (2.00, "Trung bình"), (1.00, "Yếu")]


def score10_to_letter(score: float) -> str | None:
    """Điểm thang 10 (đã làm tròn 1 chữ số thập phân) -> điểm chữ; None nếu ngoài 0-10."""
    if score < 0 or score > 10:
        return None
    rounded = round(score + 1e-9, 1)
    for threshold, letter in _SCORE_TO_LETTER:
        if rounded >= threshold:
            return letter
    return "F"


def semester_rank(gpa: float) -> str:
    value = round(gpa + 1e-9, 2)
    for threshold, name in SEMESTER_RANKS:
        if value >= threshold:
            return name
    return "Kém"


@dataclass(frozen=True)
class Course:
    credits: float
    letter: str  # A, B+, B, C+, C, D+, D, F, hoặc M/I/W (không tính điểm)
    name: str = ""
    is_condition: bool = False  # học phần điều kiện: GDQP&AN, GDTC, Ngoại ngữ căn bản, Tin học căn bản
    is_gdtc: bool = False  # GDTC: không tính vào ĐTBCHK/ĐTBCNH (nhưng vẫn là học phần điều kiện)
    score10: float | None = None

    @property
    def point(self) -> float | None:
        return LETTER_POINTS.get(self.letter)


def make_course(credits, letter=None, score10=None, name="", is_condition=False, is_gdtc=False) -> Course | None:
    """Dựng một học phần hợp lệ; None nếu thiếu/ sai dữ liệu (để không tính bừa)."""
    if isinstance(credits, bool) or not isinstance(credits, (int, float)) or credits <= 0:
        return None
    letter_norm = str(letter).strip().upper().replace(" ", "") if letter else ""
    if not letter_norm and score10 is not None:
        letter_norm = score10_to_letter(float(score10)) or ""
    if letter_norm not in LETTER_POINTS and letter_norm not in NOT_COUNTED_LETTERS:
        return None
    return Course(
        credits=float(credits),
        letter=letter_norm,
        name=name or "",
        is_condition=bool(is_condition or is_gdtc),
        is_gdtc=bool(is_gdtc),
        score10=float(score10) if score10 is not None else None,
    )


@dataclass(frozen=True)
class CourseAverages:
    semester_points: float
    semester_credits: float
    semester_gpa: float | None  # ĐTBCHK; None nếu không có học phần nào được tính
    cumulative_points: float
    cumulative_credits: float
    cumulative_gpa: float | None  # ĐTBCTL của các học phần này (chỉ phần đã tích lũy, không F, không điều kiện)


def averages(courses: list[Course]) -> CourseAverages:
    sem_points = sem_credits = cum_points = cum_credits = 0.0
    for course in courses:
        point = course.point
        if point is None:  # M, I, W
            continue
        if not course.is_gdtc:  # Điều 24 khoản 2: GDTC không vào ĐTBCHK; học phần điều kiện khác và F thì có
            sem_points += course.credits * point
            sem_credits += course.credits
        if point >= LETTER_POINTS["D"] and not course.is_condition:  # Điều 24 khoản 4
            cum_points += course.credits * point
            cum_credits += course.credits
    return CourseAverages(
        semester_points=sem_points,
        semester_credits=sem_credits,
        semester_gpa=sem_points / sem_credits if sem_credits else None,
        cumulative_points=cum_points,
        cumulative_credits=cum_credits,
        cumulative_gpa=cum_points / cum_credits if cum_credits else None,
    )


def _n(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _g(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def format_courses_report(courses: list[Course]) -> str:
    result = averages(courses)
    lines = ["KẾT QUẢ TÍNH SẴN cho các học phần người dùng nêu (đã tính bằng máy tính, chính xác): dùng NGUYÊN các con số này, KHÔNG tự tính lại."]
    for i, course in enumerate(courses, 1):
        label = course.name or f"Học phần {i}"
        tags = []
        if course.is_gdtc:
            tags.append("GDTC: không vào ĐTBCHK/ĐTBCTL")
        elif course.is_condition:
            tags.append("học phần điều kiện: vào ĐTBCHK nhưng không vào ĐTBCTL")
        if course.letter in NOT_COUNTED_LETTERS:
            tags.append(f"điểm {course.letter}: không tính vào ĐTBCHK/ĐTBCTL")
        score = f", điểm {_n(course.score10)}" if course.score10 is not None else ""
        if course.point is not None:
            body = f"{_n(course.credits)} TC{score}, điểm chữ {course.letter} = {_g(course.point)} (hệ 4); {_n(course.credits)} x {_g(course.point)} = {_n(course.credits * course.point)}"
        else:
            body = f"{_n(course.credits)} TC{score}, điểm {course.letter}"
        lines.append(f"- {label}: {body}" + (f" [{'; '.join(tags)}]" if tags else ""))
    if result.semester_gpa is not None:
        lines.append(
            f"- ĐTBCHK = tổng(TC x điểm) / tổng TC = {_n(result.semester_points)} / {_n(result.semester_credits)} = "
            f"{_g(result.semester_gpa)} -> xếp loại học tập: {semester_rank(result.semester_gpa)} (Điều 24). "
            "Học phần F vẫn được tính vào ĐTBCHK."
        )
    if result.cumulative_gpa is not None:
        lines.append(
            f"- ĐTBCTL của các học phần này (chỉ học phần đã tích lũy, bỏ F và học phần điều kiện) = "
            f"{_n(result.cumulative_points)} / {_n(result.cumulative_credits)} = {_g(result.cumulative_gpa)}."
        )
    else:
        lines.append("- ĐTBCTL: chưa có học phần nào đủ điều kiện được tính (đã tích lũy và không phải học phần điều kiện).")
    return "\n".join(lines)
