from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import Settings, settings
from app.core.security import hash_refresh_token
from app.models import RefreshToken

EMAIL = "b2100001@student.ctu.edu.vn"


def _login(client) -> dict:
    res = client.post("/api/v1/auth/dev-login", json={"email": EMAIL})
    assert res.status_code == 200
    return res.json()


def _refresh(client, token):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


def _bearer(access_token):
    return {"Authorization": f"Bearer {access_token}"}


def test_default_lifetimes_are_7_days_and_30_days():
    assert Settings.model_fields["access_token_expire_minutes"].default == 7 * 24 * 60
    assert Settings.model_fields["refresh_token_expire_days"].default == 30


def test_login_returns_both_tokens_with_right_lifetimes(client, session_factory):
    tokens = _login(client)
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["access_token"] != tokens["refresh_token"]

    claims = jwt.decode(tokens["access_token"], settings.secret_key, algorithms=["HS256"])
    access_ttl = datetime.fromtimestamp(claims["exp"], timezone.utc) - datetime.now(timezone.utc)
    assert abs(access_ttl - timedelta(minutes=settings.access_token_expire_minutes)) < timedelta(minutes=1)

    with session_factory() as db:
        row = db.query(RefreshToken).one()
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        refresh_ttl = expires - datetime.now(timezone.utc)
    assert abs(refresh_ttl - timedelta(days=settings.refresh_token_expire_days)) < timedelta(minutes=1)


def test_refresh_token_is_stored_hashed_not_plain(client, session_factory):
    tokens = _login(client)
    with session_factory() as db:
        row = db.query(RefreshToken).one()
        assert row.token_hash == hash_refresh_token(tokens["refresh_token"])
        assert row.token_hash != tokens["refresh_token"]


def test_refresh_rotates_tokens(client):
    first = _login(client)
    res = _refresh(client, first["refresh_token"])
    assert res.status_code == 200
    second = res.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["user"]["email"] == EMAIL
    assert client.get("/api/v1/me", headers=_bearer(second["access_token"])).status_code == 200


def test_refresh_token_is_single_use(client):
    first = _login(client)
    assert _refresh(client, first["refresh_token"]).status_code == 200
    assert _refresh(client, first["refresh_token"]).status_code == 401


def test_reusing_an_old_token_after_grace_revokes_every_session(client, session_factory):
    first = _login(client)
    second = _refresh(client, first["refresh_token"]).json()

    # Giả lập token cũ đã bị thu hồi từ lâu (ngoài khoảng "đua nhau" 30 giây).
    with session_factory() as db:
        row = db.query(RefreshToken).filter_by(token_hash=hash_refresh_token(first["refresh_token"])).one()
        row.revoked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()

    assert _refresh(client, first["refresh_token"]).status_code == 401
    # Nghi bị đánh cắp -> token hợp lệ hiện tại cũng bị thu hồi.
    assert _refresh(client, second["refresh_token"]).status_code == 401


def test_quick_double_refresh_does_not_kill_the_session(client):
    # Hai tab làm mới cùng lúc: tab thua bị từ chối nhưng phiên của tab thắng vẫn sống.
    first = _login(client)
    winner = _refresh(client, first["refresh_token"]).json()
    assert _refresh(client, first["refresh_token"]).status_code == 401
    assert _refresh(client, winner["refresh_token"]).status_code == 200


def test_refresh_rejects_unknown_and_expired_tokens(client, session_factory):
    assert _refresh(client, "not-a-real-token").status_code == 401

    tokens = _login(client)
    with session_factory() as db:
        row = db.query(RefreshToken).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert _refresh(client, tokens["refresh_token"]).status_code == 401


def test_expired_access_token_is_rejected_but_refresh_recovers(client):
    tokens = _login(client)
    expired = jwt.encode(
        {"sub": tokens["user"]["id"], "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm="HS256",
    )
    assert client.get("/api/v1/me", headers=_bearer(expired)).status_code == 401

    fresh = _refresh(client, tokens["refresh_token"]).json()
    assert client.get("/api/v1/me", headers=_bearer(fresh["access_token"])).status_code == 200


def test_logout_revokes_refresh_token(client):
    tokens = _login(client)
    res = client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 204
    assert _refresh(client, tokens["refresh_token"]).status_code == 401
    # Idempotent: đăng xuất lần nữa / với token lạ không lỗi.
    assert client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/logout", json={"refresh_token": "nope"}).status_code == 204


def test_refresh_denied_for_disabled_user(client, session_factory):
    from app.models import User

    tokens = _login(client)
    with session_factory() as db:
        db.query(User).update({"is_active": False})
        db.commit()
    assert _refresh(client, tokens["refresh_token"]).status_code == 403


def test_refresh_denied_when_domain_no_longer_allowed(client, session_factory, monkeypatch):
    tokens = _login(client)
    monkeypatch.setattr(settings, "allowed_email_domains", ["other.example"])
    assert _refresh(client, tokens["refresh_token"]).status_code == 403
