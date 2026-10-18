"""Ảnh QR ủng hộ do admin tải lên, lưu thành một file trên đĩa server (cùng kiểu với tài liệu quy định đã nạp)."""

import io
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.core.config import settings

QR_STEM = "qr"
# Chỉ nhận ảnh raster phổ biến. KHÔNG nhận SVG: file SVG có thể chứa script, mở trực tiếp từ domain API sẽ chạy được.
_FORMATS: dict[str, tuple[str, str]] = {  # định dạng Pillow -> (đuôi file, mime)
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "WEBP": ("webp", "image/webp"),
}
_EXTENSIONS = [ext for ext, _ in _FORMATS.values()]
MAX_SIDE_PX = 4096  # QR không cần ảnh lớn hơn; cũng chặn ảnh "bom" giải nén


class InvalidImage(Exception):
    """File không phải ảnh PNG/JPEG/WebP hợp lệ."""


@dataclass
class QrInfo:
    path: Path
    mime: str
    version: str  # đổi mỗi khi thay ảnh: FE đưa vào URL để trình duyệt không dùng ảnh cũ trong cache


def _dir() -> Path:
    return Path(settings.donate_dir)


def _mime_for(ext: str) -> str:
    return next(mime for e, mime in _FORMATS.values() if e == ext)


def check_image(data: bytes) -> tuple[str, str]:
    """Xác thực `data` là ảnh thật giải mã được. Trả về (đuôi file, mime). Kiểu ảnh lấy từ NỘI DUNG, không tin tên file/header."""
    if not data:
        raise InvalidImage("empty")
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format or ""
            width, height = img.size
            if fmt not in _FORMATS:
                raise InvalidImage(f"unsupported format {fmt or 'unknown'}")
            if width > MAX_SIDE_PX or height > MAX_SIDE_PX:
                raise InvalidImage("image too large in pixels")
            img.verify()  # phát hiện file bị cắt cụt / hỏng
    except InvalidImage:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow ném nhiều loại lỗi khác nhau (OSError, SyntaxError, EOFError...) với file hỏng
        raise InvalidImage(str(exc)) from exc
    return _FORMATS[fmt]


def current_qr() -> QrInfo | None:
    directory = _dir()
    for ext in _EXTENSIONS:
        path = directory / f"{QR_STEM}.{ext}"
        if path.is_file():
            stat = path.stat()
            return QrInfo(path=path, mime=_mime_for(ext), version=f"{stat.st_mtime_ns:x}-{stat.st_size:x}")
    return None


def save_qr(data: bytes) -> QrInfo:
    """Kiểm tra rồi ghi ảnh mới thay ảnh cũ. Ghi qua file tạm + `os.replace` nên không bao giờ để lại ảnh ghi dở."""
    ext, _mime = check_image(data)
    directory = _dir()
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f".{QR_STEM}-{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_bytes(data)
        os.replace(tmp, directory / f"{QR_STEM}.{ext}")
    finally:
        tmp.unlink(missing_ok=True)
    for other in _EXTENSIONS:  # đổi định dạng (png -> jpg) thì xoá file cũ để chỉ còn một ảnh
        if other != ext:
            (directory / f"{QR_STEM}.{other}").unlink(missing_ok=True)
    info = current_qr()
    assert info is not None
    return info


def delete_qr() -> bool:
    """Xoá ảnh QR. Trả về True nếu trước đó có ảnh."""
    removed = False
    for ext in _EXTENSIONS:
        path = _dir() / f"{QR_STEM}.{ext}"
        if path.is_file():
            path.unlink()
            removed = True
    return removed
