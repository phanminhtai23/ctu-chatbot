"""Tính ĐTBCTL, hạng tốt nghiệp và khả năng đạt mục tiêu bằng số học chính xác (không giao cho LLM).

Căn cứ QĐ 3266/QĐ-ĐHCT:
- Điều 24 khoản 4: ĐTBCTL là trung bình có trọng số (số TC) của các học phần đã tích lũy, KHÔNG gồm học phần F và
  học phần điều kiện.
- Điều 7 khoản 6: học phần điều kiện gồm GDQP&AN, GDTC, Ngoại ngữ căn bản, Tin học căn bản.
- Điều 34: hạng tốt nghiệp theo ĐTBCTL (xuất sắc 3,60-4,00; giỏi 3,20-3,59; khá 2,50-3,19; trung bình 2,00-2,49).
"""

from dataclasses import dataclass

MAX_POINT = 4.0
RANKS: list[tuple[str, float]] = [("xuất sắc", 3.60), ("giỏi", 3.20), ("khá", 2.50), ("trung bình", 2.00)]
_EPS = 1e-9


def rank_of(gpa: float) -> str | None:
    """Hạng ứng với một ĐTBCTL (làm tròn 2 chữ số như bảng ở Điều 34); None nếu dưới 2,00."""
    value = round(gpa + _EPS, 2)
    for name, threshold in RANKS:
        if value >= threshold:
            return name
    return None


def threshold_of(rank: str) -> float | None:
    rank = rank.strip().lower()
    return next((t for name, t in RANKS if name == rank), None)


@dataclass(frozen=True)
class GpaFacts:
    total_credits: float  # tổng TC của chương trình
    done_credits: float  # TC đã học/đã tích lũy
    current_gpa: float  # ĐTBCTL hiện tại (thang 4)
    target_gpa: float | None = None
    target_rank: str | None = None
    excluded_done: float | None = None  # TC đã học KHÔNG tính vào ĐTBCTL (học phần điều kiện, điểm M...); None = chưa biết
    excluded_total: float | None = None  # tổng TC học phần điều kiện của cả chương trình; None = chưa biết

    @property
    def assumed_all_counted(self) -> bool:
        """Người dùng chưa cho biết số TC không tính điểm -> mặc định mọi TC đều được tính."""
        return not self.excluded_done and not self.excluded_total


@dataclass(frozen=True)
class RankPlan:
    rank: str
    threshold: float
    needed_average: float | None  # điểm trung bình cần đạt ở phần còn lại; None nếu không còn TC nào
    achievable: bool


@dataclass(frozen=True)
class GpaAnalysis:
    counted_done: float  # C
    counted_total: float  # T
    remaining: float  # T - C
    points_now: float  # C x ĐTBCTL hiện tại
    max_gpa: float  # nếu phần còn lại toàn A (4,0)
    current_rank: str | None
    max_rank: str | None
    plans: list[RankPlan]
    target: RankPlan | None  # kế hoạch cho mục tiêu người dùng nêu (nếu có)
    target_label: str | None


def analyze(facts: GpaFacts) -> GpaAnalysis | None:
    """Trả về None nếu số liệu vô lý (âm, vượt quá tổng, ĐTBCTL ngoài 0-4...)."""
    excluded_done = facts.excluded_done or 0.0
    excluded_total = facts.excluded_total or 0.0
    counted_total = facts.total_credits - excluded_total
    counted_done = facts.done_credits - excluded_done
    values = (facts.total_credits, facts.done_credits, facts.current_gpa, excluded_done, excluded_total)
    if any(v < 0 for v in values):
        return None
    if not (0 <= facts.current_gpa <= MAX_POINT):
        return None
    if counted_total <= 0 or counted_done < 0 or counted_done > counted_total + _EPS:
        return None
    if excluded_done > excluded_total + _EPS and facts.excluded_total is not None:
        return None  # đã học nhiều TC điều kiện hơn tổng TC điều kiện của chương trình

    remaining = max(0.0, counted_total - counted_done)
    points_now = counted_done * facts.current_gpa
    max_gpa = (points_now + MAX_POINT * remaining) / counted_total

    def plan(name: str, threshold: float) -> RankPlan:
        if remaining <= _EPS:
            achievable = round(facts.current_gpa + _EPS, 2) >= threshold
            return RankPlan(name, threshold, None, achievable)
        needed = (threshold * counted_total - points_now) / remaining
        return RankPlan(name, threshold, max(needed, 0.0), round(max_gpa + _EPS, 2) >= threshold)

    plans = [plan(name, threshold) for name, threshold in RANKS]

    target = None
    label = None
    if facts.target_gpa is not None:
        target = plan(f"mục tiêu {facts.target_gpa:.2f}".replace(".", ","), facts.target_gpa)
        label = rank_of(facts.target_gpa)
    elif facts.target_rank:
        threshold = threshold_of(facts.target_rank)
        if threshold is not None:
            target = plan(facts.target_rank.strip().lower(), threshold)
            label = facts.target_rank.strip().lower()

    return GpaAnalysis(
        counted_done=counted_done,
        counted_total=counted_total,
        remaining=remaining,
        points_now=points_now,
        max_gpa=max_gpa,
        current_rank=rank_of(facts.current_gpa),
        max_rank=rank_of(max_gpa),
        plans=plans,
        target=target,
        target_label=label,
    )


def _n(value: float) -> str:
    """Số kiểu Việt Nam: dấu phẩy thập phân, bỏ phần thập phân nếu là số nguyên."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _g(value: float) -> str:
    """Điểm trung bình luôn hiện 2 chữ số thập phân (3,60 chứ không phải 3,6), dấu phẩy kiểu Việt Nam."""
    return f"{value:.2f}".replace(".", ",")


def format_report(facts: GpaFacts, result: GpaAnalysis) -> str:
    """Khối văn bản đưa vào prompt: các con số đã tính sẵn để LLM chỉ việc diễn giải."""
    lines = [
        "KẾT QUẢ TÍNH SẴN (đã tính bằng máy tính, chính xác): dùng NGUYÊN các con số và kết luận này, KHÔNG tự tính lại.",
        f"- C (TC đã học được tính điểm) = {_n(result.counted_done)}; T (tổng TC chương trình được tính điểm) = {_n(result.counted_total)};"
        f" còn lại = {_n(result.remaining)} TC.",
    ]
    if facts.assumed_all_counted:
        lines.append(
            "- GIẢ ĐỊNH: người dùng chưa cho biết số TC không tính điểm, nên coi mọi TC đều được tính vào ĐTBCTL. "
            "Hãy nói rõ giả định này và hỏi hai số: TC học phần điều kiện/điểm M trong phần đã học, và tổng TC học phần điều kiện của chương trình."
        )
    else:
        lines.append(
            f"- Đã loại học phần điều kiện/điểm M: {_n(facts.excluded_done or 0)} TC trong phần đã học, "
            f"{_n(facts.excluded_total or 0)} TC trong cả chương trình."
        )
    lines.append(f"- ĐTBCTL hiện tại = {_g(facts.current_gpa)} (hạng hiện tại: {result.current_rank or 'chưa đạt hạng trung bình'}).")
    lines.append(f"- Tổng điểm hệ 4 hiện có = {_n(result.counted_done)} x {_g(facts.current_gpa)} = {_n(result.points_now)}.")
    if result.remaining > _EPS:
        lines.append(
            f"- Nếu {_n(result.remaining)} TC còn lại đều đạt A (4,0): ĐTBCTL TỐI ĐA = "
            f"({_n(result.points_now)} + {_n(result.remaining)} x 4,0) / {_n(result.counted_total)} = {_g(result.max_gpa)}"
            + f" (hạng tối đa: {result.max_rank or 'chưa đạt hạng trung bình'})."
        )
    else:
        lines.append("- Đã học hết số TC được tính điểm: ĐTBCTL hiện tại cũng là kết quả cuối cùng.")
    lines.append("- Điểm trung bình cần đạt ở phần còn lại để đạt từng hạng:")
    for item in result.plans:
        if item.needed_average is None:
            verdict = "ĐẠT" if item.achievable else "KHÔNG đạt"
            lines.append(f"  + loại {item.rank} (từ {_g(item.threshold)}): {verdict}")
            continue
        verdict = "CÓ THỂ" if item.achievable else "KHÔNG THỂ"
        needed = _g(item.needed_average)
        if item.needed_average <= _EPS:
            note = "đã chắc chắn đạt, kể cả khi điểm phần còn lại thấp"
        elif item.needed_average <= MAX_POINT + _EPS:
            note = f"cần điểm trung bình {needed}/4,00 ở phần còn lại"
        else:
            note = f"cần điểm trung bình {needed}, vượt mức tối đa 4,00"
        lines.append(f"  + loại {item.rank} (từ {_g(item.threshold)}): {verdict} ({note})")
    if result.target is not None:
        tgt = result.target
        verdict = "CÓ THỂ" if tgt.achievable else "KHÔNG THỂ"
        lines.append(
            f"- ĐIỀU NGƯỜI DÙNG HỎI ({tgt.rank}, ngưỡng {_g(tgt.threshold)}): kết luận = {verdict}. "
            "Mở đầu câu trả lời bằng kết luận này kèm con số ĐTBCTL tối đa."
        )
        if not tgt.achievable:
            lines.append(
                "- Khi KHÔNG THỂ: cách duy nhất là học cải thiện điểm (điểm cũ được thay bằng điểm cao nhất, Điều 17 và 24); "
                "mỗi TC nâng từ C (2,0) lên A (4,0) thêm 2,0 điểm vào tổng điểm hệ 4."
            )
    return "\n".join(lines)
