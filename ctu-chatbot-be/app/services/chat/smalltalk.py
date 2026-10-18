"""Chào hỏi / cảm ơn / tạm biệt / "bạn là ai?" -> trả lời có sẵn, KHÔNG gọi LLM (nhanh, miễn phí, không tốn lượt chat).

Chỉ khớp khi CẢ tin nhắn là câu xã giao (so khớp nguyên câu sau khi bỏ dấu/dấu câu/emoji): "chào bạn" qua,
"chào bạn cho mình hỏi về điều 14" không qua -> vẫn đi đường bình thường để được trả lời đúng ý.
Kết quả trả về dưới dạng `SuggestedAnswer` nên đi chung đường "trả lời có sẵn" với câu hỏi gợi ý.
"""

import random
import re

from app.services.chat.moderation import fold
from app.services.chat.suggested import SuggestedAnswer

_TAIL = r"(?:\s+(?:ban|bot|chatbot|ad|admin|oi|a|ah|nha|nhe|nhen|ne|day|em|anh|chi|moi nguoi|cac ban|ca nha|vay|the|nhi|ha))*"

_PATTERNS: dict[str, re.Pattern[str]] = {
    "bye": re.compile(rf"^(?:bye(?: bye)?|bai bai|tam biet|hen gap lai|goodbye|good bye|see you|chao tam biet){_TAIL}$"),
    "thanks": re.compile(
        r"^(?:cam on|thanks?|thank you|tks|thx|ty)"
        r"(?:\s+(?:ban|bot|chatbot|nhieu|rat nhieu|nha|nhe|a|ah|nhen|so much|you|em|ad|admin))*$"
    ),
    "greeting": re.compile(
        rf"^(?:xin )?(?:chao|hi+|hello+|helo|hey+|alo|hallo|hola|yo|he lo|good (?:morning|afternoon|evening))"
        rf"(?:\s+buoi\s+(?:sang|trua|chieu|toi))?{_TAIL}$"
    ),
    "who": re.compile(
        r"^(?:ban la ai|ban ten gi|ban ten la gi|ban la gi|bot la ai|bot ten gi|ban la chatbot gi|gioi thieu(?: ve)?(?: ban)?(?: than)?)"
        r"(?:\s+(?:vay|the|nhi|nha|ha|a|ah|ne|oi|ban))*$"
    ),
    "capabilities": re.compile(
        r"^(?:ban lam duoc gi|ban giup duoc gi|ban co the lam gi|ban biet lam gi|ban co the giup(?: toi| minh| em)? gi|ban giup gi duoc"
        r"|bot lam duoc gi|huong dan(?: su dung)?|help|giup(?: toi| minh| em)?|ban lam gi|ban biet gi)"
        r"(?:\s+(?:vay|the|nhi|nha|ha|a|ah|ne|oi))*$"
    ),
    "ack": re.compile(r"^(?:ok|oke|okie|okay|duoc roi|hieu roi|da hieu|tuyet voi|tuyet)(?:\s+(?:ban|nha|nhe|a|ah|roi|ha|nhen|bot|chatbot|la))*$"),
}

# Mỗi loại có nhiều biến thể ngắn gọn, mỗi lần chọn ngẫu nhiên một câu cho đỡ nhàm.
_REPLIES: dict[str, list[str]] = {
    "greeting": [
        "Xin chào bạn! 👋 Mình là trợ lý học vụ của Trường Đại học Cần Thơ. Bạn muốn hỏi gì về quy chế đào tạo, điểm số, tín chỉ hay tốt nghiệp?",
        "Chào bạn nha! 😊 Cần tra cứu quy chế học vụ (điểm, học phần, cảnh báo học tập, học bổng...) cứ hỏi mình nhé.",
        "Hello bạn! Mình sẵn sàng giải đáp thắc mắc về quy chế đào tạo của CTU. Bạn hỏi đi nào!",
        "Ê, chào bạn hiền! 🌟 Hôm nay bạn muốn tra cứu điều gì về học vụ?",
        "Chào mừng bạn ghé thăm! Điểm số, tín chỉ hay học bổng, bạn cứ hỏi, mình trả lời liền tay 💪",
        "Alo alo! 📞 Trợ lý học vụ CTU nghe đây. Bạn cần mình giúp gì nào?",
        "Hi bạn! ✨ Mình ở đây để giải thích quy chế học vụ cho dễ hiểu. Bạn thắc mắc chỗ nào?",
        "Chào bạn, chúc bạn một ngày học tập thật hiệu quả! 📚 Có gì cần hỏi cứ nhắn mình nha.",
        "Dạ, mình chào bạn! 🙌 Bạn muốn biết về điểm, học phần, cảnh báo học tập hay tốt nghiệp?",
        "Chào bạn nè! 🐾 Quy chế dài dòng để mình đọc giúp, bạn chỉ cần hỏi thôi.",
        "Xin chào! Rất vui được gặp bạn. Bạn cứ đặt câu hỏi về quy chế đào tạo của Trường nhé 😄",
        "Hế lô! 🎓 Mình sẵn sàng rồi, bạn hỏi đi!",
    ],
    "thanks": [
        "Không có chi bạn nhé! 😊 Cần hỏi thêm gì về học vụ cứ nhắn mình.",
        "Rất vui vì giúp được bạn! Có thắc mắc nào nữa thì cứ hỏi mình nha.",
        "Dạ không có gì ạ! 💛 Bạn cần tra cứu thêm gì thì cứ nói mình nhé.",
        "Giúp được bạn là mình vui rồi! 🌈 Còn gì thắc mắc thì hỏi tiếp nha.",
        "Đừng khách sáo nha bạn ơi! Mình luôn ở đây khi bạn cần.",
        "Có gì đâu bạn! Chúc bạn học tốt, điểm cao nhé 🎯",
    ],
    "bye": [
        "Tạm biệt bạn! 👋 Khi nào cần tra cứu quy chế học vụ cứ quay lại nhé.",
        "Hẹn gặp lại bạn! Chúc bạn học tốt và điểm cao nha 🎓",
        "Bye bye bạn! 🌸 Có thắc mắc gì mình luôn ở đây.",
        "Chào bạn nhé, chúc bạn một ngày thật vui! ☀️",
        "Hẹn gặp lại! Nhớ ăn uống đầy đủ và ôn bài đều đặn nha 🍀",
        "Tạm biệt! Khi nào cần mình cứ ghé lại, mình không đi đâu cả 😄",
    ],
    "who": [
        "Mình là chatbot học vụ của Trường Đại học Cần Thơ 🤖 Mình trả lời các câu hỏi về Quy chế đào tạo trình độ đại học (QĐ 3266/QĐ-ĐHCT) và có thể giúp tính điểm trung bình, kèm trích dẫn Điều khoản.",
        "Mình là trợ lý ảo giúp sinh viên CTU tra cứu quy chế đào tạo đại học 📘 Hỏi mình về điểm, tín chỉ, cảnh báo học tập, học bổng, tốt nghiệp... mình sẽ trả lời kèm Điều khoản liên quan.",
        "Mình là bạn đồng hành học vụ của sinh viên CTU ✨ Chuyên đọc quy chế (QĐ 3266/QĐ-ĐHCT) thay bạn và giải thích cho dễ hiểu.",
    ],
    "capabilities": [
        "Mình có thể giúp bạn:\n- Tra cứu Quy chế đào tạo đại học của CTU (điểm, tín chỉ, đăng ký học phần, cảnh báo học tập, học bổng, tốt nghiệp...) và trích dẫn Điều khoản.\n- Tính điểm trung bình học kỳ / tích lũy.\n- Tìm thông tin ngoài quy chế của Trường (học phí, ký túc xá, lịch...) khi cần.\n\nBạn cứ đặt câu hỏi nhé!",
        "Mình làm được khá nhiều thứ nè 💡\n- Giải thích quy chế đào tạo đại học của CTU, có trích Điều khoản.\n- Tính ĐTBCHK, ĐTBCTL giúp bạn.\n- Tra thêm thông tin của Trường trên web khi quy chế không đề cập.\n\nBạn thử hỏi một câu đi!",
    ],
    "ack": [
        "Ok bạn! Cần hỏi thêm gì cứ nhắn mình nhé 😊",
        "Mình luôn sẵn sàng khi bạn cần tra cứu thêm nha!",
        "Okie! 👌 Còn gì thắc mắc cứ hỏi tiếp nhé.",
        "Dạ! Bạn cần gì thêm thì cứ nói mình nghe nha 🙌",
        "Tuyệt! Có câu hỏi khác thì bạn cứ gửi mình nhé ✨",
    ],
}


def _normalize(text: str) -> str:
    text = fold(text)
    text = re.sub(r"(.)\1{2,}", r"\1", text)  # "chaooo" -> "chao"
    text = re.sub(r"[^a-z0-9]+", " ", text)  # bỏ dấu câu / emoji
    return text.strip()


def lookup(text: str, rng: random.Random | None = None) -> SuggestedAnswer | None:
    """Tin nhắn có phải thuần xã giao không? Có thì trả câu trả lời có sẵn (chọn ngẫu nhiên một biến thể)."""
    normalized = _normalize(text)
    if not normalized or len(normalized) > 60:
        return None
    for kind, pattern in _PATTERNS.items():
        if pattern.match(normalized):
            answer = (rng or random).choice(_REPLIES[kind])
            return SuggestedAnswer(id=f"smalltalk:{kind}", category="smalltalk", question=text, answer=answer)
    return None
