from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.chat.graph import SYSTEM_PROMPT, build_chat_graph, window
from app.services.llm.gemini import LLMError, LLMNotConfigured, LLMUnavailable


def _new_conversation(client, headers) -> str:
    res = client.post("/api/v1/conversations", headers=headers)
    assert res.status_code == 201
    return res.json()["id"]


def _send(client, headers, conv_id, text):
    return client.post(f"/api/v1/conversations/{conv_id}/messages", headers=headers, json={"content": text})


def _other_user_headers(client):
    res = client.post("/api/v1/auth/dev-login", json={"email": "b2100002@student.ctu.edu.vn"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_conversations_require_auth(client):
    assert client.post("/api/v1/conversations").status_code == 401
    assert client.get("/api/v1/conversations").status_code == 401


def test_send_message_returns_both_messages_and_sets_title(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    res = _send(client, auth_headers, conv_id, "  Cách tính điểm trung bình học kỳ?  ")
    assert res.status_code == 200
    body = res.json()
    assert body["user_message"]["role"] == "user"
    assert body["user_message"]["content"] == "Cách tính điểm trung bình học kỳ?"
    assert body["assistant_message"]["role"] == "assistant"
    assert "Cách tính điểm" in body["assistant_message"]["content"]
    assert body["user_message"]["id"] != body["assistant_message"]["id"]
    assert body["conversation"]["title"] == "Cách tính điểm trung bình học kỳ?"


def test_bot_remembers_earlier_turns_from_checkpoint(client, auth_headers, fake_llm):
    conv_id = _new_conversation(client, auth_headers)
    _send(client, auth_headers, conv_id, "Tên tôi là An")
    _send(client, auth_headers, conv_id, "Tôi tên gì?")

    second_call = fake_llm.calls[1]
    texts = [m.content for m in second_call]
    assert second_call[0].content == SYSTEM_PROMPT  # prompt hệ thống luôn ở đầu
    assert "Tên tôi là An" in texts  # lượt 1 của người dùng được nạp lại từ checkpoint
    assert any(isinstance(m, AIMessage) for m in second_call)  # cả câu trả lời lượt 1
    assert texts[-1] == "Tôi tên gì?"


def test_history_survives_rebuilding_the_graph_like_a_server_restart(client, auth_headers, checkpointer, fake_llm):
    conv_id = _new_conversation(client, auth_headers)
    _send(client, auth_headers, conv_id, "Tên tôi là An")

    # Dựng đồ thị MỚI trên cùng nơi lưu checkpoint (giống khởi động lại server với Postgres).
    new_graph = build_chat_graph(fake_llm, checkpointer)
    from app.main import app
    from app.api.deps import get_chat_graph

    app.dependency_overrides[get_chat_graph] = lambda: new_graph
    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "Tên tôi là An"

    _send(client, auth_headers, conv_id, "Tôi tên gì?")
    assert "Tên tôi là An" in [m.content for m in fake_llm.calls[-1]]


def test_get_conversation_returns_messages_in_order(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    _send(client, auth_headers, conv_id, "câu 1")
    _send(client, auth_headers, conv_id, "câu 2")
    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in detail["messages"] if m["role"] == "user"] == ["câu 1", "câu 2"]
    assert all(m["created_at"] for m in detail["messages"])


def test_conversations_are_isolated_between_users(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    _send(client, auth_headers, conv_id, "bí mật của tôi")
    other = _other_user_headers(client)

    assert client.get(f"/api/v1/conversations/{conv_id}", headers=other).status_code == 404
    assert _send(client, other, conv_id, "đọc trộm").status_code == 404
    assert client.delete(f"/api/v1/conversations/{conv_id}", headers=other).status_code == 404
    assert client.get("/api/v1/conversations", headers=other).json() == []


def test_list_conversations_newest_activity_first(client, auth_headers):
    first = _new_conversation(client, auth_headers)
    second = _new_conversation(client, auth_headers)
    _send(client, auth_headers, first, "hoạt động mới nhất")
    ids = [c["id"] for c in client.get("/api/v1/conversations", headers=auth_headers).json()]
    assert ids == [first, second]


def test_delete_conversation_removes_metadata_and_history(client, auth_headers, chat_graph):
    conv_id = _new_conversation(client, auth_headers)
    _send(client, auth_headers, conv_id, "xoá tôi đi")
    assert client.delete(f"/api/v1/conversations/{conv_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).status_code == 404
    state = chat_graph.get_state({"configurable": {"thread_id": conv_id}})
    assert not (state.values or {}).get("messages")


def test_blank_or_too_long_message_is_rejected(client, auth_headers):
    conv_id = _new_conversation(client, auth_headers)
    assert _send(client, auth_headers, conv_id, "    ").status_code == 422
    assert _send(client, auth_headers, conv_id, "x" * 4001).status_code == 422


def test_llm_failure_rolls_back_the_user_message(client, auth_headers, fake_llm):
    conv_id = _new_conversation(client, auth_headers)
    fake_llm.error = LLMError("boom")
    assert _send(client, auth_headers, conv_id, "câu hỏi bị lỗi").status_code == 502

    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()
    assert detail["messages"] == []  # không để lại tin "mồ côi", gửi lại sẽ không bị trùng
    assert detail["title"] == ""

    fake_llm.error = None
    assert _send(client, auth_headers, conv_id, "câu hỏi bị lỗi").status_code == 200
    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]


def test_llm_error_codes_are_machine_readable(client, auth_headers, fake_llm):
    conv_id = _new_conversation(client, auth_headers)

    fake_llm.error = LLMNotConfigured("no key")
    res = _send(client, auth_headers, conv_id, "a")
    assert (res.status_code, res.json()["detail"]) == (503, "LLM_NOT_CONFIGURED")

    fake_llm.error = LLMUnavailable(retry_after=42)
    res = _send(client, auth_headers, conv_id, "a")
    assert (res.status_code, res.json()["detail"]) == (503, "LLM_RATE_LIMITED")
    assert res.headers["Retry-After"] == "42"


def test_window_keeps_recent_messages_and_starts_with_a_user_turn():
    msgs = [HumanMessage("h1"), AIMessage("a1"), HumanMessage("h2"), AIMessage("a2"), HumanMessage("h3")]
    assert [m.content for m in window(msgs, 3)] == ["h2", "a2", "h3"]
    # Cắt giữa chừng làm đầu đoạn là câu của bot -> bỏ nó đi (Gemini cần lượt đầu là của người dùng).
    assert [m.content for m in window(msgs, 4)] == ["h2", "a2", "h3"]
    assert [m.content for m in window(msgs, 100)] == ["h1", "a1", "h2", "a2", "h3"]
    assert not any(isinstance(m, SystemMessage) for m in window(msgs, 5))
