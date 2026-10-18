"""Chuẩn hóa chữ OCR thô thành Markdown để chunk theo Điều (mã thuần túy, không gọi LLM nên kiểm thử được).

Việc làm: bỏ phần Quyết định ban hành phía trước; bỏ số trang và dòng đầu/cuối trang lặp lại; nối câu bị ngắt giữa hai
trang; đưa "Chương ..." và "Điều N. ..." về dạng tiêu đề Markdown (`##` / `###`) mà `rag.chunker` nhận ra; dọn khoảng
trắng. Không sửa nội dung từng chữ.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

_PAGE_MARK = re.compile(r"^\s*-{2,}\s*Trang\s+(\d+)\s*-{2,}\s*$", re.IGNORECASE)
_CHAPTER = re.compile(r"^(?:Chương|CHƯƠNG)\s+([IVXLC]+|\d+)\s*[.:\-–]?\s*(.*)$")
_ARTICLE = re.compile(r"^Điều\s+(\d{1,3})\s*[.:]\s*(\S.*)$")
_TITLE = re.compile(r"^QUY\s+ĐỊNH\b.*", re.IGNORECASE)
_ISSUED = re.compile(r"^\(?\s*Ban hành kèm theo", re.IGNORECASE)
_LIST_START = re.compile(r"^(\d+[.)]|[a-zđ][.)]|[-•*+]|\|)")
_SENTENCE_END = re.compile(r"[.;:!?)”\"…]$")
_MAX_HEADING_TITLE = 160
_MIN_REPEATS = 3  # dòng đầu/cuối trang lặp từng này trang trở lên thì coi là tiêu đề trang


@dataclass
class NormalizeResult:
    markdown: str
    chapters: int = 0
    articles: list[int] = field(default_factory=list)
    pages: int = 0
    removed_front_lines: int = 0
    removed_running_lines: list[str] = field(default_factory=list)
    joined_page_breaks: int = 0
    repeated_fragments: int = 0
    first_page: int = 1  # trang đầu tiên của phần Quy định (trước đó là Quyết định ban hành)
    warnings: list[str] = field(default_factory=list)


def _split_pages(raw: str) -> list[tuple[int, list[str]]]:
    pages: list[tuple[int, list[str]]] = []
    number, lines = 1, []
    started = False
    for line in raw.replace("\r\n", "\n").split("\n"):
        mark = _PAGE_MARK.match(line)
        if mark:
            if started or lines:
                pages.append((number, lines))
            number, lines, started = int(mark.group(1)), [], True
            continue
        lines.append(line)
    pages.append((number, lines))
    return pages


_EMPHASIS_HEADING = re.compile(r"^(\*{1,3}|_{1,3})\s*((?:Chương|CHƯƠNG|Điều)\b.*?)\s*\1$")


def _clean(line: str) -> str:
    line = unicodedata.normalize("NFC", line).replace(" ", " ").replace("\t", " ")
    line = re.sub(r" {2,}", " ", line).strip()
    emphasized = _EMPHASIS_HEADING.match(line)  # OCR hay bọc tiêu đề trong **...**
    return emphasized.group(2) if emphasized else line


def _drop_repeated_fragments(lines: list[str], window: int = 3) -> int:
    """OCR theo nhóm trang đôi khi lặp lại một dòng ở chỗ nối (bản cụt rồi bản đầy đủ). Bỏ bản cụt/bản lặp."""
    dropped = 0
    for i, line in enumerate(lines):
        if len(line) < 15:
            continue
        seen = 0
        for j in range(i + 1, len(lines)):
            if not lines[j]:
                continue
            seen += 1
            if seen > window:
                break
            if lines[j] == line or (lines[j].startswith(line) and len(lines[j]) > len(line)):
                lines[i] = ""
                dropped += 1
                break
    return dropped


def _strip_page_number(lines: list[str]) -> list[str]:
    """Bỏ dòng chỉ có số (số trang) ở đầu hoặc cuối trang."""
    out = list(lines)
    for index in (0, -1):
        while out and not out[index].strip():
            out.pop(index)
        if out and re.fullmatch(r"-?\s*\d{1,3}\s*-?", out[index].strip()):
            out.pop(index)
    return out


def _is_heading(line: str) -> bool:
    return bool(_CHAPTER.match(line) or _ARTICLE.match(line))


def normalize_ocr(raw: str) -> NormalizeResult:
    result = NormalizeResult(markdown="")
    pages = _split_pages(raw)
    result.pages = len(pages)
    cleaned: list[tuple[int, list[str]]] = [(n, _strip_page_number([_clean(x) for x in lines])) for n, lines in pages]

    result.first_page = next((n for n, lines in cleaned if any(_CHAPTER.match(x) for x in lines)), cleaned[0][0])

    # Tiêu đề/chân trang lặp lại ở nhiều trang.
    edge_counts: Counter[str] = Counter()
    for _, lines in cleaned:
        non_empty = [x for x in lines if x]
        for edge in {non_empty[0], non_empty[-1]} if non_empty else set():
            if len(edge) <= 120 and not _is_heading(edge):
                edge_counts[edge] += 1
    running = {text for text, count in edge_counts.items() if count >= _MIN_REPEATS}
    result.removed_running_lines = sorted(running)

    merged: list[str] = []
    for page_index, (_, lines) in enumerate(cleaned):
        non_empty_positions = [i for i, x in enumerate(lines) if x]
        if non_empty_positions:
            first, last = non_empty_positions[0], non_empty_positions[-1]
            for pos in (first, last):
                if lines[pos] in running:
                    lines[pos] = ""
        if page_index > 0:
            # Câu bị ngắt giữa hai trang: dòng cuối trang trước không kết thúc câu và dòng đầu trang sau viết thường.
            nxt = next((i for i, x in enumerate(lines) if x), None)
            prev = next((i for i in range(len(merged) - 1, -1, -1) if merged[i]), None)
            if nxt is not None and prev is not None:
                head, tail = lines[nxt], merged[prev]
                continues = (
                    head[:1].islower()
                    and not _SENTENCE_END.search(tail)
                    and not _LIST_START.match(head)
                    and not tail.startswith(("#", "|"))
                )
                if continues:
                    merged[prev] = f"{tail} {head}"
                    lines[nxt] = ""
                    result.joined_page_breaks += 1
        merged.extend(lines)
        merged.append("")

    result.repeated_fragments = _drop_repeated_fragments(merged)

    # Bỏ phần phía trước Quy định (Quyết định ban hành, căn cứ pháp lý, chữ ký).
    start = next((i for i, x in enumerate(merged) if _CHAPTER.match(x)), None)
    if start is None:
        result.warnings.append("Không thấy tiêu đề 'Chương ...' trong văn bản OCR")
        start = 0
    title_idx = next((i for i in range(start, -1, -1) if _TITLE.match(merged[i])), None)
    begin = title_idx if title_idx is not None else start
    result.removed_front_lines = sum(1 for x in merged[:begin] if x)
    body = merged[begin:]

    out: list[str] = []
    chapters = 0
    index = 0
    while index < len(body):
        line = body[index]
        index += 1
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if title_idx is not None and index - 1 == 0 and _TITLE.match(line):
            out.extend([f"# {line}", ""])
            continue
        if _ISSUED.match(line):
            out.extend([f"*{line.strip('*')}*", ""])
            continue
        chapter = _CHAPTER.match(line)
        if chapter:
            number, rest = chapter.group(1), chapter.group(2).strip()
            if not rest:  # tiêu đề chương nằm ở dòng kế
                following = next((j for j in range(index, len(body)) if body[j]), None)
                if following is not None and not _is_heading(body[following]) and body[following].isupper():
                    rest = body[following]
                    body[following] = ""
            out.extend(["", f"## Chương {number}. {rest}".rstrip(". ") if rest else f"## Chương {number}", ""])
            chapters += 1
            continue
        article = _ARTICLE.match(line)
        if article and len(article.group(2)) <= _MAX_HEADING_TITLE and not article.group(2).endswith("."):
            number = int(article.group(1))
            out.extend(["", f"### Điều {number}. {article.group(2).strip()}", ""])
            result.articles.append(number)
            continue
        out.append(line)

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    result.markdown = text
    result.chapters = chapters
    if not result.articles:
        result.warnings.append("Không thấy tiêu đề 'Điều N. ...' nào")
    return result
