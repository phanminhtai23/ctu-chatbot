

def test_users_can_be_sorted_by_column(client, admin_headers, session_factory):
    from app.models import User

    with session_factory() as db:
        for i, (spam, bad) in enumerate([(5, 0), (1, 9), (3, 2)]):
            db.add(User(email=f"s{i}@student.ctu.edu.vn", name=f"U{i}", spam_count=spam, profanity_count=bad))
        db.commit()

    def emails(**params):
        res = client.get("/api/v1/admin/users", params=params, headers=admin_headers)
        assert res.status_code == 200
        return [u["email"] for u in res.json()["items"] if u["email"].startswith("s")]

    assert emails(sort="spam", order="desc") == ["s0@student.ctu.edu.vn", "s2@student.ctu.edu.vn", "s1@student.ctu.edu.vn"]
    assert emails(sort="profanity", order="desc") == ["s1@student.ctu.edu.vn", "s2@student.ctu.edu.vn", "s0@student.ctu.edu.vn"]
    assert emails(sort="spam", order="asc")[0] == "s1@student.ctu.edu.vn"
    for key in ("name", "role", "state", "created", "last_active", "messages", "storage"):
        assert client.get("/api/v1/admin/users", params={"sort": key, "order": "asc"}, headers=admin_headers).status_code == 200
    assert client.get("/api/v1/admin/users", params={"sort": "bogus"}, headers=admin_headers).status_code == 422
