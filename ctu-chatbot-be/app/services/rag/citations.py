import re

_MENTION = re.compile(r"điều\s+(\d{1,2})\b", re.IGNORECASE)


def cited_sources(answer: str, hits: list) -> list[dict]:
    """Các Điều mà câu trả lời THỰC SỰ nhắc tới (theo thứ tự xuất hiện), giới hạn trong các Điều đã đưa cho LLM.

    Đây là danh sách "tham chiếu" hiện cho người dùng: ít và đúng chỗ hơn việc liệt kê mọi Điều đã truy xuất.
    """
    by_article = {hit.article: hit for hit in hits}
    seen: list[int] = []
    for match in _MENTION.finditer(answer):
        number = int(match.group(1))
        if number in by_article and number not in seen:
            seen.append(number)
    return [{"article": n, "title": by_article[n].title} for n in seen]
