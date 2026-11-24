import json
import threading
import uuid

import anyio
import pytest
from starlette.requests import ClientDisconnect

from app.api.v1.conversations import stream_response
from app.core.config import settings
from app.models import Conversation, User
from app.schemas.conversation import SendMessageIn
from app.services.chat.queue import get_turn_queue
from app.services.llm.gemini import LLMError, LLMNotConfigured, LLMUnavailable


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def _new_conversation(client, headers) -> str:
    return client.post("/api/v1/conversations", headers=headers).json()["id"]


def _stream(client, headers, conv_id, text):
    return client.post(f"/api/v1/conversations/{conv_id}/messages/stream", headers=headers, json={"content": text})


def _build_response(client, headers, session_factory, chat_graph):
    conv_id = _new_conversation(client, headers)
    with session_factory() as db:
        conv = db.get(Conversation, uuid.UUID(conv_id))
        user = db.get(User, conv.user_id)
        body = SendMessageIn(content="Cách tính điểm?")
        response = stream_response(db, user, conv, body, chat_graph, session_factory, None)
    return conv_id, response


def _other_user_headers(client):
    res = client.post("/api/v1/auth/dev-login", json={"email": "b2100002@student.ctu.edu.vn"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_stream_requires_auth(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    res = client.post(f"/api/v1/conversations/{conv_id}/messages/stream", json={"content": "hi"})
    assert res.status_code == 401


def test_stream_sends_start_tokens_then_done(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    res = _stream(client, auth_headers, conv_id, "Cách tính điểm?")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(res.text)
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    assert kinds.count("token") > 1  # thật sự được chia thành nhiều đoạn
    assert set(kinds[1:-1]) == {"token"}

    start, done = events[0][1], events[-1][1]
    assert start["user_message"]["content"] == "Cách tính điểm?"
    streamed = "".join(data["text"] for kind, data in events if kind == "token")
    assert streamed == done["assistant_message"]["content"]
    assert "Cách tính điểm?" in streamed
    assert done["conversation"]["title"] == "Cách tính điểm?"


def test_stream_result_is_persisted_with_wait_time(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    done = parse_sse(_stream(client, auth_headers, conv_id, "câu hỏi").text)[-1][1]
    assert done["assistant_message"]["duration_seconds"] is not None
    first_token = done["assistant_message"]["first_token_seconds"]
    assert first_token >= 0

    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["duration_seconds"] is None  # chỉ tin của bot có thời gian chờ
    bot = detail["messages"][1]
    assert bot["duration_seconds"] == done["assistant_message"]["duration_seconds"]
    assert bot["duration_seconds"] >= 0
    assert detail["messages"][0]["first_token_seconds"] is None
    assert bot["first_token_seconds"] == first_token
    assert bot["id"] == done["assistant_message"]["id"]


def test_non_stream_endpoint_also_reports_wait_time(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    res = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers, json={"content": "điểm D có đậu không"})
    assert res.json()["assistant_message"]["duration_seconds"] is not None
    assert res.json()["assistant_message"]["first_token_seconds"] is not None


def test_stream_keeps_memory_across_turns(client, auth_headers, fake_llm):
    conv_id = _new_conversation(client, auth_headers)
    _stream(client, auth_headers, conv_id, "Tên tôi là An")
    _stream(client, auth_headers, conv_id, "Tôi tên gì?")
    assert "Tên tôi là An" in [m.content for m in fake_llm.calls[1]]


@pytest.mark.parametrize("at", ["headers", "token", "done"])
def test_stream_frees_turn_on_disconnected_transport(client, auth_headers, session_factory, chat_graph, monkeypatch, at):
    monkeypatch.setattr(settings, "chat_busy_wait_seconds", 0)
    conv_id, response = _build_response(client, auth_headers, session_factory, chat_graph)

    queue = get_turn_queue()

    async def receive():
        pytest.fail("ASGI 2.4 reports a closed client through send")

    async def send(message):
        body = message.get("body", b"")
        if at == "headers" and message["type"] == "http.response.start":
            raise OSError("client disconnected")
        if at == "token" and body.startswith(b"event: token\n"):
            raise OSError("client disconnected")
        if at == "done" and body.startswith(b"event: done\n"):
            assert queue.running == queue.waiting == 0
            raise OSError("client disconnected")

    with pytest.raises(ClientDisconnect):
        anyio.run(response, {"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

    assert queue.running == queue.waiting == 0
    history = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()["messages"]
    assert [message["role"] for message in history] == (["user", "assistant"] if at == "done" else [])
    retry = _stream(client, auth_headers, conv_id, "Hỏi tiếp cách tính điểm?")
    assert retry.status_code == 200
    assert parse_sse(retry.text)[-1][0] == "done"


def test_disconnected_waiter_releases_ticket_without_waiting_for_other_user(
    client, auth_headers, session_factory, chat_graph, monkeypatch,
):
    monkeypatch.setattr(settings, "chat_max_concurrent", 1)
    monkeypatch.setattr(settings, "chat_busy_wait_seconds", 0)
    queue = get_turn_queue()
    blocker = queue.enter("already-running")
    assert list(queue.wait(blocker)) == []
    conv_id, response = _build_response(client, auth_headers, session_factory, chat_graph)

    async def disconnect_while_waiting():
        queued = anyio.Event()

        async def send(message):
            if message.get("body", b"").startswith(b"event: queued\n"):
                queued.set()

        async def receive():
            await queued.wait()
            await anyio.sleep(0.05)  # allow the worker to resume waiting on the queue
            return {"type": "http.disconnect"}

        await response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send)

    # Keep the test bounded if a regression makes response cleanup wait for the blocker.
    timer = threading.Timer(3, queue.release, args=(blocker,))
    timer.start()
    try:
        anyio.run(disconnect_while_waiting)
        assert queue.waiting == 0
        assert queue.running == 1
    finally:
        timer.cancel()
        queue.release(blocker)

    retry = _stream(client, auth_headers, conv_id, "Hỏi sau khi ngắt kết nối?")
    assert retry.status_code == 200
    assert parse_sse(retry.text)[-1][0] == "done"


def test_stream_error_is_sent_as_event_and_rolls_back(client, auth_headers, fake_llm):
    conv_id = _new_conversation(client, auth_headers)

    fake_llm.error = LLMUnavailable(retry_after=7)
    events = parse_sse(_stream(client, auth_headers, conv_id, "hỏi").text)
    assert [k for k, _ in events] == ["start", "error"]
    assert events[-1][1] == {"code": "LLM_RATE_LIMITED", "retry_after": 7}

    fake_llm.error = LLMNotConfigured("no key")
    assert parse_sse(_stream(client, auth_headers, conv_id, "hỏi").text)[-1][1] == {"code": "LLM_NOT_CONFIGURED"}

    fake_llm.error = LLMError("boom")
    assert parse_sse(_stream(client, auth_headers, conv_id, "hỏi").text)[-1][1] == {"code": "LLM_ERROR"}

    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()
    assert detail["messages"] == []  # không để lại tin "mồ côi"
    assert detail["title"] == ""

    fake_llm.error = None
    assert parse_sse(_stream(client, auth_headers, conv_id, "hỏi lại").text)[-1][0] == "done"


def test_stream_validates_before_streaming(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    assert _stream(client, auth_headers, conv_id, "   ").status_code == 422
    assert _stream(client, auth_headers, conv_id, "x" * 4001).status_code == 422
    other = _other_user_headers(client)
    assert _stream(client, other, conv_id, "đọc trộm").status_code == 404
    assert _stream(client, auth_headers, "00000000-0000-0000-0000-000000000000", "hi").status_code == 404


def test_rename_conversation(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    res = client.patch(f"/api/v1/conversations/{conv_id}", headers=auth_headers, json={"title": "  Tên   mới \n tự đặt "})
    assert res.status_code == 200
    assert res.json()["title"] == "Tên mới tự đặt"
    listed = client.get("/api/v1/conversations", headers=auth_headers).json()
    assert listed[0]["title"] == "Tên mới tự đặt"


def test_rename_survives_new_messages(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    client.patch(f"/api/v1/conversations/{conv_id}", headers=auth_headers, json={"title": "Giữ nguyên"})
    _stream(client, auth_headers, conv_id, "câu hỏi đầu tiên")
    assert client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()["title"] == "Giữ nguyên"


def test_rename_validation_and_ownership(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    url = f"/api/v1/conversations/{conv_id}"
    assert client.patch(url, headers=auth_headers, json={"title": "   "}).status_code == 422
    assert client.patch(url, headers=auth_headers, json={"title": "x" * 201}).status_code == 422
    assert client.patch(url, json={"title": "a"}).status_code == 401
    assert client.patch(url, headers=_other_user_headers(client), json={"title": "chiếm"}).status_code == 404
