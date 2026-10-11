import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter(prefix="/documents", tags=["documents"])

# Dữ liệu do scripts/build_pdf_layout.py sinh ra: ảnh từng trang PDF + vị trí từng Điều trên trang.
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "qd3266"
_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


@lru_cache(maxsize=1)
def _layout() -> dict:
    path = DATA_DIR / "layout.json"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document layout not built")
    return json.loads(path.read_text(encoding="utf-8"))


# Văn bản quy định là tài liệu công khai của Trường và FE hiển thị ảnh bằng thẻ <img> (không gắn được header
# Authorization), nên hai endpoint này không yêu cầu đăng nhập.
@router.get("/qd3266/layout")
def get_layout() -> dict:
    """Số trang, kích thước ảnh và vị trí (trang + khung chữ nhật chuẩn hoá 0..1) của từng Điều."""
    return _layout()


@router.get("/qd3266/pages/{page}.jpg")
def get_page_image(page: int) -> FileResponse:
    layout = _layout()
    if page < 1 or page > int(layout["page_count"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Page not found")
    path = DATA_DIR / "pages" / f"page-{page:02d}.jpg"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Page not found")
    return FileResponse(path, media_type="image/jpeg", headers=_CACHE_HEADERS)
