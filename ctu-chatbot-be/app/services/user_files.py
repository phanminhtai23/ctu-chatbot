"""Quy tắc cho file người dùng tải lên: kiểm tra loại file, dung lượng, hạn mức cá nhân."""

import re
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.avatar import random_avatar_url
from app.core.config import settings
from app.models import User, UserFile
from app.services import donate
from app.services.storage import CloudStorage, StorageError, avatar_delivery_url

MB = 1024 * 1024


class UploadRejected(Exception):
    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def quota_bytes() -> int:
    return int(settings.user_storage_quota_mb * MB)


def max_upload_bytes() -> int:
    return int(settings.user_upload_max_mb * MB)


def used_bytes(db: Session, user_id: uuid.UUID) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(UserFile.size_bytes), 0)).where(UserFile.user_id == user_id)) or 0)


def clean_filename(name: str | None, fallback: str) -> str:
    name = re.split(r"[\\/]", (name or "").strip())[-1]
    name = re.sub(r"[\x00-\x1f]", "", name)[:150].strip()
    return name or fallback


def sniff(data: bytes, *, allow_pdf: bool) -> tuple[str, str]:
    """(mime, kiểu Cloudinary 'image' | 'raw') theo NỘI DUNG file. Chỉ nhận PNG/JPEG/WebP (và PDF khi allow_pdf)."""
    if allow_pdf and data[:5] == b"%PDF-":
        return "application/pdf", "raw"
    try:
        _ext, mime = donate.check_image(data)
    except donate.InvalidImage:
        raise UploadRejected(415, "UNSUPPORTED_TYPE") from None
    return mime, "image"


def check_size(size: int) -> None:
    if size == 0:
        raise UploadRejected(400, "EMPTY_FILE")
    if size > max_upload_bytes():
        raise UploadRejected(413, "FILE_TOO_LARGE")


def _upload(storage: CloudStorage, data: bytes, *, filename: str, folder: str, resource_type: str, delivery_type: str):
    try:
        return storage.upload(data, filename=filename, folder=folder, resource_type=resource_type, delivery_type=delivery_type)
    except StorageError:
        raise UploadRejected(502, "STORAGE_ERROR") from None


def _forget(storage: CloudStorage, file: UserFile) -> None:
    """Xoá file trên Cloudinary; lỗi mạng thì bỏ qua (dữ liệu mồ côi tốn chỗ của mình chứ không tốn hạn mức của người dùng)."""
    try:
        storage.delete(file.public_id, resource_type=file.resource_type, delivery_type=file.delivery_type)
    except StorageError:
        pass


def add_attachment(db: Session, storage: CloudStorage, user: User, data: bytes, name: str | None) -> UserFile:
    check_size(len(data))
    mime, resource_type = sniff(data, allow_pdf=True)
    if used_bytes(db, user.id) + len(data) > quota_bytes():
        raise UploadRejected(413, "QUOTA_EXCEEDED")
    filename = clean_filename(name, "tep.pdf" if mime == "application/pdf" else "anh")
    stored = _upload(
        storage, data, filename=filename, folder=f"files/{user.id}", resource_type=resource_type, delivery_type="authenticated"
    )
    row = UserFile(
        user_id=user.id, kind="attachment", filename=filename, content_type=mime, size_bytes=len(data),
        public_id=stored.public_id, resource_type=resource_type, delivery_type="authenticated", url=stored.url,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_file(db: Session, storage: CloudStorage, file: UserFile) -> None:
    _forget(storage, file)
    db.delete(file)
    db.commit()


def _current_avatar_file(db: Session, user: User) -> UserFile | None:
    return db.scalar(select(UserFile).where(UserFile.user_id == user.id, UserFile.kind == "avatar"))


def set_avatar(db: Session, storage: CloudStorage, user: User, data: bytes, name: str | None) -> User:
    check_size(len(data))
    mime, _ = sniff(data, allow_pdf=False)
    old = _current_avatar_file(db, user)
    if used_bytes(db, user.id) - (old.size_bytes if old else 0) + len(data) > quota_bytes():
        raise UploadRejected(413, "QUOTA_EXCEEDED")
    filename = clean_filename(name, "avatar")
    stored = _upload(storage, data, filename=filename, folder="avatars", resource_type="image", delivery_type="upload")
    row = UserFile(
        user_id=user.id, kind="avatar", filename=filename, content_type=mime, size_bytes=len(data),
        public_id=stored.public_id, resource_type="image", delivery_type="upload", url=stored.url,
    )
    if old is not None:
        _forget(storage, old)
        db.delete(old)
    db.add(row)
    user.avatar_url = avatar_delivery_url(stored.url)
    db.commit()
    db.refresh(user)
    return user


def reset_avatar(db: Session, storage: CloudStorage | None, user: User, *, random_default: bool = True) -> User:
    """Bỏ ảnh đã tải lên (nếu có) và đổi sang một ảnh mặc định ngẫu nhiên mới."""
    old = _current_avatar_file(db, user)
    if old is not None:
        if storage is not None:
            _forget(storage, old)
        db.delete(old)
    user.avatar_url = random_avatar_url() if random_default else None
    db.commit()
    db.refresh(user)
    return user
