"""Nơi lưu các phiên bản tài liệu đã nạp và con trỏ tới phiên bản đang dùng.

    <documents_dir>/
        active.json                  phiên bản đang dùng: {version, collection, filename, activated_at, articles}
        versions/<job_id>/
            source.pdf               PDF admin upload
            ocr.txt                  chữ OCR thô (có dòng "--- Trang N ---")
            clean.md                 văn bản đã chuẩn hóa, mỗi Điều một mục "### Điều N. ..."
            layout.json, pages/      vị trí từng Điều trên ảnh trang (để hiện PDF khi bấm tham chiếu)
            job.json                 trạng thái các bước của lần nạp này

Chưa có `active.json` (chưa từng nạp qua trang admin) thì hệ thống dùng dữ liệu cũ đi kèm repo
(`app/data/qd3266`, `vector-docs/qd3266-clean.md`, collection `qd3266`).
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

from app.core.config import settings

_BACKEND_DIR = Path(__file__).resolve().parents[3]  # .../ctu-chatbot-be
LEGACY_COLLECTION = "qd3266"
LEGACY_DATA_DIR = _BACKEND_DIR / "app" / "data" / "qd3266"


def documents_root() -> Path:
    path = Path(settings.documents_dir)
    return path if path.is_absolute() else _BACKEND_DIR / path


def versions_root() -> Path:
    return documents_root() / "versions"


def version_dir(version: str) -> Path:
    if not version or "/" in version or "\\" in version or version.startswith("."):
        raise ValueError(f"Mã phiên bản không hợp lệ: {version!r}")
    return versions_root() / version


def atomic_write_text(path: Path, text: str) -> None:
    """Ghi file qua file tạm rồi đổi tên: đọc ở thread khác không bao giờ thấy file viết dở."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_active() -> dict | None:
    path = documents_root() / "active.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("version") and data.get("collection") else None


def write_active(info: dict) -> None:
    atomic_write_text(documents_root() / "active.json", json.dumps(info, ensure_ascii=False, indent=1))


def clear_active() -> None:
    (documents_root() / "active.json").unlink(missing_ok=True)


def active_data_dir() -> Path:
    """Thư mục chứa layout.json + pages/ của phiên bản đang dùng."""
    active = read_active()
    if active is None:
        return LEGACY_DATA_DIR
    return version_dir(active["version"])


def active_collection() -> str:
    active = read_active()
    return active["collection"] if active else LEGACY_COLLECTION


def collection_name(version: str) -> str:
    return f"qd3266-{version}"  # mã phiên bản gồm thời gian + đuôi ngẫu nhiên nên không trùng


def prune_versions(keep: set[str], max_total: int) -> list[str]:
    """Giữ `max_total` phiên bản mới nhất (mã phiên bản bắt đầu bằng thời gian nên sắp theo tên là sắp theo thời gian)
    cộng các phiên bản trong `keep`; xoá phần còn lại. Trả về tên đã xoá."""
    root = versions_root()
    if not root.exists():
        return []
    names = sorted((d.name for d in root.iterdir() if d.is_dir()), reverse=True)
    survivors = set(names[: max(1, max_total)]) | keep
    removed = []
    for name in names:
        if name not in survivors:
            shutil.rmtree(root / name, ignore_errors=True)
            removed.append(name)
    return removed
