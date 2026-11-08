import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import get_current_user, get_document_catalog
from app.core.config import settings
from app.services.chat import route_catalog
from app.services.ingest.catalog import CatalogError, DocumentCatalog
from app.services.ingest.storage import active_data_dir

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/catalog/summary")
def catalog_summary() -> dict:
    """Công khai (trang giới thiệu): các tài liệu chatbot đang hỗ trợ = tuyến tài liệu đã đồng bộ và đang bật trong catalog."""
    try:
        nodes = route_catalog.enabled_nodes(route_catalog.load_config())
    except ValueError:
        return {"count": 0, "documents": []}
    documents = [
        {
            "id": node["id"],
            "label": node["label"],
            "decision_no": node.get("decision_no", ""),
            "description": node.get("description", ""),
            "official_url": node.get("official_url", ""),
        }
        for node in nodes
        if node["kind"] == "document"
    ]
    return {"count": len(documents), "documents": documents}


@router.get("/catalog/routes", dependencies=[Depends(get_current_user)])
def selectable_routes() -> list[dict]:
    """Các nguồn người dùng có thể chọn để hỏi: tài liệu đã đồng bộ và (nếu bật) tìm kiếm web. Mặc định người dùng dùng tất cả."""
    try:
        nodes = route_catalog.enabled_nodes(route_catalog.load_config())
    except ValueError:
        return []
    return [
        {
            "id": node["id"],
            "label": node["label"],
            "kind": node["kind"],
            "description": node.get("description", ""),
            "decision_no": node.get("decision_no", ""),
            "official_url": node.get("official_url", ""),
        }
        for node in nodes
        if node["kind"] == "document" or (node["kind"] == "web" and settings.web_search_enabled)
    ]

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
