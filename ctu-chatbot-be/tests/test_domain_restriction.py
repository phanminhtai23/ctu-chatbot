import pytest

from app.api.v1 import auth as auth_module
from app.core.config import settings
from app.models import User
from app.services.google_auth import GoogleIdentity

GMAIL = "someone@gmail.com"


@pytest.fixture()
def google_enabled(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")


def _google_login(client, monkeypatch, email):
    identity = GoogleIdentity(email=email, name="X", picture=None)
    monkeypatch.setattr(auth_module, "verify_google_id_token", lambda credential: identity)
    return client.post("/api/v1/auth/google", json={"credential": "t"})


def _open_mode(monkeypatch):
    monkeypatch.setattr(settings, "allowed_email_domains", [])


def _restricted_mode(monkeypatch):
    monkeypatch.setattr(settings, "allowed_email_domains", ["ctu.edu.vn", "edu.ctu.vn"])


def test_restricted_mode_blocks_new_non_ctu_account(client, google_enabled, monkeypatch):
    assert _google_login(client, monkeypatch, GMAIL).status_code == 403


def test_tightening_blocks_existing_non_admin_login_and_old_token(client, google_enabled, monkeypatch):
    _open_mode(monkeypatch)
    res = _google_login(client, monkeypatch, GMAIL)
    assert res.status_code == 200
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/api/v1/me", headers=headers).status_code == 200

    _restricted_mode(monkeypatch)  # tắt chế độ mở
    assert _google_login(client, monkeypatch, GMAIL).status_code == 403
    assert client.get("/api/v1/me", headers=headers).status_code == 403  # token cũ cũng mất hiệu lực


def test_admin_is_exempt_from_domain_restriction(client, google_enabled, session_factory, monkeypatch):
    _open_mode(monkeypatch)
    token = _google_login(client, monkeypatch, GMAIL).json()["access_token"]
    with session_factory() as db:
        db.query(User).filter(User.email == GMAIL).update({"role": "admin"})
        db.commit()

    _restricted_mode(monkeypatch)
    res = _google_login(client, monkeypatch, GMAIL)
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "admin"
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_ctu_account_still_allowed_when_restricted(client, google_enabled, monkeypatch):
    res = _google_login(client, monkeypatch, "b2100001@student.ctu.edu.vn")
    assert res.status_code == 200
