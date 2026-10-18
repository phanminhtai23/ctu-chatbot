"""Câu hỏi gợi ý khi mở chat: trả lời có sẵn (cache), không gọi LLM, không tính giới hạn chat."""

import importlib.util
from pathlib import Path

import pytest

from app.services.chat import suggested
from tests.answer_checks import case_problems, friendly_problems
from tests.test_streaming import parse_sse

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_suggested_cache.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("build_suggested_cache", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _new_conversation(client, headers) -> str:
    return client.post("/api/v1/conversations", headers=headers).json()["id"]


def _send(client, headers, conv_id, text):
    return client.post(f"/api/v1/conversations/{conv_id}/messages", headers=headers, json={"content": text})


@pytest.fixture()
def first():
    return suggested.load()[0]


# ---- dữ liệu cache ----


def test_cache_has_scholarship_and_gpa_questions():
    items = suggested.load()
    assert len(items) >= 4
    categories = {item.category for item in items}
    assert {"Học bổng", "Điểm trung bình"} <= categories  # ngoài ra có các nhóm quan trọng khác (cảnh báo học tập, tốt nghiệp...)
    assert len(categories) >= 3
    assert [i.id for i in items[:2]] == ["xuat-sac", "hb-so-sanh"]  # hai câu hay nhất nằm đầu
    assert len({i.id for i in items}) == len(items)
    assert len({suggested.normalize(i.question) for i in items}) == len(items)


def test_every_cached_answer_has_valid_sources():
    for item in suggested.load():
        assert item.answer.strip() and item.sources
        for source in item.sources:
            assert 1 <= source["article"] <= 36 and source["title"]
            assert f"Điều {source['article']}" in item.answer  # chỉ giữ tham chiếu mà câu trả lời thực sự nhắc tới


def test_cache_is_in_sync_with_the_questions_and_expectations_in_the_build_script():
    script = _load_script()
    by_id = {item.id: item for item in suggested.load()}
    assert set(by_id) == {item_id for item_id, *_ in script.SUGGESTIONS}
    for item_id, category, question, case in script.SUGGESTIONS:
        item = by_id[item_id]
        assert (item.category, item.question) == (category, question)
        problems = case_problems(case, item.answer) + friendly_problems(item.answer)
        assert not problems, f"[{item_id}] {problems}\n{item.answer}"


# ---- so khớp câu hỏi ----


@pytest.mark.parametrize(
    "variant",
    [lambda q: q, lambda q: q.upper(), lambda q: "  " + q.replace(" ", "  ") + "  ", lambda q: q.rstrip("?") + " ?", lambda q: q + "!!"],
)
def test_lookup_ignores_case_spaces_and_trailing_punctuation(first, variant):
    assert suggested.lookup(variant(first.question)) is first


def test_lookup_requires_the_same_question():
    assert suggested.lookup("Học bổng là gì?") is None
    assert suggested.lookup(suggested.load()[0].question + " Giải thích thêm giúp mình") is None
    assert suggested.lookup("") is None


# ---- API ----


def test_suggestions_endpoint_is_public_and_hides_answers(client):
    res = client.get("/api/v1/suggestions")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == len(suggested.load())
    assert all(set(item) == {"id", "category", "question"} for item in body)
    assert {item["question"] for item in body} == {i.question for i in suggested.load()}


def test_suggested_question_gets_the_cached_answer_without_calling_the_llm(client, auth_headers, fake_llm, first):
    conv_id = _new_conversation(client, auth_headers)
    res = _send(client, auth_headers, conv_id, first.question)
    assert res.status_code == 200
    body = res.json()
    assert body["assistant_message"]["content"] == first.answer
    assert body["assistant_message"]["cached"] is True
    assert body["user_message"]["cached"] is False
    assert [s["article"] for s in body["assistant_message"]["sources"]] == [s["article"] for s in first.sources]
    assert body["assistant_message"]["duration_seconds"] is None
    assert fake_llm.calls == []  # không gọi LLM
    assert body["conversation"]["title"].startswith(first.question[:20])


def test_cached_turn_is_saved_in_the_conversation_history(client, auth_headers, first):
    conv_id = _new_conversation(client, auth_headers)
    _send(client, auth_headers, conv_id, first.question)
    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == first.answer and detail["messages"][1]["cached"] is True
    assert detail["messages"][1]["sources"]  # tham chiếu vẫn còn khi mở lại cuộc trò chuyện


def test_next_question_after_a_cached_turn_remembers_it(client, auth_headers, fake_llm, first):
    conv_id = _new_conversation(client, auth_headers)
    _send(client, auth_headers, conv_id, first.question)
    _send(client, auth_headers, conv_id, "Còn trường hợp khác thì sao?")
    sent = [m.content for m in fake_llm.calls[-1]]  # lượt gọi cuối là lượt trả lời (lượt đầu có thể là trích số liệu)
    assert first.question in sent and first.answer in sent  # LLM thấy cả lượt có sẵn làm ngữ cảnh


def test_cached_answers_do_not_use_up_the_chat_budget(client, auth_headers, fake_llm, first):
    conv_id = _new_conversation(client, auth_headers)
    for _ in range(15):  # nhiều hơn giới hạn 10 tin / 5 phút
        assert _send(client, auth_headers, conv_id, first.question).status_code == 200
    assert fake_llm.calls == []
    for i in range(10):
        assert _send(client, auth_headers, conv_id, f"câu hỏi thường {i}").status_code == 200
    assert _send(client, auth_headers, conv_id, "câu thường thứ 11").status_code == 429  # vẫn bị giới hạn bình thường
    assert _send(client, auth_headers, conv_id, first.question).status_code == 200  # nhưng câu gợi ý vẫn được trả lời


def test_a_normal_question_still_goes_to_the_llm(client, auth_headers, fake_llm):
    conv_id = _new_conversation(client, auth_headers)
    body = _send(client, auth_headers, conv_id, "Học kỳ 1 bắt đầu tuần nào?").json()
    assert body["assistant_message"]["cached"] is False
    assert len(fake_llm.calls) == 1


def test_streaming_endpoint_replays_the_cached_answer_in_the_same_event_format(client, auth_headers, fake_llm, first):
    conv_id = _new_conversation(client, auth_headers)
    res = client.post(f"/api/v1/conversations/{conv_id}/messages/stream", headers=auth_headers, json={"content": first.question})
    assert res.status_code == 200
    events = parse_sse(res.text)
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "start" and kinds[-1] == "done"
    tokens = [data["text"] for kind, data in events if kind == "token"]
    assert len(tokens) > 3 and "".join(tokens) == first.answer
    done = events[-1][1]
    assert done["assistant_message"]["cached"] is True and done["assistant_message"]["sources"]
    assert done["conversation"]["id"] == conv_id
    assert fake_llm.calls == []


def test_cached_questions_are_still_private_to_the_conversation_owner(client, auth_headers, first):
    other = client.post("/api/v1/auth/dev-login", json={"email": "b2100002@student.ctu.edu.vn"}).json()["access_token"]
    conv_id = _new_conversation(client, auth_headers)
    res = _send(client, {"Authorization": f"Bearer {other}"}, conv_id, first.question)
    assert res.status_code == 404  # không dùng được câu gợi ý để ghi vào cuộc trò chuyện của người khác
