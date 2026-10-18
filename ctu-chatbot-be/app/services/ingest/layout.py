"""Gộp kết quả khoanh vùng từng trang thành layout.json: Điều -> danh sách (trang, khung chữ nhật chuẩn hoá 0..1).

Cùng định dạng với `scripts/build_pdf_layout.py` (FE đọc qua /documents/qd3266/layout).
"""

PAD_X = 0.01  # đệm quanh khung để không cắt mất chữ ở mép
PAD_Y = 0.003


def blocks_to_highlights(blocks: list[dict], page: int, previous: int | None, articles: dict[int, dict]) -> int | None:
    """Thêm các khối hợp lệ của một trang vào `articles` (sửa tại chỗ). Trả về số Điều cuối cùng thấy được."""
    for block in blocks:
        if not isinstance(block, dict):
            continue
        article = block.get("article")
        box = block.get("box_2d")
        if isinstance(box, list) and len(box) == 1 and isinstance(box[0], list):
            box = box[0]  # Gemini đôi khi trả [[ymin, xmin, ymax, xmax]]
        if not isinstance(box, list) or len(box) != 4 or article is None:
            continue
        try:
            article = int(article)
            values = [float(v) for v in box]
        except (TypeError, ValueError):
            continue
        if values[0] < 60 and (values[3] - values[1]) < 100:
            continue  # số trang ở đầu trang
        if previous is not None and article < previous:
            continue  # số Điều lùi lại: model nhầm, bỏ khối này
        y0, x0, y1, x1 = (max(0.0, min(1.0, v / 1000)) for v in values)
        y0, y1 = max(0.0, y0 - PAD_Y), min(1.0, y1 + PAD_Y)
        x0, x1 = max(0.0, x0 - PAD_X), min(1.0, x1 + PAD_X)
        if y1 <= y0 or x1 <= x0:
            continue
        previous = article
        entry = articles.setdefault(article, {"highlights": []})
        entry["highlights"].append({"page": page, "box": [round(y0, 4), round(x0, 4), round(y1, 4), round(x1, 4)]})
    return previous


def build_layout(
    articles: dict[int, dict], titles: dict[int, str], pages: dict[int, tuple[int, int]], document: str, title: str
) -> dict:
    for number, entry in articles.items():
        entry["title"] = titles.get(number, "")
    return {
        "document": document,
        "title": title,
        "page_count": len(pages),
        "pages": {str(p): {"width": w, "height": h} for p, (w, h) in sorted(pages.items())},
        "articles": {str(n): articles[n] for n in sorted(articles)},
    }
