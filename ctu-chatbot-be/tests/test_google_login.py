import pytest

from app.api.v1 import auth as auth_module
from app.core.config import settings
from app.services.google_auth import GoogleAuthError, GoogleIdentity


@pytest.fixture()
def google_enabled(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")


def _fake_verifier(identity: GoogleIdentity | None):
    def verify(credential: str) -> GoogleIdentity:
        if identity is None:
            raise GoogleAuthError("Invalid Google token")
        return identity

    return verify


def test_google_login_not_configured(client):
    res = client.post("/api/v1/auth/google", json={"credential": "x"})
    assert res.status_code == 503


def test_google_login_creates_user_with_role_user(client, google_enabled, monkeypatch):
    identity = GoogleIdentity(
        email="b2100001@student.ctu.edu.vn", name="Nguyen Van A", picture="https://pic/a.png"
    )
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_verifier(identity))

    res = client.post("/api/v1/auth/google", json={"credential": "token"})
    assert res.status_code == 200
    user = res.json()["user"]
    assert user["email"] == "b2100001@student.ctu.edu.vn"
    assert user["name"] == "Nguyen Van A"
    assert user["avatar_url"] == "https://pic/a.png"  # ảnh Google gốc là ảnh mặc định
    assert user["role"] == "user"
    assert res.json()["access_token"]


def test_google_login_keeps_existing_profile_and_role(client, session_factory, google_enabled, monkeypatch):
    identity = GoogleIdentity(email="b2100001@student.ctu.edu.vn", name="Google Name", picture=None)
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_verifier(identity))
    first = client.post("/api/v1/auth/google", json={"credential": "t"}).json()
    headers = {"Authorization": f"Bearer {first['access_token']}"}
    client.patch("/api/v1/me", headers=headers, json={"name": "Tên Tôi Tự Đặt"})

    from app.models import User

    with session_factory() as db:
        db.query(User).update({"role": "admin"})
        db.commit()

    second = client.post("/api/v1/auth/google", json={"credential": "t"}).json()
    assert second["user"]["id"] == first["user"]["id"]
    assert second["user"]["name"] == "Tên Tôi Tự Đặt"  # không bị Google ghi đè
    assert second["user"]["role"] == "admin"  # đăng nhập lại không hạ quyền


def test_google_login_invalid_token(client, google_enabled, monkeypatch):
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_verifier(None))
    assert client.post("/api/v1/auth/google", json={"credential": "bad"}).status_code == 401


def test_google_login_rejects_other_domain(client, google_enabled, monkeypatch):
    identity = GoogleIdentity(email="someone@gmail.com", name="X", picture=None)
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_verifier(identity))
    assert client.post("/api/v1/auth/google", json={"credential": "t"}).status_code == 403


def test_empty_allowed_domains_lets_any_email_in(client, google_enabled, monkeypatch):
    monkeypatch.setattr(settings, "allowed_email_domains", [])
    identity = GoogleIdentity(email="someone@gmail.com", name="X", picture=None)
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_verifier(identity))
    res = client.post("/api/v1/auth/google", json={"credential": "t"})
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "user"


def test_verify_rejects_unconfigured_client_id():
    from app.services.google_auth import verify_google_id_token

    with pytest.raises(GoogleAuthError):
        verify_google_id_token("anything")


def test_default_avatar_is_the_google_picture_and_the_button_returns_to_it(client, google_enabled, monkeypatch):
    identity = GoogleIdentity(email="b2100001@student.ctu.edu.vn", name="A", picture="https://lh3.googleusercontent.com/a/me")
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_verifier(identity))
    headers = {"Authorization": "Bearer " + client.post("/api/v1/auth/google", json={"credential": "t"}).json()["access_token"]}
    assert client.get("/api/v1/me", headers=headers).json()["avatar_url"] == "https://lh3.googleusercontent.com/a/me"

    rolled = client.delete("/api/v1/me/avatar", headers=headers).json()["avatar_url"]  # quay ảnh ngẫu nhiên
    assert rolled.startswith("https://api.dicebear.com/")
    back = client.delete("/api/v1/me/avatar", params={"random": "false"}, headers=headers)
    assert back.json()["avatar_url"] == "https://lh3.googleusercontent.com/a/me"  # "Mặc định" về lại ảnh Google, không mất


def test_google_picture_is_refreshed_on_every_login_and_kept_when_google_sends_none(client, google_enabled, monkeypatch):
    def login(picture):
        identity = GoogleIdentity(email="b2100001@student.ctu.edu.vn", name="A", picture=picture)
        monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_verifier(identity))
        token = client.post("/api/v1/auth/google", json={"credential": "t"}).json()["access_token"]
        return client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()["avatar_url"]

    assert login("https://pic/1.png") == "https://pic/1.png"
    assert login("https://pic/2.png") == "https://pic/2.png"  # Google đổi ảnh -> ảnh mặc định đổi theo
    assert login(None) == "https://pic/2.png"  # lần này Google không gửi ảnh: giữ ảnh đã biết
