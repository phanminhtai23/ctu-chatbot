import io
from pathlib import Path

from PIL import Image

from app.core.config import settings


def _image(fmt: str, size: tuple[int, int] = (40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


PNG = _image("PNG")
JPG = _image("JPEG")
WEBP = _image("WEBP")
GIF = _image("GIF")
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

QR = "/api/v1/donate/qr"
INFO = "/api/v1/donate"
ADMIN_QR = "/api/v1/admin/donate/qr"


def put(client, headers, data: bytes, content_type: str = "image/png"):
    return client.put(ADMIN_QR, headers={**headers, "Content-Type": content_type}, content=data)


def files_in_storage() -> list[str]:
    directory = Path(settings.donate_dir)
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


def test_no_qr_by_default_and_anyone_can_ask(client):
    assert client.get(INFO).json() == {"has_qr": False, "version": None}
    assert client.get(QR).status_code == 404


def test_only_admin_can_upload_or_delete(client, auth_headers):
    assert client.put(ADMIN_QR, content=PNG).status_code == 401
    assert put(client, auth_headers, PNG).status_code == 403
    assert client.delete(ADMIN_QR).status_code == 401
    assert client.delete(ADMIN_QR, headers=auth_headers).status_code == 403
    assert client.get(INFO).json()["has_qr"] is False


def test_admin_uploads_and_everyone_can_view_it(client, admin_headers):
    res = put(client, admin_headers, PNG)
    assert res.status_code == 200
    assert res.json()["has_qr"] is True
    assert res.json()["version"]

    assert client.get(INFO).json() == res.json()  # người chưa đăng nhập cũng thấy
    image = client.get(QR)  # không cần đăng nhập: thẻ <img> không gửi được Authorization
    assert image.status_code == 200
    assert image.content == PNG
    assert image.headers["content-type"] == "image/png"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert image.headers["etag"]


def test_conditional_request_gets_304(client, admin_headers):
    put(client, admin_headers, PNG)
    etag = client.get(QR).headers["etag"]
    again = client.get(QR, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert client.get(QR, headers={"If-None-Match": '"something-else"'}).status_code == 200


def test_replacing_with_another_format_leaves_a_single_file(client, admin_headers):
    first = put(client, admin_headers, PNG).json()["version"]
    assert files_in_storage() == ["qr.png"]

    second = put(client, admin_headers, JPG, "image/jpeg").json()["version"]
    assert second != first  # đổi ảnh thì phiên bản đổi, FE không dùng ảnh cũ trong cache
    assert files_in_storage() == ["qr.jpg"]
    image = client.get(QR)
    assert image.headers["content-type"] == "image/jpeg"
    assert image.content == JPG

    put(client, admin_headers, WEBP, "image/webp")
    assert files_in_storage() == ["qr.webp"]
    assert client.get(QR).headers["content-type"] == "image/webp"


def test_image_type_comes_from_the_content_not_the_header(client, admin_headers):
    # Trình duyệt/hệ điều hành có thể gửi sai Content-Type; kiểu thật lấy từ nội dung file.
    assert put(client, admin_headers, PNG, "application/octet-stream").status_code == 200
    assert client.get(QR).headers["content-type"] == "image/png"


def test_rejects_things_that_are_not_valid_images(client, admin_headers):
    truncated_png = PNG[: len(PNG) // 2]
    for name, body in {
        "svg": SVG,
        "gif": GIF,
        "random": b"not an image at all" * 20,
        "empty": b"",
        "truncated": truncated_png,
        "html": b"<html><body>hi</body></html>",
    }.items():
        res = put(client, admin_headers, body, "image/png")
        assert (name, res.status_code, res.json()["detail"]) == (name, 400, "INVALID_IMAGE")
    assert client.get(INFO).json()["has_qr"] is False
    assert files_in_storage() == []


def test_rejects_files_that_are_too_large(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "donate_qr_max_mb", 0.0001)  # ~100 byte
    res = put(client, admin_headers, PNG)
    assert (res.status_code, res.json()["detail"]) == (413, "IMAGE_TOO_LARGE")
    assert client.get(INFO).json()["has_qr"] is False


def test_rejects_images_with_huge_dimensions(client, admin_headers):
    wide = _image("PNG", (4097, 1))  # file nhỏ nhưng ảnh rộng bất thường
    res = put(client, admin_headers, wide)
    assert (res.status_code, res.json()["detail"]) == (400, "INVALID_IMAGE")


def test_failed_upload_keeps_the_existing_qr(client, admin_headers):
    put(client, admin_headers, PNG)
    assert put(client, admin_headers, SVG).status_code == 400
    assert client.get(QR).content == PNG
    assert files_in_storage() == ["qr.png"]  # không để lại file tạm


def test_delete_removes_the_qr_and_is_idempotent(client, admin_headers):
    put(client, admin_headers, PNG)
    assert client.delete(ADMIN_QR, headers=admin_headers).status_code == 204
    assert client.get(INFO).json() == {"has_qr": False, "version": None}
    assert client.get(QR).status_code == 404
    assert files_in_storage() == []
    assert client.delete(ADMIN_QR, headers=admin_headers).status_code == 204
