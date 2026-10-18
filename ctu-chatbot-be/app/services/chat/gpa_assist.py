"""Hỗ trợ tính điểm và kiểm tra quy định: trích số liệu từ cuộc trò chuyện, tính bằng Python, đưa kết quả vào prompt.

LLM nhỏ hay chia sai (524/151 thành 3,33; 13/6 thành 2,33), so sánh sai (3,60 >= 3,60), sai ở mốc "đúng bằng ngưỡng"
(8/16 TC là 50% chứ không "vượt quá 50%") và viết kết luận ở câu đầu trước khi áp dụng hết các bước. Vì vậy các phép
tính và luật có ngưỡng được làm bằng mã (`grades`, `grades_courses`, `rules`) và LLM chỉ diễn giải kết quả.

Bước trích số liệu tốn thêm MỘT lần gọi LLM nên chỉ chạy khi tin nhắn có vẻ nói về điểm/tín chỉ/quy định có ngưỡng
kèm con số.
"""

import json
import logging
import re
from collections.abc import Iterator
from typing import Protocol

from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage, SystemMessage

from app.services.chat.text import message_text
from app.services.grades import GpaFacts, analyze, format_report
from app.services.grades_courses import Course, format_courses_report, make_course
from app.services.rules import (
    GraduationFacts,
    Student,
    WarningFacts,
    evaluate_graduation,
    evaluate_warning,
    format_graduation,
    format_scholarship,
    format_warning,
    rank_scholarship,
)

logger = logging.getLogger("app.chat")

# Từ khoá về điểm/tín chỉ: cần ít nhất HAI con số mới đáng trích (ví dụ tổng TC và ĐTBCTL).
_KEYWORDS = re.compile(
    r"đtbctl|đtbchk|đtbcnh|điểm\s*(tb|trung bình)|trung bình chung|tích lũy|tín chỉ|\btc\b|\bchỉ\b|xuất sắc|giỏi|tốt nghiệp",
    re.IGNORECASE,
)
# Từ khoá về quy định có ngưỡng (cảnh báo, học bổng, hạng tốt nghiệp...): một con số là đủ.
_RULE_KEYWORDS = re.compile(
    r"cảnh báo|học bổng|buộc thôi|khiển trách|kỷ luật|rèn luyện|\bđrl\b|\bgpa\b|điểm f|\bf\b|rớt|nợ|hạng tốt nghiệp|tốt nghiệp loại|giảm một mức|đạt loại",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_ARTICLE_REF = re.compile(r"(?:điều|khoản|điểm)\s+\d+\w?", re.IGNORECASE)
_TRANSCRIPT_MESSAGES = 6

EXTRACT_PROMPT = """Bạn là bộ trích xuất số liệu. Đọc cuộc trò chuyện giữa sinh viên và chatbot rồi trả về DUY NHẤT một đối tượng JSON (không giải thích, không markdown) với các khoá dưới đây. Chưa nói thì để null (hoặc [] với danh sách); KHÔNG bịa số liệu.

A. Khả năng đạt mục tiêu điểm:
- "total_credits": tổng số tín chỉ của chương trình đào tạo (số), hoặc null
- "done_credits": số tín chỉ sinh viên đã học/đã tích lũy (số), hoặc null
- "current_gpa": điểm trung bình chung tích lũy hiện tại, thang 4 (số), hoặc null
- "target_gpa": mức điểm mục tiêu thang 4 nếu sinh viên nêu bằng số (số), hoặc null
- "target_rank": hạng tốt nghiệp mục tiêu, một trong "xuất sắc", "giỏi", "khá", "trung bình", hoặc null
- "excluded_done": số tín chỉ TRONG PHẦN ĐÃ HỌC mà sinh viên nói là học phần điều kiện/điểm M/không tính vào điểm trung bình (số), hoặc null nếu chưa nói
- "excluded_total": tổng số tín chỉ học phần điều kiện của CẢ chương trình nếu sinh viên nói (số), hoặc null nếu chưa nói
- "courses": danh sách các học phần cụ thể sinh viên liệt kê để tính điểm trung bình (mảng, [] nếu không có). Mỗi phần tử: {"name": tên hoặc null, "credits": số tín chỉ, "letter": điểm chữ "A","B+","B","C+","C","D+","D","F","M","I","W" hoặc null, "score10": điểm thang 10 hoặc null, "is_condition": true nếu là học phần điều kiện (GDQP&AN, GDTC, Ngoại ngữ căn bản, Tin học căn bản), "is_gdtc": true nếu là Giáo dục thể chất}

B. "graduation": đối tượng hoặc null. CHỈ khi câu hỏi về HẠNG TỐT NGHIỆP / tốt nghiệp loại gì / bị giảm hạng. Khoá: "gpa" (ĐTBCTL toàn khóa), "total_credits" (tổng TC quy định của chương trình), "f_credits" (tổng TC học phần bị điểm F, KHÔNG tính F của học phần đăng ký học CẢI THIỆN), "improvement_f_credits" (TC F của học phần học cải thiện), "severe_discipline" (true nếu từng bị kỷ luật từ mức cảnh cáo cấp Trường trở lên, gồm đình chỉ và buộc thôi học; false nếu nói rõ chưa bị kỷ luật hoặc chỉ bị khiển trách; null nếu không nói).

C. "warning": đối tượng hoặc null. CHỈ khi câu hỏi về CẢNH BÁO HỌC TẬP / BUỘC THÔI HỌC. Khoá: "cohort" (số khóa, "K48" là 48), "semester_gpa" (ĐTBCHK học kỳ đang nói), "is_first_semester" (true nếu là học kỳ ĐẦU TIÊN của khóa học), "registered_credits" (TC đăng ký trong học kỳ), "failed_credits" (TC rớt/không đạt trong học kỳ), "owed_credits" (tổng TC nợ đọng từ đầu khóa), "cumulative_gpa" (ĐTBCTL), "year_level" (1, 2, 3 hoặc 4 nếu là năm thứ mấy), "skipped_registration" (true nếu không đăng ký học trong học kỳ mà không được phép), "previously_warned" (true nếu đã bị cảnh báo học tập ở học kỳ trước).

D. "scholarship": danh sách hoặc []. CHỈ khi câu hỏi về HỌC BỔNG khuyến khích học tập; mỗi sinh viên một phần tử: {"name": tên (A, B, "bạn thứ nhất"...; không có thì "Người 1", "Người 2"...), "gpa": ĐTBCHK thang 4, "conduct": điểm rèn luyện thang 100, "registered_credits": TC đã đăng ký ở học kỳ trước hoặc null, "credits_arranged_by_school": true nếu số TC ít là do Trường bố trí, "has_f": true nếu có học phần điểm F/dưới điểm D, "school_discipline": true nếu bị kỷ luật từ khiển trách cấp Trường trở lên}. Chỉ điền gpa và conduct khi sinh viên nêu cả hai.

Chấp nhận cách viết đời thường: "151 chỉ" là 151 tín chỉ, "điểm tb 3.2" hay "3,2" là 3.2, "gpa 3,8 đrl 89" là gpa 3.8 và conduct 89. Số thập phân dùng dấu chấm. Lấy số liệu MỚI NHẤT nếu sinh viên đã điều chỉnh."""


class ChatModel(Protocol):
    def stream(self, messages: list[BaseMessage]) -> Iterator[AIMessageChunk]: ...


def looks_like_gpa_question(history: list[BaseMessage]) -> bool:
    """Rẻ và bảo thủ: có từ khoá và đủ con số trong các tin người dùng gần nhất."""
    recent = " ".join(message_text(m) for m in history if isinstance(m, HumanMessage))[-1500:]
    # "Điều 14" không phải số liệu điểm.
    numbers = _NUMBER.findall(_ARTICLE_REF.sub(" ", recent))
    if _RULE_KEYWORDS.search(recent) and len(numbers) >= 1:
        return True
    return bool(_KEYWORDS.search(recent)) and len(numbers) >= 2


def _number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _flag(value) -> bool | None:
    return value if isinstance(value, bool) else None


def _load_json(raw: str) -> dict | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def parse_facts(raw: str) -> GpaFacts | None:
    data = _load_json(raw)
    if data is None:
        return None
    total, done, gpa = (_number(data.get(k)) for k in ("total_credits", "done_credits", "current_gpa"))
    if total is None or done is None or gpa is None:
        return None  # thiếu số liệu cốt lõi: để LLM hỏi lại người dùng
    rank = data.get("target_rank")
    return GpaFacts(
        total_credits=total,
        done_credits=done,
        current_gpa=gpa,
        target_gpa=_number(data.get("target_gpa")),
        target_rank=rank.strip().lower() if isinstance(rank, str) and rank.strip() else None,
        excluded_done=_number(data.get("excluded_done")),
        excluded_total=_number(data.get("excluded_total")),
    )


def parse_courses(raw: str) -> list[Course]:
    """Danh sách học phần hợp lệ; rỗng nếu thiếu hoặc có phần tử sai (không tính bừa một phần)."""
    data = _load_json(raw)
    items = data.get("courses") if data else None
    if not isinstance(items, list) or not items:
        return []
    courses: list[Course] = []
    for item in items:
        if not isinstance(item, dict):
            return []
        course = make_course(
            credits=_number(item.get("credits")),
            letter=item.get("letter"),
            score10=_number(item.get("score10")),
            name=str(item.get("name") or ""),
            is_condition=bool(item.get("is_condition")),
            is_gdtc=bool(item.get("is_gdtc")),
        )
        if course is None:
            return []
        courses.append(course)
    return courses


def parse_graduation(raw: str) -> GraduationFacts | None:
    data = _load_json(raw)
    block = data.get("graduation") if data else None
    if not isinstance(block, dict):
        return None
    gpa = _number(block.get("gpa"))
    if gpa is None:
        return None
    return GraduationFacts(
        gpa=gpa,
        total_credits=_number(block.get("total_credits")),
        f_credits=_number(block.get("f_credits")),
        severe_discipline=_flag(block.get("severe_discipline")),
    )


def parse_warning(raw: str) -> WarningFacts | None:
    data = _load_json(raw)
    block = data.get("warning") if data else None
    if not isinstance(block, dict):
        return None
    cohort = _number(block.get("cohort"))
    year = _number(block.get("year_level"))
    facts = WarningFacts(
        cohort=int(cohort) if cohort is not None else None,
        semester_gpa=_number(block.get("semester_gpa")),
        is_first_semester=_flag(block.get("is_first_semester")),
        registered_credits=_number(block.get("registered_credits")),
        failed_credits=_number(block.get("failed_credits")),
        owed_credits=_number(block.get("owed_credits")),
        cumulative_gpa=_number(block.get("cumulative_gpa")),
        year_level=int(year) if year is not None else None,
        skipped_registration=_flag(block.get("skipped_registration")),
        previously_warned=_flag(block.get("previously_warned")),
    )
    has_data = any(
        getattr(facts, name) is not None
        for name in ("semester_gpa", "failed_credits", "owed_credits", "cumulative_gpa", "skipped_registration", "previously_warned")
    )
    return facts if has_data else None


def parse_students(raw: str) -> list[Student]:
    data = _load_json(raw)
    items = data.get("scholarship") if data else None
    if not isinstance(items, list):
        return []
    students: list[Student] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        gpa, conduct = _number(item.get("gpa")), _number(item.get("conduct"))
        if gpa is None or conduct is None:
            continue
        students.append(
            Student(
                name=str(item.get("name") or f"Người {index}"),
                gpa=gpa,
                conduct=conduct,
                registered_credits=_number(item.get("registered_credits")),
                credits_arranged_by_school=_flag(item.get("credits_arranged_by_school")),
                has_f=_flag(item.get("has_f")),
                school_discipline=_flag(item.get("school_discipline")),
            )
        )
    return students


def build_report_from_extraction(raw: str) -> str:
    """Ghép các khối "KẾT QUẢ TÍNH SẴN" từ phản hồi trích số liệu (rỗng nếu không có gì áp dụng được)."""
    blocks: list[str] = []

    courses = parse_courses(raw)
    if courses:
        blocks.append(format_courses_report(courses))

    facts = parse_facts(raw)
    if facts is not None:
        result = analyze(facts)
        if result is not None:
            blocks.append(format_report(facts, result))

    graduation = parse_graduation(raw)
    if graduation is not None:
        outcome = evaluate_graduation(graduation)
        if outcome is not None:
            blocks.append(format_graduation(graduation, outcome))

    warning = parse_warning(raw)
    if warning is not None:
        blocks.append(format_warning(evaluate_warning(warning)))

    students = parse_students(raw)
    if students:
        blocks.append(format_scholarship(rank_scholarship(students)))

    return "\n\n".join(blocks)


def build_gpa_report(llm: ChatModel, history: list[BaseMessage]) -> str:
    """Khối kết quả tính sẵn cho prompt, hoặc chuỗi rỗng nếu không áp dụng/không đủ số liệu."""
    if not looks_like_gpa_question(history):
        return ""
    transcript = "\n".join(
        f"{'Sinh viên' if isinstance(m, HumanMessage) else 'Chatbot'}: {message_text(m)}"
        for m in history[-_TRANSCRIPT_MESSAGES:]
    )
    try:
        raw = "".join(
            message_text(chunk)
            for chunk in llm.stream([SystemMessage(content=EXTRACT_PROMPT), HumanMessage(content=transcript)])
        )
    except Exception:  # noqa: BLE001 - lỗi bước phụ không được làm hỏng câu trả lời chính
        logger.exception("Không trích được số liệu điểm; bot sẽ tự trả lời không có kết quả tính sẵn")
        return ""
    try:
        return build_report_from_extraction(raw)
    except Exception:  # noqa: BLE001 - số liệu trích sai kiểu không được làm hỏng cả lượt chat
        logger.exception("Không dựng được kết quả tính sẵn từ số liệu đã trích")
        return ""
