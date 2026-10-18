import base64
import io
import json
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from PIL import Image

from app.main import app
from app.schemas.conversation import DEFAULT_ATTACHMENT_PROMPT
from app.services import rate_limit
from app.services.chat import attachments as att
from app.services.chat.graph import ATTACHMENT_INTRO, build_system_prompt
from app.services.rate_limit import MultiWindowLimiter, parse_rate_limits
from app.services.storage import get_storage
from tests.test_user_files import FakeStorage

PDF = b"%PDF-1.4\n" + b"hello pdf " * 100 + b"\n%%EOF"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), (10, 100, 200)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def storage(client, monkeypatch):
    fake = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: fake
    monkeypatch.setattr(att, "fetch_bytes", lambda url: PDF if "raw" in url else _png())
    return fake


def _upload(client, headers, data=PDF, name="tai-lieu.pdf"):
    res = client.post("/api/v1/me/files", params={"name": name}, headers={**headers, "Content-Type": "application/octet-stream"}, content=data)
    assert res.status_code == 201, res.text
    return res.json()["file"]


def _conv(client, headers):
    return client.post("/api/v1/conversations", headers=headers).json()["id"]


def _send(client, headers, conv_id, content, ids=()):
    return client.post(
        f"/api/v1/conversations/{conv_id}/messages", headers=headers, json={"content": content, "attachment_ids": list(ids)}
    )


def test_upload_returns_the_created_file(client, storage, auth_headers):
    file = _upload(client, auth_headers)
    assert file["filename"] == "tai-lieu.pdf" and file["content_type"] == "application/pdf" and file["id"] and file["url"]


def test_the_llm_receives_the_file_but_the_checkpoint_keeps_only_a_reference(client, storage, fake_llm, auth_headers):
    file = _upload(client, auth_headers)
    conv = _conv(client, auth_headers)
    res = _send(client, auth_headers, conv, "Tóm tắt giúp mình", [file["id"]])
    assert res.status_code == 200
    user_msg = res.json()["user_message"]
    assert user_msg["content"] == "Tóm tắt giúp mình"
    assert [a["id"] for a in user_msg["attachments"]] == [file["id"]]
    assert user_msg["attachments"][0]["url"] == file["url"] and user_msg["attachments"][0]["filename"] == "tai-lieu.pdf"

    sent = next(m for m in fake_llm.calls[-1] if isinstance(m, HumanMessage))
    assert isinstance(sent.content, list)
    blocks = {b["type"]: b for b in sent.content}
    assert blocks["file"]["mime_type"] == "application/pdf" and base64.b64decode(blocks["file"]["base64"]) == PDF
    assert "Tóm tắt giúp mình" in blocks["text"]["text"] and "tai-lieu.pdf" in blocks["text"]["text"]

    history = client.get(f"/api/v1/conversations/{conv}", headers=auth_headers).json()["messages"]
    assert history[0]["content"] == "Tóm tắt giúp mình"  # văn bản gốc, không lẫn nội dung tệp
    assert history[0]["attachments"][0]["filename"] == "tai-lieu.pdf" and history[1]["attachments"] == []


def test_images_are_sent_as_image_blocks_and_streaming_works(client, storage, fake_llm, auth_headers):
    file = _upload(client, auth_headers, _png(), "anh.png")
    conv = _conv(client, auth_headers)
    res = client.post(
        f"/api/v1/conversations/{conv}/messages/stream", headers=auth_headers, json={"content": "Ảnh này là gì?", "attachment_ids": [file["id"]]}
    )
    assert res.status_code == 200 and "event: done" in res.text
    start = json.loads(res.text.split("event: start\ndata: ")[1].split("\n")[0])
    assert start["user_message"]["attachments"][0]["filename"] == "anh.png"
    blocks = next(m for m in fake_llm.calls[-1] if isinstance(m, HumanMessage)).content
    image = next(b for b in blocks if b["type"] == "image")
    assert image["mime_type"] == "image/png"


def test_sending_only_a_file_uses_a_default_question(client, storage, fake_llm, auth_headers):
    file = _upload(client, auth_headers)
    conv = _conv(client, auth_headers)
    res = client.post(f"/api/v1/conversations/{conv}/messages", headers=auth_headers, json={"attachment_ids": [file["id"]]})
    assert res.status_code == 200 and res.json()["user_message"]["content"] == DEFAULT_ATTACHMENT_PROMPT
    assert client.post(f"/api/v1/conversations/{conv}/messages", headers=auth_headers, json={"content": "  "}).status_code == 422


def test_only_your_own_attachments_can_be_used(client, storage, auth_headers):
    mine = _upload(client, auth_headers)
    token = client.post("/api/v1/auth/dev-login", json={"email": "b2100002@student.ctu.edu.vn"}).json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    theirs = _upload(client, other)
    conv = _conv(client, auth_headers)

    for bad in (theirs["id"], str(uuid.uuid4())):
        res = _send(client, auth_headers, conv, "hỏi", [bad])
        assert res.status_code == 422 and res.json()["detail"] == "ATTACHMENT_NOT_FOUND"
    assert _send(client, auth_headers, conv, "hỏi", [mine["id"], mine["id"]]).status_code == 200  # trùng id thì chỉ tính một
    assert client.get(f"/api/v1/conversations/{conv}", headers=auth_headers).json()["messages"][0]["attachments"].__len__() == 1


def test_avatar_cannot_be_attached(client, storage, auth_headers):
    client.put("/api/v1/me/avatar", params={"name": "a.png"}, headers={**auth_headers, "Content-Type": "image/png"}, content=_png())
    avatar = client.get("/api/v1/me/files", headers=auth_headers).json()["items"][0]
    assert avatar["kind"] == "avatar"
    res = _send(client, auth_headers, _conv(client, auth_headers), "hỏi", [avatar["id"]])
    assert res.status_code == 422


def test_at_most_three_files_per_message(client, storage, auth_headers):
    ids = [_upload(client, auth_headers, PDF + bytes([i]), f"f{i}.pdf")["id"] for i in range(4)]
    conv = _conv(client, auth_headers)
    assert _send(client, auth_headers, conv, "hỏi", ids).status_code == 422
    assert _send(client, auth_headers, conv, "hỏi", ids[:3]).status_code == 200


def test_a_file_always_goes_to_the_llm_even_for_greetings_and_suggested_questions(client, storage, fake_llm, auth_headers):
    file = _upload(client, auth_headers)
    conv = _conv(client, auth_headers)
    calls = len(fake_llm.calls)
    res = _send(client, auth_headers, conv, "xin chào", [file["id"]])
    assert res.status_code == 200 and len(fake_llm.calls) == calls + 1  # không bị trả lời chào hỏi có sẵn
    assert res.json()["assistant_message"]["cached"] is False
    assert _send(client, auth_headers, conv, "đm mày", [file["id"]]).status_code == 422  # chửi thề vẫn bị chặn


def test_upload_rate_limit(client, storage, auth_headers, monkeypatch):
    monkeypatch.setattr(rate_limit, "upload_limiter", MultiWindowLimiter(parse_rate_limits("2/1m")))
    for i in range(2):
        _upload(client, auth_headers, PDF + bytes([i]), f"{i}.pdf")
    res = client.post("/api/v1/me/files", params={"name": "x.pdf"}, headers={**auth_headers, "Content-Type": "application/octet-stream"}, content=PDF)
    assert res.status_code == 429 and res.json()["detail"] == "UPLOAD_RATE_LIMITED" and int(res.headers["Retry-After"]) >= 1


# ---- build_llm_history ----


def _human(text, *files):
    items = [{"id": f, "filename": f"{f}.pdf", "content_type": "application/pdf", "size_bytes": 10, "url": f"https://x/{f}"} for f in files]
    return HumanMessage(content=text, id=str(uuid.uuid4()), additional_kwargs={"attachments": items} if items else {})


def test_only_the_most_recent_messages_with_files_carry_the_file_content():
    history = [_human("1", "a"), AIMessage(content="r"), _human("2", "b"), _human("3", "c"), _human("4", "d"), _human("5")]
    out = att.build_llm_history(history, fetch=lambda url: b"DATA")
    carried = [m for m in out if isinstance(m.content, list) and any(b["type"] == "file" for b in m.content)]
    assert len(carried) == att.RECENT_WITH_FILES == 3
    oldest = out[0].content[0]["text"]
    assert "a.pdf" in oldest and "không còn trong ngữ cảnh" in oldest and len(out[0].content) == 1  # chỉ còn ghi chú
    assert out[1] is history[1] and out[-1] is history[-1]  # tin không có tệp giữ nguyên


def test_unreadable_files_are_reported_to_the_llm():
    out = att.build_llm_history([_human("hỏi", "a")], fetch=lambda url: None)
    assert "không đọc được tệp" in out[0].content[0]["text"] and len(out[0].content) == 1


def test_system_prompt_mentions_attachments_only_when_present_and_helper_detects_them():
    assert ATTACHMENT_INTRO in build_system_prompt([], attachments=True)
    assert ATTACHMENT_INTRO not in build_system_prompt([])
    assert att.has_attachments([_human("x", "a")]) and not att.has_attachments([_human("x")])
    assert not att.has_attachments([_human("x", "a"), _human("y")])  # chỉ xét tin mới nhất


def test_file_cache_avoids_refetching(monkeypatch):
    calls = []

    class Resp:
        status_code = 200
        content = b"abc"

    monkeypatch.setattr(att.requests, "get", lambda url, timeout=None: calls.append(url) or Resp())
    monkeypatch.setattr(att, "_cache", att._Cache(1024))
    assert att.fetch_bytes("https://x/1") == b"abc" and att.fetch_bytes("https://x/1") == b"abc"
    assert calls == ["https://x/1"]
    monkeypatch.setattr(att.requests, "get", lambda url, timeout=None: type("R", (), {"status_code": 404, "content": b""})())
    assert att.fetch_bytes("https://x/gone") is None
