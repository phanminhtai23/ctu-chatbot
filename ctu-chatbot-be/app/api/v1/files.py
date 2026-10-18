from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session
import uuid

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, UserFile
from app.schemas.user import UserOut
from app.services import user_files
from app.services.storage import CloudStorage, get_storage

router = APIRouter(prefix="/me", tags=["files"])


def _item(f: UserFile) -> dict:
    return {
        "id": str(f.id),
        "kind": f.kind,
        "filename": f.filename,
        "content_type": f.content_type,
        "size_bytes": f.size_bytes,
        "url": f.url,
        "created_at": f.created_at.isoformat(),
    }


def _listing(db: Session, user: User) -> dict:
    files = db.scalars(select(UserFile).where(UserFile.user_id == user.id).order_by(UserFile.created_at.desc())).all()
    return {
        "items": [_item(f) for f in files],
        "used_bytes": user_files.used_bytes(db, user.id),
        "quota_bytes": user_files.quota_bytes(),
        "max_upload_bytes": user_files.max_upload_bytes(),
    }


async def _read_body(request: Request) -> bytes:
    """Đọc body nhưng dừng ngay khi vượt giới hạn mỗi lần tải (không nạp file khổng lồ vào bộ nhớ)."""
    limit = user_files.max_upload_bytes()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, detail="FILE_TOO_LARGE")
    chunks: list[bytes] = []
    size = 0
    async for part in request.stream():
        size += len(part)
        if size > limit:
            raise HTTPException(413, detail="FILE_TOO_LARGE")
        chunks.append(part)
    return b"".join(chunks)


def _rejected(exc: user_files.UploadRejected) -> HTTPException:
    return HTTPException(exc.status_code, detail=exc.code)


@router.get("/files")
def list_files(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """File đã tải lên + dung lượng đã dùng / tối đa."""
    return _listing(db, user)


@router.post("/files", status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    name: str = Query("", max_length=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: CloudStorage = Depends(get_storage),
) -> dict:
    """Tải PDF hoặc ảnh (PNG/JPEG/WebP) lên. Gửi nguyên file làm body (giống tải ảnh QR); tên file đặt ở `?name=`."""
    data = await _read_body(request)
    try:
        await run_in_threadpool(user_files.add_attachment, db, storage, user, data, name)
    except user_files.UploadRejected as exc:
        raise _rejected(exc) from None
    return await run_in_threadpool(_listing, db, user)


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: CloudStorage = Depends(get_storage),
) -> Response:
    file = db.get(UserFile, file_id)
    if file is None or file.user_id != user.id or file.kind != "attachment":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    user_files.delete_file(db, storage, file)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/avatar", response_model=UserOut)
async def upload_avatar(
    request: Request,
    name: str = Query("", max_length=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: CloudStorage = Depends(get_storage),
):
    """Đổi ảnh đại diện (PNG/JPEG/WebP). Ảnh cũ được xoá; ảnh mới tính vào hạn mức dung lượng."""
    data = await _read_body(request)
    try:
        return await run_in_threadpool(user_files.set_avatar, db, storage, user, data, name)
    except user_files.UploadRejected as exc:
        raise _rejected(exc) from None


@router.delete("/avatar", response_model=UserOut)
def reset_avatar(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: CloudStorage = Depends(get_storage),
):
    """Bỏ ảnh đã tải lên và đổi sang ảnh mặc định ngẫu nhiên khác (gọi lại để "quay" ảnh mới)."""
    return user_files.reset_avatar(db, storage, user)
