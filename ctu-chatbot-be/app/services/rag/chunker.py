import re
from dataclasses import dataclass

_CHAPTER = re.compile(r"^##\s+(Chương\s+.+?)\s*$")
_ARTICLE = re.compile(r"^###\s+Điều\s+(\d+)\.\s*(.+?)\s*$")
# Ghi chú của người chuẩn hóa văn bản, không phải nội dung quy định.
_EDITORIAL = re.compile(r"^\*\(Các ô")


@dataclass(frozen=True)
class Chunk:
    """Một Điều của văn bản quy định (đơn vị chunk theo yêu cầu: mỗi Điều là một chunk)."""

    article: int
    title: str
    chapter: str
    text: str  # đã gồm dòng tiêu đề "Điều N. ..." nên vector mang đúng chủ đề

    @property
    def id(self) -> str:
        return f"dieu-{self.article}"

    @property
    def heading(self) -> str:
        return f"Điều {self.article}. {self.title}"


def split_into_articles(markdown: str) -> list[Chunk]:
    """Tách văn bản đã chuẩn hóa thành các chunk, mỗi Điều một chunk."""
    chunks: list[Chunk] = []
    chapter = ""
    current: dict | None = None

    def flush() -> None:
        if current is None:
            return
        body = "\n".join(current["lines"]).strip()
        text = f"{current['chapter']}\n{current['heading']}\n\n{body}".strip()
        chunks.append(Chunk(current["article"], current["title"], current["chapter"], text))

    for line in markdown.splitlines():
        chapter_match = _CHAPTER.match(line)
        if chapter_match:
            flush()
            current = None
            chapter = chapter_match.group(1)
            continue
        article_match = _ARTICLE.match(line)
        if article_match:
            flush()
            number, title = int(article_match.group(1)), article_match.group(2)
            current = {
                "article": number,
                "title": title,
                "chapter": chapter,
                "heading": f"Điều {number}. {title}",
                "lines": [],
            }
            continue
        if current is not None and not _EDITORIAL.match(line):
            current["lines"].append(line)
    flush()

    numbers = [c.article for c in chunks]
    if len(set(numbers)) != len(numbers):
        raise ValueError(f"Điều bị trùng khi tách chunk: {numbers}")
    return chunks
