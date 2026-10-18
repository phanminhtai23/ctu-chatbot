"""Các quy tắc học vụ có điều kiện/ngưỡng được kiểm tra bằng mã (không giao cho LLM so sánh).

LLM nhỏ hay sai ở các mốc "đúng bằng ngưỡng", "vượt quá", và khi phải áp dụng nhiều bước theo thứ tự. Mỗi hàm ở đây
nhận số liệu đã trích từ câu hỏi, trả kết quả chính xác kèm lý do; LLM chỉ việc diễn giải.

Căn cứ QĐ 3266/QĐ-ĐHCT:
- Điều 34: hạng tốt nghiệp theo ĐTBCTL; xuất sắc/giỏi bị giảm MỘT mức nếu (a) khối lượng học phần điểm F vượt quá 5%
  tổng TC của chương trình (không tính F của học phần học cải thiện) hoặc (b) từng bị kỷ luật từ cảnh cáo cấp Trường.
- Điều 18: cảnh báo học tập và buộc thôi học.
- Điều 9: xếp MỨC học bổng (cả ĐTBCHK lẫn ĐRL), cấp từ mức cao xuống thấp, cùng mức thì so ĐTBCHK rồi ĐRL.
- Xếp loại ĐRL theo Thông tư 16/2015/TT-BGDĐT (QĐ 3266 viện dẫn): 90-100 xuất sắc; 80-<90 tốt; 65-<80 khá;
  50-<65 trung bình; 35-<50 yếu; <35 kém.
"""

from dataclasses import dataclass, field

from app.services.grades import rank_of

_EPS = 1e-9

# ----------------------------------------------------------------------------------------------------------------
# Định dạng số
# ----------------------------------------------------------------------------------------------------------------


def _g(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def _n(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


# ----------------------------------------------------------------------------------------------------------------
# Điểm rèn luyện
# ----------------------------------------------------------------------------------------------------------------

CONDUCT_BANDS: list[tuple[str, float]] = [("xuất sắc", 90), ("tốt", 80), ("khá", 65), ("trung bình", 50), ("yếu", 35)]


def conduct_rank(score: float) -> str:
    for name, threshold in CONDUCT_BANDS:
        if score >= threshold:
            return name
    return "kém"


# ----------------------------------------------------------------------------------------------------------------
# Hạng tốt nghiệp (Điều 34)
# ----------------------------------------------------------------------------------------------------------------

_LOWER = {"xuất sắc": "giỏi", "giỏi": "khá"}  # chỉ xuất sắc và giỏi bị giảm hạng, mỗi lần MỘT mức


@dataclass(frozen=True)
class GraduationFacts:
    gpa: float  # ĐTBCTL toàn khóa
    total_credits: float | None = None  # tổng TC quy định của chương trình đào tạo
    f_credits: float | None = None  # TC bị điểm F, KHÔNG gồm học phần học cải thiện bị F
    severe_discipline: bool | None = None  # từng bị kỷ luật từ cảnh cáo cấp Trường trở lên; None = chưa nói


@dataclass(frozen=True)
class GraduationResult:
    base_rank: str | None
    final_rank: str | None
    graduates: bool  # ĐTBCTL >= 2,00 (Điều 32)
    f_ratio: float | None
    f_exceeds: bool
    f_known: bool
    discipline: bool
    discipline_known: bool
    downgraded: bool
    reasons: list[str] = field(default_factory=list)


def evaluate_graduation(facts: GraduationFacts) -> GraduationResult | None:
    if not (0 <= facts.gpa <= 4.0):
        return None
    base = rank_of(facts.gpa)
    f_known = facts.total_credits is not None and facts.total_credits > 0 and facts.f_credits is not None
    f_ratio = (facts.f_credits / facts.total_credits) if f_known else None
    # "vượt quá 5%": phải LỚN HƠN 5% (đúng bằng 5% thì chưa vượt). Nhân chéo để tránh sai số số thực.
    f_exceeds = bool(f_known and facts.f_credits * 20 > facts.total_credits + _EPS)
    discipline_known = facts.severe_discipline is not None
    discipline = bool(facts.severe_discipline)

    reasons: list[str] = []
    if f_exceeds:
        reasons.append("khối lượng học phần điểm F vượt quá 5% tổng TC của chương trình")
    if discipline:
        reasons.append("từng bị kỷ luật từ mức cảnh cáo cấp Trường trở lên")

    final = base
    downgraded = False
    if base in _LOWER and reasons:
        final = _LOWER[base]  # chỉ giảm MỘT mức, dù thuộc cả hai trường hợp
        downgraded = True
    return GraduationResult(
        base_rank=base,
        final_rank=final,
        graduates=base is not None,
        f_ratio=f_ratio,
        f_exceeds=f_exceeds,
        f_known=f_known,
        discipline=discipline,
        discipline_known=discipline_known,
        downgraded=downgraded,
        reasons=reasons,
    )


def format_graduation(facts: GraduationFacts, result: GraduationResult) -> str:
    lines = [
        "KẾT QUẢ TÍNH SẴN về HẠNG TỐT NGHIỆP (Điều 34; đã kiểm tra bằng mã, chính xác): dùng NGUYÊN kết luận này, KHÔNG tự suy luận lại.",
        f"- ĐTBCTL = {_g(facts.gpa)} -> hạng theo điểm: {result.base_rank or 'chưa đủ 2,00 nên chưa đủ điều kiện tốt nghiệp (Điều 32)'}.",
    ]
    if result.f_known:
        threshold = facts.total_credits * 0.05
        lines.append(
            f"- Học phần điểm F (không tính học phần học cải thiện bị F): {_n(facts.f_credits)} TC / {_n(facts.total_credits)} TC = "
            f"{result.f_ratio * 100:.2f}%".replace(".", ",")
            + f"; ngưỡng 5% = {_n(threshold)} TC (phải LỚN HƠN ngưỡng mới bị tính là vượt quá) -> "
            + ("VƯỢT quá 5%." if result.f_exceeds else "KHÔNG vượt quá 5%.")
        )
    else:
        lines.append("- Học phần điểm F: người dùng chưa nêu đủ (cần số TC bị F và tổng TC chương trình); tạm coi là không vượt quá 5%.")
    if result.discipline_known:
        lines.append(
            "- Kỷ luật từ cảnh cáo cấp Trường trở lên: " + ("CÓ." if result.discipline else "KHÔNG (khiển trách hoặc chưa bị kỷ luật không làm giảm hạng).")
        )
    else:
        lines.append("- Kỷ luật: người dùng chưa nêu; tạm coi là chưa bị kỷ luật từ cảnh cáo cấp Trường trở lên.")
    if result.base_rank is None:
        lines.append("- HẠNG CUỐI CÙNG: chưa đủ điều kiện tốt nghiệp vì ĐTBCTL dưới 2,00.")
    elif result.downgraded:
        lines.append(
            f"- HẠNG CUỐI CÙNG: {result.final_rank} (bị giảm MỘT mức từ {result.base_rank} vì: " + "; ".join(result.reasons) + "). "
            "Dù thuộc cả hai trường hợp vẫn chỉ giảm MỘT mức."
        )
    else:
        note = ""
        if result.base_rank in _LOWER:
            note = " (không thuộc trường hợp nào làm giảm hạng)"
        elif result.base_rank:
            note = " (chỉ hạng xuất sắc và giỏi mới bị xét giảm hạng)"
        lines.append(f"- HẠNG CUỐI CÙNG: {result.final_rank}{note}.")
    if not (result.f_known and result.discipline_known) and result.base_rank in _LOWER:
        lines.append(
            "- Nhắc người dùng: hạng xuất sắc/giỏi sẽ giảm một mức nếu F vượt quá 5% hoặc từng bị cảnh cáo cấp Trường; hãy hỏi thêm nếu chưa rõ."
        )
    lines.append("Mở đầu câu trả lời bằng HẠNG CUỐI CÙNG này.")
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------------------------
# Cảnh báo học tập, buộc thôi học (Điều 18)
# ----------------------------------------------------------------------------------------------------------------

YEAR_GPA_THRESHOLDS = {1: 1.2, 2: 1.4, 3: 1.6}  # từ năm thứ tư trở đi: 1,8
LATER_YEARS_THRESHOLD = 1.8
RULE_2C_FROM_COHORT = 47  # tiêu chí 2c chỉ áp dụng từ Khóa 47 trở về sau


@dataclass(frozen=True)
class WarningFacts:
    cohort: int | None = None  # khóa tuyển sinh, ví dụ 48
    semester_gpa: float | None = None  # ĐTBCHK học kỳ đang xét
    is_first_semester: bool | None = None  # học kỳ đầu tiên của khóa học
    registered_credits: float | None = None  # TC đăng ký trong học kỳ
    failed_credits: float | None = None  # TC không đạt trong học kỳ
    owed_credits: float | None = None  # tổng TC nợ đọng từ đầu khóa
    cumulative_gpa: float | None = None  # ĐTBCTL hiện tại
    year_level: int | None = None  # trình độ năm thứ mấy (1, 2, 3, 4 trở đi)
    skipped_registration: bool | None = None  # không đăng ký học trong học kỳ mà không được phép
    previously_warned: bool | None = None  # đã bị cảnh báo học tập ở học kỳ trước


@dataclass(frozen=True)
class Criterion:
    label: str
    status: str  # "vi_pham" | "khong" | "thieu" | "khong_ap_dung"
    detail: str


@dataclass(frozen=True)
class WarningResult:
    criteria: list[Criterion]
    warned: bool
    missing: list[str]
    expelled: bool | None  # theo Điều 18 khoản 5b; None nếu không đủ dữ liệu/không áp dụng
    expulsion_detail: str


def evaluate_warning(facts: WarningFacts) -> WarningResult:
    criteria: list[Criterion] = []

    # (a) ĐTBCHK dưới 0,80 (học kỳ đầu của khóa) hoặc dưới 1,00 (các học kỳ tiếp theo)
    if facts.semester_gpa is None:
        criteria.append(Criterion("ĐTBCHK dưới ngưỡng", "thieu", "chưa có ĐTBCHK"))
    else:
        gpa = facts.semester_gpa
        if facts.is_first_semester is True:
            hit = gpa < 0.80 - _EPS
            criteria.append(Criterion("ĐTBCHK dưới 0,80 (học kỳ đầu của khóa)", "vi_pham" if hit else "khong", f"ĐTBCHK = {_g(gpa)}"))
        elif facts.is_first_semester is False:
            hit = gpa < 1.00 - _EPS
            criteria.append(Criterion("ĐTBCHK dưới 1,00 (các học kỳ tiếp theo)", "vi_pham" if hit else "khong", f"ĐTBCHK = {_g(gpa)}"))
        else:
            if gpa < 0.80 - _EPS:
                criteria.append(Criterion("ĐTBCHK dưới ngưỡng", "vi_pham", f"ĐTBCHK = {_g(gpa)} < 0,80: dưới ngưỡng ở cả học kỳ đầu lẫn các học kỳ sau"))
            elif gpa >= 1.00 - _EPS:
                criteria.append(Criterion("ĐTBCHK dưới ngưỡng", "khong", f"ĐTBCHK = {_g(gpa)} >= 1,00: không dưới ngưỡng nào"))
            else:
                criteria.append(Criterion("ĐTBCHK dưới ngưỡng", "thieu", f"ĐTBCHK = {_g(gpa)} nằm giữa 0,80 và 1,00: phụ thuộc có phải học kỳ đầu của khóa không"))

    # (b) không đăng ký học trong học kỳ mà không được Hiệu trưởng cho phép
    if facts.skipped_registration is True:
        criteria.append(Criterion("Không đăng ký học trong học kỳ mà không được phép", "vi_pham", "có"))
    elif facts.skipped_registration is False:
        criteria.append(Criterion("Không đăng ký học trong học kỳ mà không được phép", "khong", "không"))

    # (c) từ Khóa 47 trở về sau
    if facts.cohort is None:
        criteria.append(Criterion("Các tiêu chí bổ sung từ Khóa 47 trở về sau", "thieu", "chưa biết khóa của sinh viên"))
    elif facts.cohort < RULE_2C_FROM_COHORT:
        criteria.append(
            Criterion(
                "Các tiêu chí bổ sung (TC không đạt > 50%, nợ > 24 TC, ĐTBCTL theo năm)",
                "khong_ap_dung",
                f"chỉ áp dụng từ Khóa {RULE_2C_FROM_COHORT} trở về sau; Khóa {facts.cohort} không áp dụng",
            )
        )
    else:
        if facts.registered_credits is not None and facts.failed_credits is not None and facts.registered_credits > 0:
            share = facts.failed_credits / facts.registered_credits
            hit = facts.failed_credits * 2 > facts.registered_credits + _EPS  # "vượt quá 50%": phải LỚN HƠN 50%
            criteria.append(
                Criterion(
                    "Tổng TC không đạt trong học kỳ vượt quá 50% khối lượng đã đăng ký",
                    "vi_pham" if hit else "khong",
                    f"{_n(facts.failed_credits)}/{_n(facts.registered_credits)} TC = {share * 100:.1f}%".replace(".", ",")
                    + (" (lớn hơn 50%)" if hit else " (không lớn hơn 50%; đúng bằng 50% thì chưa vượt quá)"),
                )
            )
        else:
            criteria.append(Criterion("Tổng TC không đạt trong học kỳ vượt quá 50% khối lượng đã đăng ký", "thieu", "cần số TC đăng ký và số TC không đạt"))
        if facts.owed_credits is not None:
            hit = facts.owed_credits > 24 + _EPS
            criteria.append(
                Criterion(
                    "Tổng TC nợ đọng từ đầu khóa vượt quá 24 TC",
                    "vi_pham" if hit else "khong",
                    f"nợ {_n(facts.owed_credits)} TC" + (" (lớn hơn 24)" if hit else " (không lớn hơn 24; đúng bằng 24 thì chưa vượt quá)"),
                )
            )
        else:
            criteria.append(Criterion("Tổng TC nợ đọng từ đầu khóa vượt quá 24 TC", "thieu", "cần tổng số TC nợ đọng"))
        if facts.cumulative_gpa is not None and facts.year_level is not None:
            level = max(1, facts.year_level)
            limit = YEAR_GPA_THRESHOLDS.get(level, LATER_YEARS_THRESHOLD)
            hit = facts.cumulative_gpa < limit - _EPS
            where = {1: "năm thứ nhất", 2: "năm thứ hai", 3: "năm thứ ba"}.get(level, "các năm tiếp theo (từ năm thứ tư)")
            criteria.append(
                Criterion(
                    f"ĐTBCTL dưới {_g(limit)} ({where})",
                    "vi_pham" if hit else "khong",
                    f"ĐTBCTL = {_g(facts.cumulative_gpa)}",
                )
            )
        else:
            criteria.append(Criterion("ĐTBCTL dưới ngưỡng theo năm học (1,2 / 1,4 / 1,6 / 1,8)", "thieu", "cần ĐTBCTL và trình độ năm học"))

    warned = any(item.status == "vi_pham" for item in criteria)
    missing = [item.label for item in criteria if item.status == "thieu"]

    expelled: bool | None = None
    detail = ""
    if facts.previously_warned is True:
        if facts.semester_gpa is None:
            detail = "đã bị cảnh báo học tập; cần ĐTBCHK của học kỳ kế tiếp để xét buộc thôi học"
        else:
            expelled = facts.semester_gpa < 1.00 - _EPS
            detail = (
                f"đã bị cảnh báo học tập và học kỳ kế tiếp có ĐTBCHK = {_g(facts.semester_gpa)} "
                + ("(dưới 1,00)" if expelled else "(không dưới 1,00; đúng bằng 1,00 thì chưa dưới)")
            )
    return WarningResult(criteria, warned, missing, expelled, detail)


def format_warning(result: WarningResult) -> str:
    lines = ["KẾT QUẢ TÍNH SẴN về CẢNH BÁO HỌC TẬP (Điều 18; đã kiểm tra bằng mã, chính xác): dùng NGUYÊN kết luận này, KHÔNG tự suy luận lại."]
    names = {"vi_pham": "THUỘC (vi phạm)", "khong": "không thuộc", "thieu": "CHƯA KIỂM TRA ĐƯỢC", "khong_ap_dung": "không áp dụng"}
    for item in result.criteria:
        lines.append(f"- {item.label}: {names[item.status]} ({item.detail}).")
    if result.warned:
        lines.append("- KẾT LUẬN: BỊ cảnh báo học tập" + ", vì thuộc: " + "; ".join(i.label for i in result.criteria if i.status == "vi_pham") + ".")
    elif result.missing:
        lines.append(
            "- KẾT LUẬN: theo các tiêu chí đã có số liệu thì KHÔNG bị cảnh báo học tập; nhưng chưa kiểm tra được: "
            + "; ".join(result.missing)
            + ". Nói rõ điều này và hỏi thêm số liệu nếu cần."
        )
    else:
        lines.append("- KẾT LUẬN: KHÔNG bị cảnh báo học tập (không thuộc tiêu chí nào).")
    if result.expulsion_detail:
        verdict = "BỊ BUỘC THÔI HỌC (Điều 18 khoản 5b; trường hợp đặc biệt do Hiệu trưởng quyết định)" if result.expelled else "KHÔNG bị buộc thôi học theo khoản 5b"
        lines.append(f"- Buộc thôi học: {result.expulsion_detail} -> {verdict}." if result.expelled is not None else f"- Buộc thôi học: {result.expulsion_detail}.")
    lines.append("Mở đầu câu trả lời bằng KẾT LUẬN này.")
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------------------------
# Học bổng khuyến khích học tập (Điều 9)
# ----------------------------------------------------------------------------------------------------------------

# (tên mức, ĐTBCHK tối thiểu, ĐRL tối thiểu). Người xếp mức cao nhất mà đạt CẢ HAI tiêu chí.
SCHOLARSHIP_LEVELS: list[tuple[str, float, float]] = [
    ("xuất sắc", 3.60, 90),
    ("giỏi", 3.20, 80),
    ("khá", 2.50, 65),
]


@dataclass(frozen=True)
class Student:
    name: str
    gpa: float  # ĐTBCHK của học kỳ trước
    conduct: float  # ĐRL của học kỳ trước (thang 100)
    registered_credits: float | None = None  # TC đã đăng ký ở học kỳ trước
    credits_arranged_by_school: bool | None = None  # TC ít do Trường bố trí
    has_f: bool | None = None  # có học phần dưới điểm D (điểm F)
    school_discipline: bool | None = None  # bị kỷ luật từ khiển trách cấp Trường trở lên


@dataclass(frozen=True)
class StudentResult:
    student: Student
    level: str | None
    level_index: int  # 0 = xuất sắc, 1 = giỏi, 2 = khá, 3 = không đủ mức
    eligible: bool
    problems: list[str]


def evaluate_student(student: Student) -> StudentResult:
    problems: list[str] = []
    if student.registered_credits is not None and student.registered_credits < 12 and not student.credits_arranged_by_school:
        problems.append(f"chỉ đăng ký {_n(student.registered_credits)} TC, chưa đủ tối thiểu 12 TC (trừ trường hợp do Trường bố trí)")
    if student.has_f:
        problems.append("có học phần dưới điểm D (điểm F)")
    if student.school_discipline:
        problems.append("bị kỷ luật từ khiển trách cấp Trường trở lên")

    level = None
    index = len(SCHOLARSHIP_LEVELS)
    for i, (name, min_gpa, min_conduct) in enumerate(SCHOLARSHIP_LEVELS):
        if student.gpa >= min_gpa - _EPS and student.conduct >= min_conduct - _EPS:
            level, index = name, i
            break
    if level is None:
        problems.append("chưa đạt tiêu chuẩn của mức học bổng nào (cần ĐTBCHK và ĐRL từ loại khá trở lên)")
    return StudentResult(student, level, index, not problems, problems)


def rank_scholarship(students: list[Student]) -> list[StudentResult]:
    """Xếp thứ tự ưu tiên: mức (cao -> thấp), rồi ĐTBCHK, rồi ĐRL. Người không đủ điều kiện xếp cuối."""
    results = [evaluate_student(s) for s in students]
    return sorted(results, key=lambda r: (not r.eligible, r.level_index, -r.student.gpa, -r.student.conduct))


def format_scholarship(results: list[StudentResult]) -> str:
    lines = [
        "KẾT QUẢ TÍNH SẴN về XÉT HỌC BỔNG (Điều 9; đã kiểm tra bằng mã, chính xác): dùng NGUYÊN kết luận này, KHÔNG tự suy luận lại.",
        "- Quy trình: (1) xác định MỨC của từng người (phải đạt CẢ ĐTBCHK lẫn ĐRL); (2) cấp từ mức cao xuống thấp; (3) chỉ khi CÙNG MỨC mới so ĐTBCHK, rồi ĐRL.",
        "- Mức: xuất sắc = ĐTBCHK từ 3,60 và ĐRL từ 90; giỏi = ĐTBCHK từ 3,20 và ĐRL từ 80 (loại tốt trở lên); khá = ĐTBCHK từ 2,50 và ĐRL từ 65 (loại khá trở lên).",
    ]
    for r in results:
        s = r.student
        band = conduct_rank(s.conduct)
        label = f"{s.name}: ĐTBCHK {_g(s.gpa)} ({rank_of(s.gpa) or 'dưới 2,00'}), ĐRL {_n(s.conduct)} (loại {band})"
        if r.level:
            label += f" -> đạt MỨC {r.level.upper()}"
        if r.problems:
            label += "; KHÔNG ĐỦ ĐIỀU KIỆN XÉT: " + "; ".join(r.problems)
        lines.append(f"- {label}.")
    ordered = [r for r in results if r.eligible]
    if len(results) > 1 and ordered:
        order = []
        for i, r in enumerate(ordered):
            tie = (
                i > 0
                and ordered[i - 1].level_index == r.level_index
                and abs(ordered[i - 1].student.gpa - r.student.gpa) < _EPS
                and abs(ordered[i - 1].student.conduct - r.student.conduct) < _EPS
            )
            order.append(f"{r.student.name}{' (ngang hạng với người liền trước)' if tie else ''}")
        lines.append("- THỨ TỰ ƯU TIÊN XÉT HỌC BỔNG (từ trước đến sau): " + " > ".join(order) + ".")
        lines.append("Mở đầu câu trả lời bằng thứ tự này (người đứng đầu danh sách được xét trước). Giải thích ngắn gọn vì sao (mức, rồi ĐTBCHK, rồi ĐRL).")
    elif ordered:
        lines.append("Mở đầu câu trả lời bằng kết luận về mức học bổng của người này.")
    else:
        lines.append("Mở đầu câu trả lời bằng việc nói không ai đủ điều kiện, kèm lý do.")
    lines.append("Mức học bổng bằng tiền và chỉ tiêu do Hiệu trưởng quyết định (Điều 9 khoản 1e); nhắc đối chiếu thông báo của Trường.")
    return "\n".join(lines)
