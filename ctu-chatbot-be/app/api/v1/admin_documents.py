"""Admin nạp tài liệu quy định mới: upload PDF -> tự động chạy cả quy trình và cho xem tiến độ từng bước.

Body của POST là chính file PDF (Content-Type: application/pdf), tên file nằm ở query `filename`
(không dùng multipart để khỏi cần thêm thư viện).
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

from app.api.deps import get_document_catalog, get_ingest_manager, require_admin
from app.core.config import settings
from app.services.ingest import pdf as pdf_mod
from app.services.chat import route_catalog
from app.services.ingest.catalog import CatalogError, DocumentCatalog
from app.services.ingest.manager import IngestBusy, JobManager

router = APIRouter(prefix="/admin/documents", tags=["admin"], dependencies=[Depends(require_admin)])


def _require_enabled() -> None:
    if not settings.document_ingest_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="INGEST_DISABLED")


def _catalog_error(exc: CatalogError) -> HTTPException:
    code = str(exc)
    if code.endswith("_NOT_FOUND"):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=code)
    if code == "CATALOG_READ_ONLY":
        return HTTPException(status.HTTP_403_FORBIDDEN, detail=code)
    if code == "CATALOG_SYNC_DISABLED":
        return HTTPException(status.HTTP_403_FORBIDDEN, detail=code)
    if code.endswith("_NOT_ALLOWED"):
        return HTTPException(status.HTTP_409_CONFLICT, detail=code)
    if code == "DOCUMENT_NAME_INVALID":
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=code)
    if code == "EXTRACT_FAILED" or code == "CLEAN_FAILED" or code == "SYNC_FAILED":
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=code)
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=code)


@router.get("/catalog")
def catalog_overview(catalog: DocumentCatalog = Depends(get_document_catalog)) -> dict:
    try:
        config = route_catalog.load_config()
    except ValueError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="ROUTE_CONFIG_INVALID") from exc
    return {
        "editable": route_catalog.editable(),
        "sync_enabled": settings.document_catalog_sync_enabled,
        "routes": config,
        "jobs": catalog.list_jobs(),
    }


@router.get("/catalog/jobs/{slug}/{job_id}")
def catalog_job(slug: str, job_id: str, catalog: DocumentCatalog = Depends(get_document_catalog)) -> dict:
    try:
        return catalog.get_job(slug, job_id)
    except CatalogError as exc:
        raise _catalog_error(exc) from exc


@router.post("/catalog/jobs", status_code=status.HTTP_201_CREATED)
async def catalog_upload(
    request: Request,
    title: str,
    filename: str = "tai-lieu.pdf",
    catalog: DocumentCatalog = Depends(get_document_catalog),
) -> dict:
    if not settings.document_catalog_edit_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="CATALOG_READ_ONLY")
    limit = settings.ingest_max_pdf_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF_TOO_LARGE")
    parts: list[bytes] = []
    size = 0
    async for part in request.stream():
        size += len(part)
        if size > limit:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF_TOO_LARGE")
        parts.append(part)
    data = b"".join(parts)
    try:
        pdf_mod.check_pdf_bytes(data, settings.ingest_max_pdf_mb)
        return catalog.upload(title, filename, data)
    except pdf_mod.PdfError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="INVALID_PDF") from exc
    except CatalogError as exc:
        raise _catalog_error(exc) from exc


@router.post("/catalog/jobs/{slug}/{job_id}/extract")
def catalog_extract(slug: str, job_id: str, catalog: DocumentCatalog = Depends(get_document_catalog)) -> dict:
    try:
        return catalog.extract(slug, job_id)
    except CatalogError as exc:
        raise _catalog_error(exc) from exc


@router.post("/catalog/jobs/{slug}/{job_id}/clean")
def catalog_clean(slug: str, job_id: str, catalog: DocumentCatalog = Depends(get_document_catalog)) -> dict:
    try:
        return catalog.clean(slug, job_id)
    except CatalogError as exc:
        raise _catalog_error(exc) from exc


@router.post("/catalog/jobs/{slug}/{job_id}/sync")
def catalog_sync_job(slug: str, job_id: str, catalog: DocumentCatalog = Depends(get_document_catalog)) -> dict:
    try:
        return catalog.sync_job(slug, job_id)
    except CatalogError as exc:
        raise _catalog_error(exc) from exc


@router.post("/catalog/sync")
def catalog_sync(catalog: DocumentCatalog = Depends(get_document_catalog)) -> dict:
    try:
        return catalog.sync_catalog()
    except (CatalogError, ValueError, OSError) as exc:
        if isinstance(exc, CatalogError):
            raise _catalog_error(exc) from exc
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CATALOG_SYNC_FAILED") from exc


@router.put("/catalog/routes")
def update_route_catalog(
    payload: dict,
) -> dict:
    if not route_catalog.editable():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="CATALOG_READ_ONLY")
    try:
        return route_catalog.save_config(payload)
    except (ValueError, OSError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="ROUTE_CONFIG_INVALID") from exc


def _summary(job, manager: JobManager | None = None) -> dict:
    active = manager.active_info() if manager else None
    is_active = bool(active and active["version"] == job.id)
    return {
        "is_active": is_active,
        "can_activate": bool(manager and not is_active and manager.can_activate(job)),
        "id": job.id,
        "filename": job.filename,
        "size_bytes": job.size_bytes,
        "status": job.status,
        "activated": job.activated,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


@router.get("")
def overview(manager: JobManager = Depends(get_ingest_manager)) -> dict:
    """Tài liệu đang dùng, lần nạp đang chạy (nếu có) và lịch sử các lần nạp gần đây."""
    return {
        "enabled": settings.document_ingest_enabled,
        "active": manager.active_info(),
        "default_available": manager.default_available(),
        "running_job_id": manager.running_job_id,
        "jobs": [_summary(j, manager) for j in manager.list()],
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str, manager: JobManager = Depends(get_ingest_manager)) -> dict:
    _valid_job_id(job_id)
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job.to_dict()


def _valid_job_id(job_id: str) -> None:
    if not re.fullmatch(r"[0-9]{14}-[0-9a-f]{6}", job_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")


@router.get("/jobs/{job_id}/source")
def download_source(job_id: str, manager: JobManager = Depends(get_ingest_manager)) -> FileResponse:
    """Tải lại file PDF gốc của một lần nạp."""
    _valid_job_id(job_id)
    job = manager.get(job_id)
    path = manager.source_path(job_id) if job else None
    if job is None or path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source not found")
    return FileResponse(path, media_type="application/pdf", filename=job.filename)


@router.post("/versions/default/activate")
def activate_default(manager: JobManager = Depends(get_ingest_manager)) -> dict:
    """Quay về tài liệu mặc định kèm hệ thống."""
    _require_enabled()
    try:
        manager.switch_to_default()
    except IngestBusy:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="INGEST_BUSY") from None
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="DEFAULT_UNAVAILABLE") from None
    return {"active": None}


@router.post("/versions/{job_id}/activate")
def activate_version(job_id: str, manager: JobManager = Depends(get_ingest_manager)) -> dict:
    """Áp dụng lại một phiên bản đã nạp trước đó (chỉ phiên bản từng qua kiểm thử)."""
    _require_enabled()
    _valid_job_id(job_id)
    try:
        info = manager.switch_to(job_id)
    except IngestBusy:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="INGEST_BUSY") from None
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="VERSION_UNAVAILABLE") from None
    return {"active": info}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload(request: Request, filename: str = "tai-lieu.pdf", manager: JobManager = Depends(get_ingest_manager)) -> dict:
    """Nhận PDF và bắt đầu quy trình ở nền. Trả về job ngay; theo dõi tiến độ bằng GET /jobs/{id}."""
    _require_enabled()
    limit = settings.ingest_max_pdf_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, detail="PDF_TOO_LARGE")
    chunks: list[bytes] = []
    size = 0
    async for part in request.stream():
        size += len(part)
        if size > limit:
            raise HTTPException(413, detail="PDF_TOO_LARGE")
        chunks.append(part)
    data = b"".join(chunks)
    try:
        pdf_mod.check_pdf_bytes(data, settings.ingest_max_pdf_mb)
    except pdf_mod.PdfError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"INVALID_PDF: {exc}") from None
    safe_name = re.sub(r"[^\w.\- ()]", "_", filename)[:120] or "tai-lieu.pdf"
    try:
        job = manager.start(safe_name, data)
    except IngestBusy:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="INGEST_BUSY") from None
    return job.to_dict()
