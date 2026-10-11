"""Sinh dữ liệu để FE hiển thị PDF quy định và tô sáng đúng đoạn khi người dùng bấm vào một tham chiếu.

PDF gốc là bản scan (không có lớp chữ), nên không thể tìm vị trí chữ bằng PDF.js. Cách làm:
  1. Render từng trang ra ảnh JPEG  -> app/data/qd3266/pages/page-NN.jpg
  2. Nhờ Gemini (nhìn ảnh) khoanh các khối văn bản của từng trang và cho biết khối đó thuộc Điều nào
     (chỉ trả toạ độ, không chép lại chữ nên không dính bộ lọc RECITATION)
  3. Gộp thành app/data/qd3266/layout.json: Điều -> danh sách (trang, khung chữ nhật chuẩn hoá 0..1)

Chạy lại khi PDF đổi:  python scripts/build_pdf_layout.py [--pdf đường_dẫn.pdf] [--skip-render]
Cần: `pdftoppm` (poppler) trong PATH và GEMINI_API_KEY_* trong .env. Mất khoảng 3-5 phút (giãn cách 7s/trang
để không vượt quota free).
"""

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.services.rag.chunker import split_into_articles  # noqa: E402
from app.services.rag.store import default_source_path  # noqa: E402

DATA_DIR = BACKEND_DIR / "app" / "data" / "qd3266"
PAGES_DIR = DATA_DIR / "pages"
RAW_DIR = BACKEND_DIR / "scripts" / ".layout_raw"  # phản hồi thô của Gemini, dùng lại khi chạy lại
FIRST_REGULATION_PAGE = 3  # trang 1-2 là Quyết định ban hành; Quy định bắt đầu từ trang 3
MIN_INTERVAL = float(os.environ.get("LAYOUT_INTERVAL", "7"))
MAX_CALLS = 30
# Model dùng cho bước khoanh vùng. gemini-3.1-flash-lite khoanh lệch ~8% ở một số trang;
# gemini-3.5-flash khoanh chính xác hơn hẳn. Đổi bằng biến môi trường LAYOUT_MODEL.
LAYOUT_MODEL = os.environ.get("LAYOUT_MODEL", "gemini-3.5-flash")
PAD_X = 0.01  # đệm quanh khung để không cắt mất chữ ở mép
PAD_Y = 0.003

PROMPT = """Đây là trang {page} của văn bản "Quy định công tác học vụ" (tiếng Việt, bản scan).
Hãy xác định MỌI khối văn bản trên trang theo thứ tự đọc: tiêu đề "Điều N. ...", từng đoạn văn, từng khoản (1., 2., a), b)...), và từng bảng.
Với mỗi khối trả về:
- "box_2d": [ymin, xmin, ymax, xmax] chuẩn hoá về 0-1000, ôm sát khối chữ.
- "article": số N của "Điều N." mà khối đó thuộc về. Khối thuộc Điều gần nhất phía trên nó. Các khối nằm đầu trang, trước mọi tiêu đề "Điều", là phần tiếp theo của Điều {previous}.
Quy tắc:
- Bỏ qua số trang, dòng đầu/cuối trang, tiêu đề "Chương ..." (article = null).
- Mỗi khoản/đoạn là một khối riêng; một bảng là một khối.
- KHÔNG chép lại nội dung chữ.
Chỉ trả JSON: {{"blocks": [{{"article": 12, "box_2d": [ymin, xmin, ymax, xmax]}}, ...]}}"""


class KeyRotator:
    """Gọi Gemini bằng nhiều key: key nào bị 429 (hết hạn mức) thì chuyển sang key kế tiếp."""

    def __init__(self, keys: list[str]):
        from google import genai

        self._clients = [genai.Client(api_key=k) for k in keys]
        self._index = 0

    @property
    def models(self):
        return self

    def generate_content(self, **kwargs):
        last: Exception | None = None
        for _ in range(len(self._clients)):
            try:
                return self._clients[self._index].models.generate_content(**kwargs)
            except Exception as exc:  # noqa: BLE001
                text = str(exc)
                if "429" in text or "RESOURCE_EXHAUSTED" in text:
                    last = exc
                    self._index = (self._index + 1) % len(self._clients)
                    print(f"key hết hạn mức, chuyển sang key #{self._index + 1}", flush=True)
                    continue
                raise
        raise last  # type: ignore[misc]


def jpeg_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return width, height
        i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    raise ValueError(f"không đọc được kích thước {path}")


def render_pages(pdf: Path) -> None:
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    for old in PAGES_DIR.glob("page-*.jpg"):
        old.unlink()
    subprocess.run(
        ["pdftoppm", "-r", "110", "-jpeg", "-jpegopt", "quality=70", str(pdf), str(PAGES_DIR / "page")],
        check=True,
    )


def ask_layout(client, image: bytes, page: int, previous: int | None) -> list[dict]:
    from google.genai import types

    prompt = PROMPT.format(page=page, previous=previous if previous is not None else "(chưa có, trang đầu của Quy định)")
    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0)
    last_error = ""
    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model=LAYOUT_MODEL,
                contents=[types.Part.from_bytes(data=image, mime_type="image/jpeg"), prompt],
                config=config,
            )
            data = json.loads(response.text)
            return data["blocks"] if isinstance(data, dict) else data
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
                raise SystemExit(f"Hết hạn mức Gemini, dừng: {last_error[:200]}") from exc
            time.sleep(15)
    raise SystemExit(f"Trang {page} lỗi sau 4 lần thử: {last_error[:300]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=next((BACKEND_DIR.parent / "vector-docs").glob("QD3266*.pdf"), None))
    parser.add_argument("--skip-render", action="store_true", help="dùng lại ảnh trang đã render")
    args = parser.parse_args()

    if not args.skip_render:
        if args.pdf is None or not args.pdf.exists():
            raise SystemExit("Không tìm thấy PDF gốc; truyền --pdf hoặc dùng --skip-render")
        render_pages(args.pdf)
    images = sorted(PAGES_DIR.glob("page-*.jpg"))
    if not images:
        raise SystemExit(f"Chưa có ảnh trang trong {PAGES_DIR}")

    keys = settings.gemini_api_keys
    if not keys:
        raise SystemExit("Chưa có GEMINI_API_KEY_* trong .env")
    client = KeyRotator(keys)
    titles = {c.article: c.title for c in split_into_articles(default_source_path().read_text(encoding="utf-8"))}

    pages_info: dict[str, dict] = {}
    articles: dict[int, dict] = {}
    previous: int | None = None
    calls = 0
    for image in images:
        page = int(re.search(r"(\d+)\.jpg$", image.name).group(1))
        width, height = jpeg_size(image)
        pages_info[str(page)] = {"width": width, "height": height}
        if page < FIRST_REGULATION_PAGE:
            continue
        if calls >= MAX_CALLS:
            raise SystemExit("Đủ trần số lần gọi, dừng")
        raw_file = RAW_DIR / f"page-{page:02d}.json"
        if raw_file.exists():
            blocks = json.loads(raw_file.read_text(encoding="utf-8"))
        else:
            calls += 1
            blocks = ask_layout(client, image.read_bytes(), page, previous)
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            raw_file.write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")
            time.sleep(MIN_INTERVAL)
        print(f"trang {page}: {len(blocks)} khối", flush=True)
        for block in blocks:
            article = block.get("article")
            box = block.get("box_2d")
            if isinstance(box, list) and len(box) == 1 and isinstance(box[0], list):
                box = box[0]  # Gemini đôi khi trả [[ymin, xmin, ymax, xmax]]
            if not isinstance(box, list) or len(box) != 4:
                continue
            if box[0] < 60 and (box[3] - box[1]) < 100:
                continue  # số trang ở đầu trang
            if article is None:
                continue  # tiêu đề Chương, số trang...
            article = int(article)
            if previous is not None and article < previous:
                continue  # số Điều lùi lại: model nhầm, bỏ khối này
            y0, x0, y1, x1 = (max(0.0, min(1.0, float(v) / 1000)) for v in box)
            y0, y1 = max(0.0, y0 - PAD_Y), min(1.0, y1 + PAD_Y)
            x0, x1 = max(0.0, x0 - PAD_X), min(1.0, x1 + PAD_X)
            if y1 <= y0 or x1 <= x0:
                continue
            previous = article
            entry = articles.setdefault(article, {"title": titles.get(article, ""), "highlights": []})
            entry["highlights"].append({"page": page, "box": [round(y0, 4), round(x0, 4), round(y1, 4), round(x1, 4)]})

    missing = sorted(set(titles) - set(articles))
    layout = {
        "document": "QD3266",
        "title": "Quy định công tác học vụ dành cho sinh viên trình độ đại học hình thức chính quy",
        "page_count": len(images),
        "pages": pages_info,
        "articles": {str(n): articles[n] for n in sorted(articles)},
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "layout.json").write_text(json.dumps(layout, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã ghi layout.json: {len(articles)} Điều, thiếu: {missing or 'không'}")


if __name__ == "__main__":
    main()
