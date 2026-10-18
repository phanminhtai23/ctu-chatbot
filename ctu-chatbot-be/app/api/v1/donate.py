from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from app.api.deps import require_admin
from app.core.config import settings
from app.services import donate

# Công khai: thẻ <img> không gửi được header Authorization. Mã QR ủng hộ vốn là thứ để cho mọi người xem.
router = APIRouter(prefix="/donate", tags=["donate"])
admin_router = APIRouter(prefix="/admin/donate", tags=["admin"], dependencies=[Depends(require_admin)])


def _info(qr: donate.QrInfo | None) -> dict:
    return {"has_qr": qr is not None, "version": qr.version if qr else None}


@router.get("")
def donate_info() -> dict:
    """Có ảnh QR chưa, và phiên bản của nó (để FE ghép vào URL ảnh tránh cache cũ)."""
    return _info(donate.current_qr())


@router.get("/qr")
def get_qr(request: Request):
    qr = donate.current_qr()
    if qr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="NO_QR")
    headers = {
        "ETag": f'"{qr.version}"',
        "Cache-Control": "no-cache",  # luôn hỏi lại bằng ETag: đổi ảnh là thấy ngay, không đổi thì nhận 304 rất nhẹ
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == headers["ETag"]:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return FileResponse(qr.path, media_type=qr.mime, headers=headers)


@admin_router.put("/qr")
async def upload_qr(request: Request) -> dict:
    """Admin tải ảnh QR lên (PNG/JPEG/WebP). Gửi nguyên file làm body, giống cách tải PDF ở trang tài liệu."""
    limit = int(settings.donate_qr_max_mb * 1024 * 1024)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, detail="IMAGE_TOO_LARGE")
    chunks: list[bytes] = []
    size = 0
    async for part in request.stream():
        size += len(part)
        if size > limit:
            raise HTTPException(413, detail="IMAGE_TOO_LARGE")
        chunks.append(part)
    try:
        qr = donate.save_qr(b"".join(chunks))
    except donate.InvalidImage:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="INVALID_IMAGE") from None
    return _info(qr)


@admin_router.delete("/qr", status_code=status.HTTP_204_NO_CONTENT)
def delete_qr() -> Response:
    donate.delete_qr()  # không có ảnh cũng không sao: kết quả cuối cùng vẫn là "không còn ảnh"
    return Response(status_code=status.HTTP_204_NO_CONTENT)
