from app.core.config import settings


def test_dev_login_creates_user_with_default_settings(client):
    res = client.post("/api/v1/auth/dev-login", json={"email": "B2100001@Student.CTU.edu.vn"})
    assert res.status_code == 200
    user = res.json()["user"]
    assert user["email"] == "b2100001@student.ctu.edu.vn"
    assert user["timezone"] == "Asia/Ho_Chi_Minh"
    assert user["language"] == "vi"
    assert user["theme"] == "system"


def test_dev_login_is_idempotent(client):
    body = {"email": "b2100001@student.ctu.edu.vn"}
    first = client.post("/api/v1/auth/dev-login", json=body).json()["user"]["id"]
    second = client.post("/api/v1/auth/dev-login", json=body).json()["user"]["id"]
    assert first == second


def test_dev_login_rejects_other_domain(client):
    res = client.post("/api/v1/auth/dev-login", json={"email": "someone@gmail.com"})
    assert res.status_code == 403


def test_dev_login_disabled_outside_dev(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    res = client.post("/api/v1/auth/dev-login", json={"email": "b2100001@student.ctu.edu.vn"})
    assert res.status_code == 404


def test_me_requires_auth(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_update_me_persists_profile_and_preferences(client, auth_headers):
    res = client.patch(
        "/api/v1/me",
        headers=auth_headers,
        json={
            "name": "  Nguyen Van A ",
            "birthday": "2003-05-17",
            "timezone": "America/New_York",
            "language": "en",
            "theme": "dark",
        },
    )
    assert res.status_code == 200
    # Đọc lại từ DB qua request mới để chắc chắn đã lưu.
    me = client.get("/api/v1/me", headers=auth_headers).json()
    assert me["name"] == "Nguyen Van A"
    assert me["birthday"] == "2003-05-17"
    assert me["timezone"] == "America/New_York"
    assert me["language"] == "en"
    assert me["theme"] == "dark"


def test_update_me_is_partial(client, auth_headers):
    client.patch("/api/v1/me", headers=auth_headers, json={"language": "en", "theme": "dark"})
    client.patch("/api/v1/me", headers=auth_headers, json={"name": "Only Name"})
    me = client.get("/api/v1/me", headers=auth_headers).json()
    assert me["name"] == "Only Name"
    assert me["language"] == "en"
    assert me["theme"] == "dark"


def test_update_me_can_clear_birthday(client, auth_headers):
    client.patch("/api/v1/me", headers=auth_headers, json={"birthday": "2003-05-17"})
    client.patch("/api/v1/me", headers=auth_headers, json={"birthday": None})
    assert client.get("/api/v1/me", headers=auth_headers).json()["birthday"] is None


def test_update_me_rejects_invalid_values(client, auth_headers):
    for bad in (
        {"timezone": "Mars/Olympus"},
        {"language": "fr"},
        {"theme": "blue"},
        {"birthday": "2999-01-01"},
        {"name": "x" * 101},
    ):
        res = client.patch("/api/v1/me", headers=auth_headers, json=bad)
        assert res.status_code == 422, bad
