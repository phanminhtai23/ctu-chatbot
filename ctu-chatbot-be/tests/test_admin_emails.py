"""ADMIN_EMAILS trong .env: đăng nhập bằng email trong danh sách là có quyền admin."""

import pytest

from app.api.v1 import auth as auth_module
from app.core.config import settings
from app.models import User
from app.services.google_auth import GoogleIdentity

BOSS = "boss@gmail.com"  # không thuộc tên miền CTU


def _dev_login(client, email):
    return client.post("/api/v1/auth/dev-login", json={"email": email})


def _role(client, token):
    return client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()["role"]


def test_parsing_accepts_commas_semicolons_spaces_and_case(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", " A@x.com; b@y.com ,C@Z.com ")
    assert settings.admin_email_set == {"a@x.com", "b@y.com", "c@z.com"}
    monkeypatch.setattr(settings, "admin_emails", "")
    assert settings.admin_email_set == frozenset()


def test_new_account_with_listed_email_becomes_admin_even_outside_allowed_domains(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", BOSS)
    res = _dev_login(client, BOSS)
    assert res.status_code == 200
    assert _role(client, res.json()["access_token"]) == "admin"


def test_existing_user_is_promoted_on_next_login(client, session_factory, monkeypatch):
    email = "b2100005@student.ctu.edu.vn"
    first = _dev_login(client, email)
    assert _role(client, first.json()["access_token"]) == "user"

    monkeypatch.setattr(settings, "admin_emails", email)
    second = _dev_login(client, email)
    assert _role(client, second.json()["access_token"]) == "admin"
    with session_factory() as db:
        assert db.query(User).filter(User.email == email).one().role == "admin"


def test_unlisted_outside_domain_account_is_still_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", BOSS)
    assert _dev_login(client, "stranger@gmail.com").status_code == 403


def test_removing_an_email_from_the_list_does_not_demote_the_account(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", BOSS)
    _dev_login(client, BOSS)
    monkeypatch.setattr(settings, "admin_emails", "")
    token = _dev_login(client, BOSS).json()["access_token"]
    assert _role(client, token) == "admin"


def test_disabled_listed_account_is_still_blocked(client, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", BOSS)
    _dev_login(client, BOSS)
    with session_factory() as db:
        db.query(User).filter(User.email == BOSS).update({"is_active": False})
        db.commit()
    assert _dev_login(client, BOSS).status_code == 403


def test_google_login_also_grants_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "admin_emails", BOSS)
    identity = GoogleIdentity(email=BOSS, name="Boss", picture=None)
    monkeypatch.setattr(auth_module, "verify_google_id_token", lambda credential: identity)
    res = client.post("/api/v1/auth/google", json={"credential": "t"})
    assert res.status_code == 200 and _role(client, res.json()["access_token"]) == "admin"
    assert client.get("/api/v1/admin/feedback", headers={"Authorization": f"Bearer {res.json()['access_token']}"}).status_code == 200
