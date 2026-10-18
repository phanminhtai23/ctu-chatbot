def _create_feedback(client, headers, **overrides):
    body = {"type": "general", "category": "bug", "message": "Lỗi tải file"}
    body.update(overrides)
    res = client.post("/api/v1/feedback", headers=headers, json=body)
    assert res.status_code == 201
    return res.json()["id"]


def test_admin_endpoints_require_auth(client):
    assert client.get("/api/v1/admin/feedback").status_code == 401


def test_admin_endpoints_forbidden_for_regular_user(client, auth_headers):
    assert client.get("/api/v1/admin/feedback", headers=auth_headers).status_code == 403
    res = client.patch(
        "/api/v1/admin/feedback/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
        json={"status": "resolved"},
    )
    assert res.status_code == 403


def test_me_exposes_role(client, auth_headers, admin_headers):
    assert client.get("/api/v1/me", headers=auth_headers).json()["role"] == "user"
    assert client.get("/api/v1/me", headers=admin_headers).json()["role"] == "admin"


def test_admin_lists_feedback_newest_first_with_user_email(client, auth_headers, admin_headers):
    first = _create_feedback(client, auth_headers, message="cũ")
    second = _create_feedback(client, auth_headers, message="mới")

    res = client.get("/api/v1/admin/feedback", headers=admin_headers)
    assert res.status_code == 200
    items = res.json()
    assert {i["id"] for i in items} == {first, second}
    assert all(i["user_email"] == "b2100001@student.ctu.edu.vn" for i in items)
    assert all(i["status"] == "new" for i in items)


def test_unread_count_only_counts_new_and_is_admin_only(client, auth_headers, admin_headers):
    url = "/api/v1/admin/feedback/unread-count"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth_headers).status_code == 403
    assert client.get(url, headers=admin_headers).json() == {"count": 0}

    a = _create_feedback(client, auth_headers)
    _create_feedback(client, auth_headers)
    assert client.get(url, headers=admin_headers).json() == {"count": 2}

    client.patch(f"/api/v1/admin/feedback/{a}", headers=admin_headers, json={"status": "reviewed"})
    assert client.get(url, headers=admin_headers).json() == {"count": 1}


def test_admin_updates_status(client, auth_headers, admin_headers):
    fid = _create_feedback(client, auth_headers)

    res = client.patch(f"/api/v1/admin/feedback/{fid}", headers=admin_headers, json={"status": "resolved"})
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"

    items = client.get("/api/v1/admin/feedback", headers=admin_headers).json()
    assert items[0]["status"] == "resolved"


def test_admin_update_rejects_bad_status_and_unknown_id(client, auth_headers, admin_headers):
    fid = _create_feedback(client, auth_headers)
    assert (
        client.patch(f"/api/v1/admin/feedback/{fid}", headers=admin_headers, json={"status": "done"}).status_code
        == 422
    )
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        client.patch(f"/api/v1/admin/feedback/{missing}", headers=admin_headers, json={"status": "new"}).status_code
        == 404
    )
