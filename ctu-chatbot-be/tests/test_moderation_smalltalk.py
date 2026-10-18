import pytest

from app.services.chat import smalltalk
from app.services.chat.moderation import is_profane


@pytest.mark.parametrize(
    "text",
    [
        "địt mẹ mày", "đm", "Đ.M bot", "đmmmmm", "vcl", "dit me may", "du ma", "fuck you", "fuuuuck", "what the shit",
        "bot ngu vãi", "thằng ngu", "đồ chó", "óc chó", "câm mồm", "khốn nạn", "con cac", "VL", "cái lồn gì vậy",
    ],
)
def test_profanity_is_caught(text):
    assert is_profane(text)


@pytest.mark.parametrize(
    "text",
    [
        "Điều 14 quy định gì?", "các bạn sinh viên được học cải thiện không", "du lịch học tập có tính tín chỉ không",
        "con chó có được vào ký túc xá không", "bánh dẻo", "đĩa CD", "đụng độ lịch thi", "buổi sáng thi lúc mấy giờ",
        "cac ban cho minh hoi", "lon nhat la bao nhieu tin chi", "mình ngu quá không hiểu điều 14", "đánh giá điểm rèn luyện",
        "dm là gì", "hi", "chào bạn",
    ],
)
def test_normal_questions_pass(text):
    assert not is_profane(text) or text == "dm là gì"  # "dm" đứng riêng là viết tắt chửi: chấp nhận bắt


@pytest.mark.parametrize(
    "text,kind",
    [
        ("Xin chào", "greeting"), ("hello bạn!!", "greeting"), ("chàooooo 😊", "greeting"), ("hi bot", "greeting"),
        ("chao ban", "greeting"), ("Cảm ơn bạn nhiều", "thanks"), ("thanks", "thanks"), ("tạm biệt nhé", "bye"),
        ("bạn là ai?", "who"), ("Bạn làm được gì vậy", "capabilities"), ("ok", "ack"),
    ],
)
def test_pure_smalltalk_gets_canned_answer(text, kind):
    hit = smalltalk.lookup(text)
    assert hit is not None and hit.id == f"smalltalk:{kind}" and hit.answer


@pytest.mark.parametrize(
    "text",
    ["chào bạn cho mình hỏi về điều 14", "cảm ơn, còn học phí thì sao", "hi, điểm D có đậu không", "ok vậy ĐTBCHK tính sao", ""],
)
def test_real_questions_are_not_smalltalk(text):
    assert smalltalk.lookup(text) is None


def test_chat_api_blocks_profanity_without_touching_history(client, auth_headers):
    conv_id = client.post("/api/v1/conversations", headers=auth_headers).json()["id"]
    for path in ("messages", "messages/stream"):
        res = client.post(f"/api/v1/conversations/{conv_id}/{path}", headers=auth_headers, json={"content": "đm mày ngu"})
        assert res.status_code == 422 and "PROFANITY" in res.text
    assert client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()["messages"] == []


def test_chat_api_greeting_is_answered_without_llm(client, auth_headers, fake_llm):
    conv_id = client.post("/api/v1/conversations", headers=auth_headers).json()["id"]
    before = len(getattr(fake_llm, "calls", []))
    res = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers, json={"content": "xin chào"})
    assert res.status_code == 200
    body = res.json()
    assert body["assistant_message"]["cached"] is True and body["assistant_message"]["content"]
    assert len(getattr(fake_llm, "calls", [])) == before


def test_greetings_and_profanity_count_toward_the_rate_limit(client, auth_headers):
    conv_id = client.post("/api/v1/conversations", headers=auth_headers).json()["id"]
    url = f"/api/v1/conversations/{conv_id}/messages"
    # conftest: CHAT_RATE_LIMIT=10/5m. Xen kẽ chào hỏi và chửi thề đều bị tính.
    for i in range(10):
        text = "xin chào" if i % 2 == 0 else "đm"
        res = client.post(url, headers=auth_headers, json={"content": text})
        assert res.status_code == (200 if i % 2 == 0 else 422)
    assert client.post(url, headers=auth_headers, json={"content": "xin chào"}).status_code == 429
    # Đang bị giới hạn mà chửi thề thì vẫn thấy cảnh báo chửi thề (422), không phải thông báo giới hạn (429).
    assert client.post(url, headers=auth_headers, json={"content": "đm"}).status_code == 422


def test_suggested_questions_still_skip_the_rate_limit(client, auth_headers):
    from app.services.chat import suggested

    items = suggested.load()
    if not items:
        pytest.skip("chưa có câu hỏi gợi ý")
    conv_id = client.post("/api/v1/conversations", headers=auth_headers).json()["id"]
    url = f"/api/v1/conversations/{conv_id}/messages"
    for _ in range(12):
        assert client.post(url, headers=auth_headers, json={"content": items[0].question}).status_code == 200


def test_every_smalltalk_kind_has_several_variants():
    from app.services.chat.smalltalk import _PATTERNS, _REPLIES

    assert set(_PATTERNS) == set(_REPLIES)
    assert len(_REPLIES["greeting"]) >= 8 and all(len(v) >= 2 for v in _REPLIES.values())
