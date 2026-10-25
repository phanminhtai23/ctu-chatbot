import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import get_document_catalog
from app.services.ingest.catalog import CatalogError, DocumentCatalog
from app.services.ingest.storage import active_data_dir

router = APIRouter(prefix="/documents", tags=["documents"])

# Ảnh từng trang PDF + vị trí từng Điều trên trang của phiên bản tài liệu ĐANG DÙNG: do admin nạp (xem
# app/services/ingest) hoặc, nếu chưa nạp lần nào, do scripts/build_pdf_layout.py sinh ra.
# Ảnh luôn được kiểm tra lại với ETag (không cache cứng) vì admin có thể thay tài liệu bất cứ lúc nào.
_CACHE_HEADERS = {"Cache-Control": "no-cache"}
_layout_cache: dict[str, tuple[float, dict]] = {}


def clear_layout_cache() -> None:
    _layout_cache.clear()


def _layout() -> dict:
    path = active_data_dir() / "layout.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document layout not built") from None
    cached = _layout_cache.get(str(path))
    if cached is None or cached[0] != mtime:
        cached = (mtime, json.loads(path.read_text(encoding="utf-8")))
        _layout_cache.clear()
        _layout_cache[str(path)] = cached
    return cached[1]


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
    path = active_data_dir() / "pages" / f"page-{page:02d}.jpg"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Page not found")
    return FileResponse(path, media_type="image/jpeg", headers=_CACHE_HEADERS)


@router.get("/catalog/{slug}/{version}/source")
def get_catalog_source(slug: str, version: str, catalog: DocumentCatalog = Depends(get_document_catalog)) -> FileResponse:
    try:
        path = catalog.source_file(slug, version)
    except CatalogError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found") from exc
    return FileResponse(path, media_type="application/pdf", filename=f"{slug}-{version}.pdf")
