"""Admin nạp tài liệu quy định mới: upload PDF -> tự động chạy cả quy trình và cho xem tiến độ từng bước.

Body của POST là chính file PDF (Content-Type: application/pdf), tên file nằm ở query `filename`
(không dùng multipart để khỏi cần thêm thư viện).
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

from app.api.deps import get_ingest_manager, require_admin
from app.core.config import settings
from app.services.ingest import pdf as pdf_mod
from app.services.ingest.manager import IngestBusy, JobManager

router = APIRouter(prefix="/admin/documents", tags=["admin"], dependencies=[Depends(require_admin)])


def _require_enabled() -> None:
    if not settings.document_ingest_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="INGEST_DISABLED")


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
