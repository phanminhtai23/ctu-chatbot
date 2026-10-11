"""Hỗ trợ tính điểm: trích số liệu từ cuộc trò chuyện, tính bằng Python, đưa kết quả vào prompt.

LLM nhỏ hay chia sai (524/151 thành 3,33; 13/6 thành 2,33) hoặc so sánh sai (3,60 >= 3,60). Vì vậy phép tính
được làm bằng mã (`app.services.grades`, `app.services.grades_courses`) và LLM chỉ diễn giải. Bước trích số liệu
tốn thêm một lần gọi LLM nên chỉ chạy khi tin nhắn có vẻ nói về điểm/tín chỉ kèm ít nhất hai con số.
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

logger = logging.getLogger("app.chat")

_KEYWORDS = re.compile(
    r"đtbctl|đtbchk|đtbcnh|điểm\s*(tb|trung bình)|trung bình chung|tích lũy|tín chỉ|\btc\b|\bchỉ\b|xuất sắc|giỏi|tốt nghiệp",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_ARTICLE_REF = re.compile(r"(?:điều|khoản|điểm)\s+\d+\w?", re.IGNORECASE)
_TRANSCRIPT_MESSAGES = 6

EXTRACT_PROMPT = """Bạn là bộ trích xuất số liệu. Đọc cuộc trò chuyện giữa sinh viên và chatbot rồi trả về DUY NHẤT một đối tượng JSON (không giải thích, không markdown) với các khoá:
- "total_credits": tổng số tín chỉ của chương trình đào tạo (số), hoặc null
- "done_credits": số tín chỉ sinh viên đã học/đã tích lũy (số), hoặc null
- "current_gpa": điểm trung bình chung tích lũy hiện tại, thang 4 (số), hoặc null
- "target_gpa": mức điểm mục tiêu thang 4 nếu sinh viên nêu bằng số (số), hoặc null
- "target_rank": hạng tốt nghiệp mục tiêu, một trong "xuất sắc", "giỏi", "khá", "trung bình", hoặc null
- "excluded_done": số tín chỉ TRONG PHẦN ĐÃ HỌC mà sinh viên nói là học phần điều kiện/điểm M/không tính vào điểm trung bình (số), hoặc null nếu chưa nói
- "excluded_total": tổng số tín chỉ học phần điều kiện của CẢ chương trình nếu sinh viên nói (số), hoặc null nếu chưa nói
- "courses": danh sách các học phần cụ thể mà sinh viên liệt kê để tính điểm trung bình (mảng, rỗng [] nếu không có). Mỗi phần tử: {"name": tên hoặc null, "credits": số tín chỉ, "letter": điểm chữ "A","B+","B","C+","C","D+","D","F","M","I","W" hoặc null, "score10": điểm thang 10 hoặc null, "is_condition": true nếu là học phần điều kiện (GDQP&AN, GDTC, Ngoại ngữ căn bản, Tin học căn bản), "is_gdtc": true nếu là Giáo dục thể chất}
Chấp nhận cách viết đời thường: "151 chỉ" là 151 tín chỉ, "điểm tb 3.2" hay "3,2" là 3.2, "môn X 3 tín chỉ được B+" là {"credits":3,"letter":"B+"}. Số thập phân dùng dấu chấm. Lấy số liệu MỚI NHẤT nếu sinh viên đã điều chỉnh. Không bịa: chưa nói thì null."""


class ChatModel(Protocol):
    def stream(self, messages: list[BaseMessage]) -> Iterator[AIMessageChunk]: ...


def looks_like_gpa_question(history: list[BaseMessage]) -> bool:
    """Rẻ và bảo thủ: có từ khoá về điểm/tín chỉ VÀ có ít nhất hai con số trong các tin người dùng gần nhất."""
    recent = " ".join(message_text(m) for m in history if isinstance(m, HumanMessage))[-1500:]
    if not _KEYWORDS.search(recent):
        return False
    # "Điều 14" không phải số liệu điểm. Cần ít nhất hai số (ví dụ tổng TC và ĐTBCTL) mới đáng để tính.
    numbers = _NUMBER.findall(_ARTICLE_REF.sub(" ", recent))
    return len(numbers) >= 2


def _number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


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


def build_gpa_report(llm: ChatModel, history: list[BaseMessage]) -> str:
    """Khối "KẾT QUẢ TÍNH SẴN" cho prompt, hoặc chuỗi rỗng nếu không áp dụng/không đủ số liệu."""
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

    blocks: list[str] = []
    courses = parse_courses(raw)
    if courses:
        blocks.append(format_courses_report(courses))
    facts = parse_facts(raw)
    if facts is not None:
        result = analyze(facts)
        if result is not None:
            blocks.append(format_report(facts, result))
    return "\n\n".join(blocks)
