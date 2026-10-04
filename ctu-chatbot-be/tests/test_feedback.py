VALID_ANSWER_ISSUE = {
    "type": "answer_issue",
    "category": "wrong_citation",
    "message": "Điều khoản trích dẫn sai",
    "conversation_id": "c-1",
    "message_id": "m-1",
}


def test_feedback_requires_auth(client):
    assert client.post("/api/v1/feedback", json=VALID_ANSWER_ISSUE).status_code == 401


def test_create_answer_issue_feedback(client, auth_headers):
    res = client.post("/api/v1/feedback", headers=auth_headers, json=VALID_ANSWER_ISSUE)
    assert res.status_code == 201
    assert res.json()["id"]


def test_create_general_feedback_without_message(client, auth_headers):
    res = client.post(
        "/api/v1/feedback", headers=auth_headers, json={"type": "general", "category": "suggestion"}
    )
    assert res.status_code == 201


def test_other_category_requires_message(client, auth_headers):
    res = client.post(
        "/api/v1/feedback",
        headers=auth_headers,
        json={"type": "general", "category": "other", "message": "   "},
    )
    assert res.status_code == 422


def test_answer_issue_requires_message_id(client, auth_headers):
    body = {**VALID_ANSWER_ISSUE, "message_id": None}
    assert client.post("/api/v1/feedback", headers=auth_headers, json=body).status_code == 422


def test_category_must_match_type(client, auth_headers):
    body = {**VALID_ANSWER_ISSUE, "category": "bug"}
    assert client.post("/api/v1/feedback", headers=auth_headers, json=body).status_code == 422


def test_message_length_limit(client, auth_headers):
    body = {**VALID_ANSWER_ISSUE, "message": "x" * 1001}
    assert client.post("/api/v1/feedback", headers=auth_headers, json=body).status_code == 422
