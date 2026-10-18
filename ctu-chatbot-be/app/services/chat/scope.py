"""Guardrail phạm vi: câu hỏi này thuộc văn bản quy chế (RAG) hay phải tìm web, hay không liên quan?

Bốn tuyến (route):
- smalltalk: chào hỏi, cảm ơn, hỏi bot là ai -> trả lời ngắn, không cần tra cứu.
- regulation: thuộc QĐ 3266 -> RAG như cũ.
- external: về Trường/việc học nhưng ngoài quy chế (học phí, lịch thi, ký túc xá...) -> bật công cụ `web_search`.
- offtopic: không liên quan học vụ -> từ chối lịch sự, không tìm web.

Điểm giống nhất (cosine) của lần tra cứu RAG đã đo: câu thuộc quy chế 0,68-0,83; câu ngoài quy chế nhưng về CTU
0,62-0,74; câu không liên quan 0,52-0,59. Hai nhóm đầu chồng lên nhau nên chỉ dùng điểm cho các vùng rõ ràng,
vùng giữa nhờ một lần gọi LLM phân loại. Mọi lỗi đều quay về `regulation` (hành vi cũ, an toàn).
"""

import logging
import re
from collections.abc import Iterator
from typing import Protocol

from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage, SystemMessage

from app.services.chat.text import message_text

logger = logging.getLogger("app.chat")

REGULATION, EXTERNAL, OFFTOPIC, SMALLTALK = "regulation", "external", "offtopic", "smalltalk"
ROUTES = (REGULATION, EXTERNAL, OFFTOPIC, SMALLTALK)

HIGH_SCORE = 0.75  # từ đây trở lên chắc chắn thuộc quy chế, khỏi gọi LLM phân loại
_ARTICLE_MENTION = re.compile(r"điều\s+\d{1,2}\b", re.IGNORECASE)
_SMALLTALK = re.compile(
    r"^\s*(hi|hello|hey|alo|chào|xin chào|chào bạn|cảm ơn|cám ơn|thanks|thank you|ok|oke|okay|bye|tạm biệt|bạn là ai|bạn tên gì|"
    r"bạn làm được gì|bạn giúp được gì)\b[\s\w,!.?😊]*$",
    re.IGNORECASE,
)
# Dấu hiệu rõ ràng của việc học vụ có ngưỡng/công thức: không cần phân loại, đã có xử lý riêng.
_REGULATION_HINT = re.compile(r"đtbctl|đtbchk|cảnh báo học tập|buộc thôi học|học cải thiện|xếp loại tốt nghiệp", re.IGNORECASE)

CLASSIFY_PROMPT = """Phân loại tin nhắn của sinh viên gửi cho chatbot học vụ Trường Đại học Cần Thơ (CTU). Trả về DUY NHẤT một từ:
- regulation: hỏi về QUY CHẾ ĐÀO TẠO / công tác học vụ sinh viên đại học chính quy: tín chỉ, điểm và cách tính điểm, ĐTBCHK, ĐTBCTL, xếp loại, cảnh báo học tập, buộc thôi học, học bổng khuyến khích, đăng ký học phần, học cải thiện, tốt nghiệp, thôi học/bảo lưu, kỷ luật, điểm rèn luyện...
- external: về Trường ĐH Cần Thơ hoặc việc học nhưng KHÔNG nằm trong quy chế: mức học phí cụ thể, lịch thi/lịch học/lịch nghỉ, ký túc xá, thư viện, điểm chuẩn/tuyển sinh, thủ tục hành chính, thông tin liên hệ, tin tức/thông báo, email/mật khẩu sinh viên, cơ sở vật chất, các khoa/ngành...
- offtopic: không liên quan đến Trường hay việc học (thời tiết, nấu ăn, thơ, lập trình chung, giá vàng, thể thao...)
- smalltalk: chào hỏi, cảm ơn, hỏi bot là ai/làm được gì.
Lưu ý: quy chế chỉ nêu NGUYÊN TẮC (ví dụ "học phí tính theo tổng số tín chỉ đăng ký, mức học phí do Hiệu trưởng quyết định") chứ không có số tiền, lịch hay tin tức cụ thể. Hỏi con số/mức tiền/ngày giờ/địa điểm cụ thể của Trường là external; hỏi nguyên tắc, điều kiện, cách tính theo quy chế là regulation.
Chỉ trả về đúng một trong bốn từ trên."""


class ChatModel(Protocol):
    def stream(self, messages: list[BaseMessage]) -> Iterator[AIMessageChunk]: ...


def parse_route(text: str) -> str | None:
    lowered = text.strip().lower()
    for route in ROUTES:
        if re.match(rf"^\W*{route}\b", lowered):
            return route
    return None


def quick_route(question: str, top_score: float | None) -> str | None:
    """Quyết định không cần LLM (rẻ): None nghĩa là còn mơ hồ."""
    if _SMALLTALK.match(question) and len(question) <= 60:
        return SMALLTALK
    if _ARTICLE_MENTION.search(question) or _REGULATION_HINT.search(question):
        return REGULATION
    if top_score is not None and top_score >= HIGH_SCORE:
        return REGULATION
    return None


def classify(llm: ChatModel, history: list[BaseMessage], top_score: float | None) -> str:
    """Chọn tuyến cho tin nhắn mới nhất. Không bao giờ ném lỗi: lỗi/đầu ra lạ thì coi là `regulation`."""
    humans = [m for m in history if isinstance(m, HumanMessage)]
    if not humans:
        return REGULATION
    question = message_text(humans[-1])
    quick = quick_route(question, top_score)
    if quick is not None:
        return quick
    context = ""
    if len(humans) > 1:  # câu nối tiếp ("còn năm ngoái thì sao?") cần câu trước để hiểu
        context = f"Tin nhắn trước đó của sinh viên: {message_text(humans[-2])[:300]}\n\n"
    try:
        reply = "".join(
            message_text(c)
            for c in llm.stream(
                [SystemMessage(content=CLASSIFY_PROMPT), HumanMessage(content=f"{context}Tin nhắn cần phân loại: {question[:500]}")]
            )
        )
    except Exception:  # noqa: BLE001
        logger.warning("Không phân loại được phạm vi câu hỏi, dùng RAG như mặc định", exc_info=True)
        return REGULATION
    route = parse_route(reply)
    if route is None:
        logger.warning("Phân loại phạm vi trả về giá trị lạ %r, dùng RAG", reply[:60])
        return REGULATION
    return route
