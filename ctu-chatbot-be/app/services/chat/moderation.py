"""Bộ lọc chửi thề / lăng mạ chạy TRƯỚC mọi bước khác: tin nhắn bị chặn không vào hàng đợi, không gọi LLM, không lưu vào lịch sử.

Cố ý bắt vừa đủ để ít chặn nhầm (câu hỏi học vụ hợp lệ như "các bạn", "du lịch", "con chó có được vào ký túc xá không"
phải qua được): mỗi mẫu đều khớp nguyên từ, và các từ mơ hồ khi bỏ dấu (cac, lon, du, deo, buoi...) chỉ bị xét khi
người dùng gõ cả câu KHÔNG dấu.
"""

import re
import unicodedata

# Khớp trên chữ thường CÓ dấu.
_ACCENTED = [
    r"địt", r"đụ", r"đéo", r"lồn", r"cặc", r"buồi", r"đĩ",
    r"đ[.\-_*]?m{1,4}", r"đ[.\-_*]?c[.\-_*]?m{1,3}", r"đ[.\-_*]?k[.\-_*]?m{1,3}",
    r"thằng\s+(?:chó|ngu|khốn|điên)", r"con\s+(?:ngu|đĩ|khốn)", r"đồ\s+(?:chó|ngu|điên|khốn|mất dạy)",
    r"chó\s+chết", r"óc\s+chó", r"mẹ\s+mày", r"mày\s+ngu", r"(?:bot|chatbot|bạn)\s+ngu",
    r"ngu\s+như\s+(?:chó|bò|lợn|heo)", r"khốn\s+nạn", r"súc\s+vật", r"mất\s+dạy", r"vô\s+học",
    r"câm\s+(?:mồm|miệng)", r"im\s+mồm",
]
# Khớp trên văn bản đã bỏ dấu, dùng cho cả hai kiểu gõ (viết tắt và tiếng Anh không bị nhập nhằng với từ thường).
_ANY = [
    r"dm{1,4}", r"dcm{1,3}", r"dkm{1,3}", r"vcl", r"vkl", r"vl", r"cmm", r"clm", r"clgt", r"cmnr",
    r"fu+c+k\w*", r"motherfu+c+k\w*", r"shit(?:ty|head)?", r"bitch\w*", r"asshole", r"cunt", r"dickhead", r"wtf", r"stfu",
]
# Chỉ xét khi cả câu gõ không dấu (khi đó "dit", "du ma" gần như chắc chắn là chửi).
_UNACCENTED_ONLY = [r"dit(?:\s+(?:me|con\s+me|cu))?", r"du\s+(?:ma|me)", r"deo", r"con\s+cac", r"cai\s+lon", r"lon\s+me"]


# Chê "ngu / ngố / ngáo / đần / khùng": chặn khi là lời chê người khác (hoặc bot), KHÔNG chặn khi người dùng tự nhận
# ("mình ngu quá không hiểu điều 14"). Khi gõ có dấu thì từ đứng riêng đã đủ rõ; khi gõ không dấu thì "ngu" có thể là "ngủ",
# "ngao" là con ngao... nên chỉ chặn khi đi kèm đại từ chê bai (bot ngu, mày ngu, thằng ngố...).
_INSULT_WORDS = r"(?:ngu(?:\s+(?:ngốc|xuẩn|si|dốt))?|ngố|ngáo|đần(?:\s+độn)?|khùng|thiểu\s+năng|não\s+cá\s+vàng)"
_SELF_BEFORE = re.compile(r"(?<!\w)(?:mình|tôi|tui|tớ|em|mik|mk|tao|con|anh|chị)\s+(?:\w+\s+)?$")
_DIRECTED_FOLDED = [r"(?:bot|chatbot|may|ban|ong|ba|thang|do|tui\s+may|cai\s+bot)\s+(?:ngu|ngo|ngao|khung|dan\s+don)"]


def _compile(patterns: list[str]) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)(?:" + "|".join(patterns) + r")(?!\w)")


_RE_ACCENTED = _compile(_ACCENTED)
_RE_ANY = _compile(_ANY)
_RE_UNACCENTED_ONLY = _compile(_UNACCENTED_ONLY)
_RE_INSULT = re.compile(r"(?<!\w)" + _INSULT_WORDS + r"(?!\w)")
_RE_DIRECTED = _compile(_DIRECTED_FOLDED)


def _insults_someone(lowered: str) -> bool:
    for match in _RE_INSULT.finditer(lowered):
        if _SELF_BEFORE.search(lowered[: match.start()]):
            continue  # tự nhận ("mình ngu quá") thì không chặn
        return True
    return False


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt (đ -> d)."""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _has_accents(text: str) -> bool:
    return "đ" in text or any(unicodedata.category(ch) == "Mn" for ch in unicodedata.normalize("NFD", text))


def is_profane(text: str) -> bool:
    lowered = unicodedata.normalize("NFC", text).lower()
    lowered = re.sub(r"(\w)\1{2,}", r"\1\1", lowered)  # "đmmmmm" -> "đmm", "fuuuck" -> "fuuck"
    folded = fold(lowered)
    folded = re.sub(r"(\w)\1{2,}", r"\1\1", folded)
    if _RE_ACCENTED.search(lowered):
        return True
    if _RE_ANY.search(folded):
        return True
    if _RE_DIRECTED.search(folded) or re.fullmatch(r"\s*ngu\W*", folded):
        return True
    if _has_accents(lowered):
        if _insults_someone(lowered):
            return True
    elif _RE_UNACCENTED_ONLY.search(folded):
        return True
    return False
