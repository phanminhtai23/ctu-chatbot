"""Chia sẻ cuộc trò chuyện: theo email, theo liên kết, quyền xem / chat tiếp."""

import json
import uuid

import pytest

from app.models import ConversationShare
from app.services.chat.queue import conversation_guard
from tests.test_streaming import parse_sse

OWNER = "b2100001@student.ctu.edu.vn"
FRIEND = "b2100002@student.ctu.edu.vn"
THIRD = "b2100003@student.ctu.edu.vn"


def _login(client, email):
    res = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture()
def friend(client):
    return _login(client, FRIEND)


@pytest.fixture()
def third(client):
    return _login(client, THIRD)


@pytest.fixture()
def conv(client, auth_headers):
    conv_id = client.post("/api/v1/conversations", headers=auth_headers).json()["id"]
    client.post(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers, json={"content": "Điều 14 nói gì?"})
    return conv_id


def _share(client, headers, conv_id, email, permission="view"):
    return client.post(f"/api/v1/conversations/{conv_id}/shares/people", headers=headers, json={"email": email, "permission": permission})


def _say(client, headers, conv_id, text="mình hỏi thêm"):
    return client.post(f"/api/v1/conversations/{conv_id}/messages", headers=headers, json={"content": text})


# ---- chia sẻ theo email ----


def test_nothing_is_visible_to_others_before_sharing(client, conv, friend):
    assert client.get(f"/api/v1/conversations/{conv}", headers=friend).status_code == 404
    assert client.get("/api/v1/shares/with-me", headers=friend).json() == []


def test_read_only_share_lets_the_friend_view_but_not_chat(client, auth_headers, conv, friend):
    assert _share(client, auth_headers, conv, FRIEND, "view").status_code == 200
    detail = client.get(f"/api/v1/conversations/{conv}", headers=friend).json()
    assert detail["access"] == "view" and len(detail["messages"]) == 2 and detail["owner_name"] == "b2100001"
    res = _say(client, friend, conv)
    assert res.status_code == 403 and res.json()["detail"] == "READ_ONLY"
    assert client.post(f"/api/v1/conversations/{conv}/messages/stream", headers=friend, json={"content": "x"}).status_code == 403
    assert len(client.get(f"/api/v1/conversations/{conv}", headers=auth_headers).json()["messages"]) == 2


def test_chat_share_lets_the_friend_continue_and_marks_the_author(client, auth_headers, conv, friend):
    _share(client, auth_headers, conv, FRIEND, "chat")
    assert client.get(f"/api/v1/conversations/{conv}", headers=friend).json()["access"] == "chat"
    res = _say(client, friend, conv, "Bạn của chủ hỏi: Điều 24 là gì?")
    assert res.status_code == 200 and res.json()["user_message"]["author_name"] == "b2100002"

    history = client.get(f"/api/v1/conversations/{conv}", headers=auth_headers).json()["messages"]
    users = [m for m in history if m["role"] == "user"]
    assert [m["author_name"] for m in users] == [None, "b2100002"]  # tin của chủ không gắn tên


def test_friend_can_stream_and_usage_is_counted_for_the_friend(client, auth_headers, admin_headers, conv, friend):
    _share(client, auth_headers, conv, FRIEND, "chat")
    res = client.post(f"/api/v1/conversations/{conv}/messages/stream", headers=friend, json={"content": "hỏi tiếp"})
    events = parse_sse(res.text)
    assert [e for e, _ in events][0] == "start" and events[-1][0] == "done"
    assert events[0][1]["user_message"]["author_name"] == "b2100002"
    top = client.get("/api/v1/admin/stats", headers=admin_headers).json()["top_users"]
    assert {u["email"] for u in top} == {OWNER, FRIEND}


def test_only_the_owner_can_rename_delete_or_manage_shares(client, auth_headers, conv, friend):
    _share(client, auth_headers, conv, FRIEND, "chat")
    assert client.patch(f"/api/v1/conversations/{conv}", headers=friend, json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/v1/conversations/{conv}", headers=friend).status_code == 404
    assert client.get(f"/api/v1/conversations/{conv}/shares", headers=friend).status_code == 404
    assert _share(client, friend, conv, THIRD).status_code == 404
    assert client.put(f"/api/v1/conversations/{conv}/shares/link", headers=friend, json={"permission": "view"}).status_code == 404


def test_share_validation(client, auth_headers, conv):
    assert _share(client, auth_headers, conv, "khong-phai-email").json()["detail"] == "INVALID_EMAIL"
    assert _share(client, auth_headers, conv, OWNER).json()["detail"] == "CANNOT_SHARE_WITH_SELF"
    assert _share(client, auth_headers, conv, "ai.do@gmail.com").json()["detail"] == "EMAIL_NOT_ALLOWED"
    assert client.post(f"/api/v1/conversations/{conv}/shares/people", headers=auth_headers, json={"email": FRIEND, "permission": "edit"}).status_code == 422


def test_sharing_is_an_upsert_and_email_is_case_insensitive(client, auth_headers, conv, friend):
    _share(client, auth_headers, conv, FRIEND.upper(), "view")
    again = _share(client, auth_headers, conv, FRIEND, "chat").json()
    state = client.get(f"/api/v1/conversations/{conv}/shares", headers=auth_headers).json()
    assert len(state["people"]) == 1 and state["people"][0]["permission"] == "chat" and state["people"][0]["id"] == again["id"]
    assert client.get(f"/api/v1/conversations/{conv}", headers=friend).json()["access"] == "chat"


def test_invite_to_someone_who_has_not_logged_in_yet_works_once_they_do(client, auth_headers, conv):
    res = _share(client, auth_headers, conv, "b2100099@student.ctu.edu.vn", "view")
    assert res.status_code == 200 and res.json()["registered"] is False
    newcomer = _login(client, "b2100099@student.ctu.edu.vn")
    items = client.get("/api/v1/shares/with-me", headers=newcomer).json()
    assert [i["id"] for i in items] == [conv] and items[0]["permission"] == "view" and items[0]["owner_name"] == "b2100001"
    assert client.get(f"/api/v1/conversations/{conv}", headers=newcomer).status_code == 200


def test_change_permission_and_remove_person(client, auth_headers, conv, friend):
    share_id = _share(client, auth_headers, conv, FRIEND, "view").json()["id"]
    url = f"/api/v1/conversations/{conv}/shares/people/{share_id}"
    assert client.patch(url, headers=auth_headers, json={"permission": "chat"}).json()["permission"] == "chat"
    assert _say(client, friend, conv).status_code == 200
    assert client.delete(url, headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/conversations/{conv}", headers=friend).status_code == 404
    assert client.delete(url, headers=auth_headers).status_code == 404


def test_deleting_the_conversation_removes_its_shares(client, auth_headers, conv, friend, session_factory):
    _share(client, auth_headers, conv, FRIEND)
    client.put(f"/api/v1/conversations/{conv}/shares/link", headers=auth_headers, json={"permission": "view"})
    assert client.delete(f"/api/v1/conversations/{conv}", headers=auth_headers).status_code == 204
    with session_factory() as db:
        assert db.query(ConversationShare).count() == 0
    assert client.get("/api/v1/shares/with-me", headers=friend).json() == []


def test_suggestions_search_users_by_email_or_name(client, auth_headers, friend, third):
    got = client.get("/api/v1/shares/suggestions", headers=auth_headers, params={"q": "b21000"}).json()
    assert {u["email"] for u in got} == {FRIEND, THIRD}  # không gồm chính mình
    assert client.get("/api/v1/shares/suggestions", headers=auth_headers, params={"q": "b"}).json() == []  # quá ngắn
    assert client.get("/api/v1/shares/suggestions", headers=auth_headers, params={"q": "b2100003"}).json() == [{"email": THIRD, "name": "b2100003"}]
    assert client.get("/api/v1/shares/suggestions").status_code == 401


def test_two_people_cannot_chat_in_the_same_conversation_at_the_same_time(client, auth_headers, conv, friend):
    _share(client, auth_headers, conv, FRIEND, "chat")
    guard_id = uuid.UUID(conv)
    assert conversation_guard.acquire(guard_id)
    try:
        res = _say(client, friend, conv)
        assert res.status_code == 409 and res.json()["detail"] == "CONVERSATION_BUSY"
        events = parse_sse(client.post(f"/api/v1/conversations/{conv}/messages/stream", headers=friend, json={"content": "x"}).text)
        assert events == [("error", {"code": "CONVERSATION_BUSY"})]
    finally:
        conversation_guard.release(guard_id)
    assert _say(client, friend, conv).status_code == 200  # xong thì chat lại được


# ---- liên kết công khai ----


def _link(client, headers, conv_id, permission="view", **extra):
    res = client.put(f"/api/v1/conversations/{conv_id}/shares/link", headers=headers, json={"permission": permission, **extra})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def test_anyone_with_the_link_can_read_without_logging_in(client, auth_headers, conv):
    token = _link(client, auth_headers, conv)
    res = client.get(f"/api/v1/shared-links/{token}")
    body = res.json()
    assert res.status_code == 200 and len(body["messages"]) == 2 and body["permission"] == "view"
    assert body["can_chat"] is False and body["owner_name"] == "b2100001" and "@" not in json.dumps(body)  # không lộ email
    assert client.get("/api/v1/shared-links/token-sai").status_code == 404


def test_read_only_link_does_not_allow_chatting_even_when_logged_in(client, auth_headers, conv, friend):
    token = _link(client, auth_headers, conv, "view")
    assert client.get(f"/api/v1/shared-links/{token}", headers=friend).json()["can_chat"] is False
    res = client.post(f"/api/v1/shared-links/{token}/messages/stream", headers=friend, json={"content": "x"})
    assert res.status_code == 403 and res.json()["detail"] == "READ_ONLY"


def test_chat_link_needs_login_to_chat(client, auth_headers, conv, friend):
    token = _link(client, auth_headers, conv, "chat")
    assert client.get(f"/api/v1/shared-links/{token}").json()["can_chat"] is False  # khách chỉ đọc
    assert client.post(f"/api/v1/shared-links/{token}/messages/stream", json={"content": "x"}).status_code == 401

    assert client.get(f"/api/v1/shared-links/{token}", headers=friend).json()["can_chat"] is True
    res = client.post(f"/api/v1/shared-links/{token}/messages/stream", headers=friend, json={"content": "mình là người nhận link"})
    events = parse_sse(res.text)
    assert events[-1][0] == "done" and events[0][1]["user_message"]["author_name"] == "b2100002"
    history = client.get(f"/api/v1/conversations/{conv}", headers=auth_headers).json()["messages"]
    assert history[-2]["content"] == "mình là người nhận link" and history[-2]["author_name"] == "b2100002"


def test_owner_chatting_through_their_own_link_is_not_marked_as_a_guest(client, auth_headers, conv):
    token = _link(client, auth_headers, conv, "chat")
    res = client.post(f"/api/v1/shared-links/{token}/messages/stream", headers=auth_headers, json={"content": "chủ hỏi"})
    assert parse_sse(res.text)[0][1]["user_message"]["author_name"] is None


def test_changing_link_permission_keeps_the_link_but_regenerate_replaces_it(client, auth_headers, conv):
    token = _link(client, auth_headers, conv, "view")
    assert _link(client, auth_headers, conv, "chat") == token
    assert client.get(f"/api/v1/shared-links/{token}").json()["permission"] == "chat"
    new_token = _link(client, auth_headers, conv, "chat", regenerate=True)
    assert new_token != token
    assert client.get(f"/api/v1/shared-links/{token}").status_code == 404
    assert client.get(f"/api/v1/shared-links/{new_token}").status_code == 200


def test_turning_the_link_off_revokes_it(client, auth_headers, conv):
    token = _link(client, auth_headers, conv)
    assert client.get(f"/api/v1/conversations/{conv}/shares", headers=auth_headers).json()["link"]["token"] == token
    assert client.delete(f"/api/v1/conversations/{conv}/shares/link", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/shared-links/{token}").status_code == 404
    assert client.get(f"/api/v1/conversations/{conv}/shares", headers=auth_headers).json()["link"] is None


def test_link_with_an_invalid_token_header_is_still_readable_as_a_guest(client, auth_headers, conv):
    token = _link(client, auth_headers, conv)
    res = client.get(f"/api/v1/shared-links/{token}", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 200 and res.json()["can_chat"] is False


def test_a_conversation_shared_by_link_is_not_listed_for_strangers(client, auth_headers, conv, third):
    _link(client, auth_headers, conv)
    assert client.get("/api/v1/shares/with-me", headers=third).json() == []
    assert client.get(f"/api/v1/conversations/{conv}", headers=third).status_code == 404
