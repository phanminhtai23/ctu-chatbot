"""Lưu file người dùng trên Cloudinary qua REST API có ký (không cần thêm thư viện, chỉ dùng `requests`).

Có hai cách phân phối: `upload` (công khai: ảnh đại diện) và `authenticated` (URL có chữ ký, không đoán được: PDF/ảnh tải lên).
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Protocol

import requests
from fastapi import HTTPException, status

from app.core.config import settings

TIMEOUT_SECONDS = 60


class StorageError(Exception):
    """Cloudinary từ chối hoặc không kết nối được."""


@dataclass(frozen=True)
class StoredFile:
    public_id: str
    url: str
    resource_type: str
    delivery_type: str
    size_bytes: int


class CloudStorage(Protocol):
    def upload(self, data: bytes, *, filename: str, folder: str, resource_type: str, delivery_type: str) -> StoredFile: ...

    def delete(self, public_id: str, *, resource_type: str, delivery_type: str) -> None: ...


class CloudinaryStorage:
    def __init__(self, cloud_name: str, api_key: str, api_secret: str, root_folder: str):
        self._cloud = cloud_name
        self._key = api_key
        self._secret = api_secret
        self._root = root_folder.strip("/")

    def _sign(self, params: dict) -> str:
        payload = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v not in ("", None))
        return hashlib.sha1((payload + self._secret).encode()).hexdigest()

    def _post(self, resource_type: str, action: str, params: dict, files: dict | None = None) -> dict:
        body = {**params, "api_key": self._key, "signature": self._sign(params)}
        try:
            res = requests.post(
                f"https://api.cloudinary.com/v1_1/{self._cloud}/{resource_type}/{action}",
                data=body,
                files=files,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise StorageError(f"cannot reach Cloudinary: {type(exc).__name__}") from exc
        if res.status_code != 200:
            raise StorageError(f"Cloudinary {res.status_code}: {res.text[:200]}")
        return res.json()

    def upload(self, data: bytes, *, filename: str, folder: str, resource_type: str, delivery_type: str) -> StoredFile:
        params = {
            "timestamp": int(time.time()),
            "folder": f"{self._root}/{folder}".strip("/"),
            "type": delivery_type,
        }
        result = self._post(resource_type, "upload", params, files={"file": (filename, data)})
        return StoredFile(
            public_id=result["public_id"],
            url=result["secure_url"],
            resource_type=resource_type,
            delivery_type=delivery_type,
            size_bytes=int(result.get("bytes", len(data))),
        )

    def delete(self, public_id: str, *, resource_type: str, delivery_type: str) -> None:
        params = {"timestamp": int(time.time()), "public_id": public_id, "type": delivery_type, "invalidate": "true"}
        result = self._post(resource_type, "destroy", params)
        if result.get("result") not in ("ok", "not found"):
            raise StorageError(f"unexpected destroy result: {result}")


class UnconfiguredStorage:
    """Chưa điền thông tin Cloudinary: tải lên báo 503; xoá thì báo lỗi nhẹ (các chỗ gọi đã bỏ qua lỗi xoá)."""

    def upload(self, data: bytes, *, filename: str, folder: str, resource_type: str, delivery_type: str) -> StoredFile:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="STORAGE_NOT_CONFIGURED")

    def delete(self, public_id: str, *, resource_type: str, delivery_type: str) -> None:
        raise StorageError("Cloudinary is not configured")


_storage: CloudinaryStorage | None = None


def get_storage() -> CloudStorage:
    """FastAPI dependency (tests thay bằng bản giả qua dependency_overrides)."""
    global _storage
    if not settings.cloudinary_configured:
        return UnconfiguredStorage()
    if _storage is None:
        _storage = CloudinaryStorage(
            settings.cloudinary_cloud_name,
            settings.cloudinary_api_key,
            settings.cloudinary_api_secret,
            settings.cloudinary_folder,
        )
    return _storage


def avatar_delivery_url(url: str) -> str:
    """Ảnh đại diện công khai: nhờ Cloudinary cắt vuông 256px, nén gọn (không tải nguyên ảnh vài MB mỗi lần hiển thị)."""
    marker = "/image/upload/"
    return url.replace(marker, f"{marker}c_fill,g_auto,w_256,h_256,f_auto,q_auto/", 1) if marker in url else url
