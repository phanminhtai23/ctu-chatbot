import hashlib
import io
import uuid

import pytest
from PIL import Image

from app.core.avatar import default_avatar_url
from app.core.config import settings
from app.main import app
from app.models import User
from app.services import storage as storage_module
from app.services.storage import CloudinaryStorage, StorageError, StoredFile, avatar_delivery_url, get_storage

MB = 1024 * 1024


def _image(fmt="PNG", size=(40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 120, 200)).save(buf, fmt)
    return buf.getvalue()


PNG = _image("PNG")
GIF = _image("GIF")
PDF = b"%PDF-1.4\n" + b"x" * 2000 + b"\n%%EOF"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>'


class FakeStorage:
    def __init__(self):
        self.uploaded: list[dict] = []
        self.deleted: list[dict] = []
        self.fail_upload = False

    def upload(self, data, *, filename, folder, resource_type, delivery_type):
        if self.fail_upload:
            raise StorageError("boom")
        public_id = f"{folder}/{uuid.uuid4().hex}"
        self.uploaded.append(
            {"public_id": public_id, "filename": filename, "folder": folder, "size": len(data),
             "resource_type": resource_type, "delivery_type": delivery_type}
        )
        url = f"https://res.cloudinary.com/demo/{resource_type}/{delivery_type}/{public_id}"
        return StoredFile(public_id, url, resource_type, delivery_type, len(data))

    def delete(self, public_id, *, resource_type, delivery_type):
        self.deleted.append({"public_id": public_id, "resource_type": resource_type, "delivery_type": delivery_type})


@pytest.fixture()
def storage(client, monkeypatch):
    monkeypatch.setattr(settings, "user_storage_quota_mb", 20)
    monkeypatch.setattr(settings, "user_upload_max_mb", 5)
    fake = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: fake
    return fake


def _upload(client, headers, data, name="tai-lieu.pdf"):
    return client.post(
        "/api/v1/me/files", params={"name": name}, headers={**headers, "Content-Type": "application/octet-stream"}, content=data
    )


def _avatar(client, headers, data, name="me.png"):
    return client.put("/api/v1/me/avatar", params={"name": name}, headers={**headers, "Content-Type": "image/png"}, content=data)


# ---- tệp tải lên ----


def test_requires_login(client, storage):
    assert client.get("/api/v1/me/files").status_code == 401
    assert client.post("/api/v1/me/files", content=PDF).status_code == 401
    assert client.put("/api/v1/me/avatar", content=PNG).status_code == 401


def test_empty_listing_shows_quota_and_limits(client, storage, auth_headers):
    body = client.get("/api/v1/me/files", headers=auth_headers).json()
    assert body == {"items": [], "used_bytes": 0, "quota_bytes": 20 * MB, "max_upload_bytes": 5 * MB}


def test_upload_pdf_and_image_then_list_and_usage(client, storage, auth_headers):
    assert _upload(client, auth_headers, PDF, "quy-che.pdf").status_code == 201
    body = _upload(client, auth_headers, PNG, "anh.png").json()
    assert sorted(i["filename"] for i in body["items"]) == ["anh.png", "quy-che.pdf"]
    assert body["used_bytes"] == len(PDF) + len(PNG)
    kinds = {i["filename"]: i["content_type"] for i in body["items"]}
    assert kinds == {"quy-che.pdf": "application/pdf", "anh.png": "image/png"}
    pdf_up = next(u for u in storage.uploaded if u["filename"] == "quy-che.pdf")
    assert pdf_up["resource_type"] == "raw" and pdf_up["delivery_type"] == "authenticated"  # URL có chữ ký, không công khai
    assert pdf_up["folder"].startswith("files/")


def test_type_is_decided_by_content_not_by_name(client, storage, auth_headers):
    assert _upload(client, auth_headers, b"just some text, not a pdf", "fake.pdf").status_code == 415
    assert _upload(client, auth_headers, GIF, "anh.gif").status_code == 415
    assert _upload(client, auth_headers, SVG, "x.svg").status_code == 415
    assert _upload(client, auth_headers, b"", "rong.pdf").status_code == 400
    assert storage.uploaded == []


def test_per_upload_size_limit(client, storage, auth_headers):
    res = _upload(client, auth_headers, b"%PDF-" + b"0" * (5 * MB))  # vượt 5 MB
    assert res.status_code == 413 and res.json()["detail"] == "FILE_TOO_LARGE"
    assert _upload(client, auth_headers, b"%PDF-" + b"0" * (5 * MB - 10)).status_code == 201


def test_total_quota_and_deleting_frees_space(client, storage, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "user_storage_quota_mb", 1)
    chunk = b"%PDF-" + b"0" * (400 * 1024)
    ids = [_upload(client, auth_headers, chunk).json()["items"][0]["id"] for _ in range(2)]
    res = _upload(client, auth_headers, chunk)  # 3 x 400KB > 1 MB
    assert res.status_code == 413 and res.json()["detail"] == "QUOTA_EXCEEDED"

    assert client.delete(f"/api/v1/me/files/{ids[0]}", headers=auth_headers).status_code == 204
    assert len(storage.deleted) == 1 and storage.deleted[0]["delivery_type"] == "authenticated"
    assert _upload(client, auth_headers, chunk).status_code == 201


def test_cannot_delete_or_see_other_peoples_files(client, storage, auth_headers):
    token = client.post("/api/v1/auth/dev-login", json={"email": "b2100002@student.ctu.edu.vn"}).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {token}"}
    file_id = _upload(client, other_headers, PDF).json()["items"][0]["id"]

    assert client.get("/api/v1/me/files", headers=auth_headers).json()["items"] == []
    assert client.delete(f"/api/v1/me/files/{file_id}", headers=auth_headers).status_code == 404
    assert client.delete(f"/api/v1/me/files/{uuid.uuid4()}", headers=auth_headers).status_code == 404
    assert storage.deleted == []


def test_storage_failure_saves_nothing(client, storage, auth_headers):
    storage.fail_upload = True
    res = _upload(client, auth_headers, PDF)
    assert res.status_code == 502 and res.json()["detail"] == "STORAGE_ERROR"
    assert client.get("/api/v1/me/files", headers=auth_headers).json()["used_bytes"] == 0


def test_not_configured_returns_503(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "cloudinary_cloud_name", "")
    res = _upload(client, auth_headers, PDF)
    assert res.status_code == 503 and res.json()["detail"] == "STORAGE_NOT_CONFIGURED"


# ---- ảnh đại diện ----


def test_new_user_has_a_default_avatar_even_without_cloud_storage(client, auth_headers, session_factory):
    me = client.get("/api/v1/me", headers=auth_headers).json()
    assert me["avatar_url"].startswith("https://api.dicebear.com/9.x/thumbs/svg?seed=")
    with session_factory() as db:  # tài khoản cũ chưa có ảnh (NULL) vẫn nhận ảnh mặc định ổn định theo id
        user = db.query(User).filter(User.email == "b2100001@student.ctu.edu.vn").one()
        user.avatar_url = None
        db.commit()
        expected = default_avatar_url(str(user.id))
    assert client.get("/api/v1/me", headers=auth_headers).json()["avatar_url"] == expected


def test_upload_avatar_replaces_the_old_one_and_counts_toward_usage(client, storage, auth_headers):
    first = _avatar(client, auth_headers, PNG)
    assert first.status_code == 200
    url = first.json()["avatar_url"]
    assert "res.cloudinary.com" in url and "c_fill" in url and "/avatars" in url

    bigger = _image("PNG", (300, 300))
    second = _avatar(client, auth_headers, bigger)
    assert second.status_code == 200 and second.json()["avatar_url"] != url
    assert len(storage.deleted) == 1 and storage.deleted[0]["delivery_type"] == "upload"  # ảnh cũ bị xoá trên Cloudinary
    listing = client.get("/api/v1/me/files", headers=auth_headers).json()
    assert listing["used_bytes"] == len(bigger) and [i["kind"] for i in listing["items"]] == ["avatar"]


def test_avatar_must_be_an_image(client, storage, auth_headers):
    assert _avatar(client, auth_headers, PDF).status_code == 415
    assert _avatar(client, auth_headers, GIF).status_code == 415


def test_reset_avatar_gives_a_new_random_default_and_frees_the_file(client, storage, auth_headers):
    _avatar(client, auth_headers, PNG)
    res = client.delete("/api/v1/me/avatar", headers=auth_headers)
    assert res.status_code == 200 and res.json()["avatar_url"].startswith("https://api.dicebear.com/")
    assert client.get("/api/v1/me/files", headers=auth_headers).json()["used_bytes"] == 0
    assert len(storage.deleted) == 1
    again = client.delete("/api/v1/me/avatar", headers=auth_headers).json()["avatar_url"]
    assert again != res.json()["avatar_url"]  # mỗi lần "quay" ra một ảnh mới


def test_avatar_cannot_be_deleted_through_the_files_endpoint(client, storage, auth_headers):
    _avatar(client, auth_headers, PNG)
    avatar_id = client.get("/api/v1/me/files", headers=auth_headers).json()["items"][0]["id"]
    assert client.delete(f"/api/v1/me/files/{avatar_id}", headers=auth_headers).status_code == 404


# ---- admin theo dõi dung lượng ----


def test_admin_sees_storage_used_per_user(client, storage, auth_headers, admin_headers):
    _upload(client, auth_headers, PDF)
    _avatar(client, auth_headers, PNG)
    users = client.get("/api/v1/admin/users", headers=admin_headers).json()["items"]
    mine = next(u for u in users if u["email"] == "b2100001@student.ctu.edu.vn")
    assert mine["storage_bytes"] == len(PDF) + len(PNG) and mine["storage_quota_bytes"] == 20 * MB
    other = next(u for u in users if u["email"] == "admin@student.ctu.edu.vn")
    assert other["storage_bytes"] == 0
    detail = client.get(f"/api/v1/admin/users/{mine['id']}", headers=admin_headers).json()
    assert detail["storage_bytes"] == len(PDF) + len(PNG)


# ---- Cloudinary (REST) ----


def test_avatar_delivery_url_adds_a_square_transformation():
    url = "https://res.cloudinary.com/x/image/upload/v1/ctu/avatars/a.png"
    expected = "https://res.cloudinary.com/x/image/upload/c_fill,g_auto,w_256,h_256,f_auto,q_auto/v1/ctu/avatars/a.png"
    assert avatar_delivery_url(url) == expected
    assert avatar_delivery_url("https://other/x.png") == "https://other/x.png"


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload, self.text = status, payload or {}, str(payload)

    def json(self):
        return self._payload


def test_cloudinary_signs_and_sends_the_expected_fields(monkeypatch):
    calls = []

    def fake_post(url, data=None, files=None, timeout=None):
        calls.append((url, data, files))
        return _Resp(
            200,
            {
                "public_id": "root/files/u/abc.pdf",
                "secure_url": "https://res.cloudinary.com/c/raw/authenticated/s--sig--/v1/abc.pdf",
                "bytes": 12,
            },
        )

    monkeypatch.setattr(storage_module.requests, "post", fake_post)
    cloud = CloudinaryStorage("cname", "key123", "secret456", "root/")
    stored = cloud.upload(b"%PDF-data", filename="a.pdf", folder="files/u", resource_type="raw", delivery_type="authenticated")
    assert stored.public_id == "root/files/u/abc.pdf" and stored.size_bytes == 12 and stored.delivery_type == "authenticated"
    url, data, files = calls[0]
    assert url == "https://api.cloudinary.com/v1_1/cname/raw/upload"
    assert data["folder"] == "root/files/u" and data["type"] == "authenticated" and data["api_key"] == "key123"
    assert files["file"][0] == "a.pdf"
    to_sign = f"folder=root/files/u&timestamp={data['timestamp']}&type=authenticated" + "secret456"
    assert data["signature"] == hashlib.sha1(to_sign.encode()).hexdigest()  # sha1(tham số theo thứ tự chữ cái + api_secret)
    assert "secret456" not in str(data)  # api_secret không bao giờ được gửi đi


def test_cloudinary_errors_become_storage_errors(monkeypatch):
    monkeypatch.setattr(storage_module.requests, "post", lambda *a, **k: _Resp(401, {"error": "bad"}))
    cloud = CloudinaryStorage("c", "k", "s", "root")
    with pytest.raises(StorageError):
        cloud.upload(b"x", filename="a", folder="f", resource_type="image", delivery_type="upload")
    with pytest.raises(StorageError):
        cloud.delete("id", resource_type="image", delivery_type="upload")


def test_deleting_an_already_missing_file_is_fine(monkeypatch):
    monkeypatch.setattr(storage_module.requests, "post", lambda *a, **k: _Resp(200, {"result": "not found"}))
    CloudinaryStorage("c", "k", "s", "root").delete("id", resource_type="image", delivery_type="upload")


def test_back_to_the_account_default_avatar_is_stable(client, storage, auth_headers, session_factory):
    with session_factory() as db:
        user = db.query(User).filter(User.email == "b2100001@student.ctu.edu.vn").first()
    me = client.get("/api/v1/me", headers=auth_headers).json()
    initial = me["avatar_url"]
    assert initial == default_avatar_url(me["id"])  # tài khoản mới: ảnh mặc định cố định theo id

    _avatar(client, auth_headers, PNG)
    client.delete("/api/v1/me/avatar", headers=auth_headers)  # quay ngẫu nhiên: ra ảnh khác
    assert client.get("/api/v1/me", headers=auth_headers).json()["avatar_url"] != initial

    _avatar(client, auth_headers, PNG)
    back = client.delete("/api/v1/me/avatar", params={"random": "false"}, headers=auth_headers)
    assert back.status_code == 200 and back.json()["avatar_url"] == initial  # về đúng ảnh mặc định ban đầu
    assert client.get("/api/v1/me/files", headers=auth_headers).json()["used_bytes"] == 0
