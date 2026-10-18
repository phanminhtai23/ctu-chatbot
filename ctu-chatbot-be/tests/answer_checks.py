"""Kiểm tra một câu trả lời của bot theo `Case` (dùng chung cho test live và kiểm tra cache câu hỏi gợi ý)."""

import re

from tests.rag_cases import Case

EMOJI = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf\u2b50\u2728]")
LATEX = re.compile(r"\$\$|\\frac|\\sum|\\times|\\cdot|\\text|\\begin|\\\(|\\\[")


def normalize(text: str) -> str:
    text = text.lower().replace("\u00a0", " ")
    return re.sub(r"[*_`]", "", text)


def friendly_problems(answer: str) -> list[str]:
    problems = []
    if LATEX.search(answer):
        problems.append("còn ký hiệu LaTeX trong câu trả lời")
    if not re.search(r"\bbạn\b|\bmình\b", answer.lower()):
        problems.append("giọng chưa thân thiện (không xưng mình/bạn)")
    if len(answer) >= 2500:
        problems.append("trả lời quá dài, khó đọc")
    return problems


def case_problems(case: Case, answer: str) -> list[str]:
    """Danh sách lỗi của câu trả lời so với kỳ vọng của `case` (rỗng nếu đạt)."""
    text = normalize(answer)
    problems = []
    if case.lead and not re.search(case.lead, text[:260], flags=re.IGNORECASE):
        problems.append(f"chưa mở đầu bằng kết luận rõ ràng ({case.lead!r})")
    for group in case.must:
        if not any(re.search(p, text, flags=re.IGNORECASE) for p in group):
            problems.append(f"thiếu một trong {group}")
    for pattern in case.forbid:
        if re.search(pattern, text, flags=re.IGNORECASE):
            problems.append(f"có nội dung không được phép {pattern!r}")
    return problems


def assert_friendly(answer: str) -> None:
    problems = friendly_problems(answer)
    assert not problems, f"{'; '.join(problems)}:\n{answer}"


def assert_case(case: Case, answer: str) -> None:
    problems = case_problems(case, answer)
    assert not problems, f"[{case.id}] {'; '.join(problems)}\n--- câu hỏi: {case.question}\n--- trả lời:\n{answer}"
