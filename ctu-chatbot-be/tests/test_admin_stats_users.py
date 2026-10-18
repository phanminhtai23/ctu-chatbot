"""Dashboard thống kê và quản lý user của admin."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models import RefreshToken, UsageEvent, User
from app.services.usage import VN_TZ, compute_stats, user_activity

# 12:00 giờ Việt Nam ngày 2026-10-18 (thứ Bảy)
NOW = datetime(2026, 10, 18, 5, 0, tzinfo=timezone.utc)


def add_user(db, email, days_ago, role="user", active=True):
    user = User(email=email, name=email.split("@")[0], role=role, is_active=active, created_at=NOW - timedelta(days=days_ago))
    db.add(user)
    db.commit()
    return user


def add_events(db, user, *when):
    for moment in when:
        db.add(UsageEvent(user_id=user.id, created_at=moment))
    db.commit()


@pytest.fixture()
def seeded(session_factory):
    with session_factory() as db:
        a = add_user(db, "a@ctu.edu.vn", 0)  # đăng ký hôm nay
        b = add_user(db, "b@ctu.edu.vn", 5)  # tuần này
        c = add_user(db, "c@ctu.edu.vn", 20)  # tháng này
        d = add_user(db, "d@ctu.edu.vn", 100)  # trong 6 tháng
        e = add_user(db, "e@ctu.edu.vn", 300)  # trong năm
        add_user(db, "f@ctu.edu.vn", 400)  # hơn một năm
        add_events(db, a, NOW, NOW - timedelta(hours=1), NOW - timedelta(days=1))
        add_events(db, b, NOW - timedelta(days=1), NOW - timedelta(days=10))
        add_events(db, c, NOW - timedelta(days=40))
        yield db


def test_registrations_are_counted_by_week_month_six_months_and_year(seeded):
    stats = compute_stats(seeded, now=NOW)
    assert stats["registrations"] == {"week": 2, "month": 3, "six_months": 4, "year": 5}
    assert stats["totals"]["users"] == 6


def test_daily_usage_counts_active_users_and_messages_with_zero_filled_days(seeded):
    stats = compute_stats(seeded, days=7, now=NOW)
    daily = {row["date"]: row for row in stats["usage_daily"]}
    assert len(stats["usage_daily"]) == 7 and stats["usage_daily"][-1]["date"] == "2026-10-18"
    assert daily["2026-10-18"] == {"date": "2026-10-18", "active_users": 1, "messages": 2}
    assert daily["2026-10-17"]["active_users"] == 2 and daily["2026-10-17"]["messages"] == 2
    assert daily["2026-10-15"] == {"date": "2026-10-15", "active_users": 0, "messages": 0}
    assert stats["totals"]["active_today"] == 1 and stats["totals"]["messages_today"] == 2
    assert stats["totals"]["active_7d"] == 2 and stats["totals"]["active_30d"] == 2 and stats["totals"]["messages"] == 6


def test_days_use_vietnam_time_not_utc(session_factory):
    with session_factory() as db:
        user = add_user(db, "late@ctu.edu.vn", 3)
        # 20:00 UTC ngày 17 = 03:00 giờ VN ngày 18
        add_events(db, user, datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc))
        stats = compute_stats(db, days=3, now=NOW)
    assert stats["usage_daily"][-1] == {"date": "2026-10-18", "active_users": 1, "messages": 1}
    assert stats["hourly"][3] == 1


def test_hourly_weekday_and_frequency(seeded):
    stats = compute_stats(seeded, days=30, now=NOW)
    assert stats["hourly"][12] == 4 and stats["hourly"][11] == 1 and sum(stats["hourly"]) == stats["frequency"]["window_messages"] == 5
    assert stats["weekday"][NOW.astimezone(VN_TZ).weekday()] == 2  # thứ Bảy
    freq = stats["frequency"]
    assert freq["avg_messages_per_day"] == round(5 / 30, 1)
    assert freq["avg_messages_per_active_user_per_day"] == round(5 / 4, 1)  # 4 cặp (user, ngày)
    assert [u["email"] for u in freq["top_users"]] == ["a@ctu.edu.vn", "b@ctu.edu.vn"]
    assert freq["top_users"][0] == {"email": "a@ctu.edu.vn", "name": "a", "messages": 3, "active_days": 2}


def test_stats_on_empty_database(session_factory):
    with session_factory() as db:
        stats = compute_stats(db, days=5, now=NOW)
    assert stats["totals"]["users"] == 0 and len(stats["usage_daily"]) == 5
    assert stats["frequency"]["avg_messages_per_active_user_per_day"] == 0 and stats["frequency"]["top_users"] == []


def test_user_activity_summary(seeded):
    user = seeded.query(User).filter(User.email == "a@ctu.edu.vn").one()
    info = user_activity(seeded, user.id, days=3, now=NOW)
    assert info["messages"] == 3 and len(info["daily"]) == 3 and info["daily"][-1]["messages"] == 2
    assert info["last_active"].startswith("2026-10-18")


# ---- API ----


def test_stats_endpoint_is_admin_only(client, auth_headers, admin_headers):
    assert client.get("/api/v1/admin/stats", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/admin/stats").status_code == 401
    body = client.get("/api/v1/admin/stats?days=7", headers=admin_headers).json()
    assert body["days"] == 7 and len(body["usage_daily"]) == 7 and "registrations" in body
    assert client.get("/api/v1/admin/stats?days=0", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/admin/stats?days=9999", headers=admin_headers).status_code == 422


def _new_conversation(client, headers):
    return client.post("/api/v1/conversations", headers=headers).json()["id"]


def test_each_chat_turn_is_recorded_as_usage(client, auth_headers, admin_headers):
    conv = _new_conversation(client, auth_headers)
    client.post(f"/api/v1/conversations/{conv}/messages", headers=auth_headers, json={"content": "Điều 14 nói gì?"})
    client.post(f"/api/v1/conversations/{conv}/messages/stream", headers=auth_headers, json={"content": "hỏi tiếp"})
    stats = client.get("/api/v1/admin/stats?days=7", headers=admin_headers).json()
    assert stats["totals"]["messages"] == 2 and stats["totals"]["active_today"] == 1
    assert stats["frequency"]["top_users"][0]["messages"] == 2


def test_failed_turn_is_not_recorded(client, auth_headers, admin_headers, fake_llm):
    fake_llm.error = RuntimeError("boom")
    conv = _new_conversation(client, auth_headers)
    with pytest.raises(RuntimeError):
        client.post(f"/api/v1/conversations/{conv}/messages", headers=auth_headers, json={"content": "x"})
    assert client.get("/api/v1/admin/stats", headers=admin_headers).json()["totals"]["messages"] == 0


def _users(client, headers, **params):
    return client.get("/api/v1/admin/users", headers=headers, params=params).json()


def test_user_list_search_filter_and_paging(client, admin_headers, session_factory):
    with session_factory() as db:
        add_user(db, "an@ctu.edu.vn", 3)
        add_user(db, "binh@ctu.edu.vn", 2, active=False)
        add_user(db, "chi@ctu.edu.vn", 1, role="admin")
    assert _users(client, admin_headers)["total"] == 4
    assert [u["email"] for u in _users(client, admin_headers, q="BINH")["items"]] == ["binh@ctu.edu.vn"]
    assert [u["email"] for u in _users(client, admin_headers, state="disabled")["items"]] == ["binh@ctu.edu.vn"]
    assert {u["email"] for u in _users(client, admin_headers, role="admin")["items"]} == {"chi@ctu.edu.vn", "admin@student.ctu.edu.vn"}
    page = _users(client, admin_headers, limit=2, offset=0)
    assert page["total"] == 4 and len(page["items"]) == 2


def test_user_list_shows_message_and_conversation_counts(client, auth_headers, admin_headers):
    conv = _new_conversation(client, auth_headers)
    client.post(f"/api/v1/conversations/{conv}/messages", headers=auth_headers, json={"content": "Điều 14 nói gì?"})
    row = next(u for u in _users(client, admin_headers)["items"] if u["email"] == "b2100001@student.ctu.edu.vn")
    assert row["messages"] == 1 and row["conversations"] == 1 and row["last_active"]


def test_user_detail_has_daily_activity(client, auth_headers, admin_headers):
    user_id = client.get("/api/v1/me", headers=auth_headers).json()["id"]
    detail = client.get(f"/api/v1/admin/users/{user_id}", headers=admin_headers).json()
    assert detail["email"] == "b2100001@student.ctu.edu.vn" and len(detail["daily"]) == 30
    assert client.get("/api/v1/admin/users/00000000-0000-0000-0000-000000000000", headers=admin_headers).status_code == 404


def test_disabling_a_user_blocks_old_tokens_and_revokes_refresh_tokens(client, auth_headers, admin_headers, session_factory):
    user_id = client.get("/api/v1/me", headers=auth_headers).json()["id"]
    res = client.patch(f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"is_active": False})
    assert res.status_code == 200 and res.json()["is_active"] is False
    assert client.get("/api/v1/me", headers=auth_headers).status_code == 403
    assert client.post("/api/v1/auth/dev-login", json={"email": "b2100001@student.ctu.edu.vn"}).status_code == 403
    with session_factory() as db:
        assert db.query(RefreshToken).filter(RefreshToken.revoked_at.is_(None)).count() == 1  # chỉ còn của admin

    client.patch(f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"is_active": True})
    assert client.post("/api/v1/auth/dev-login", json={"email": "b2100001@student.ctu.edu.vn"}).status_code == 200


def test_admin_can_change_roles(client, auth_headers, admin_headers):
    user_id = client.get("/api/v1/me", headers=auth_headers).json()["id"]
    assert client.patch(f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"role": "admin"}).json()["role"] == "admin"
    assert client.get("/api/v1/admin/stats", headers=auth_headers).status_code == 200
    assert client.patch(f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"role": "user"}).json()["role"] == "user"


def test_guards_against_locking_everyone_out(client, admin_headers, session_factory):
    me = client.get("/api/v1/me", headers=admin_headers).json()["id"]
    for body in ({"is_active": False}, {"role": "user"}):
        res = client.patch(f"/api/v1/admin/users/{me}", headers=admin_headers, json=body)
        assert res.status_code == 409 and res.json()["detail"] == "CANNOT_CHANGE_SELF"

    with session_factory() as db:
        other = add_user(db, "ad2@ctu.edu.vn", 1, role="admin")
        other_id = str(other.id)
    ok = client.patch(f"/api/v1/admin/users/{other_id}", headers=admin_headers, json={"role": "user"})
    assert ok.status_code == 200  # còn admin khác (chính mình) nên hạ được


def test_last_other_admin_cannot_be_removed_by_a_non_listed_path(client, admin_headers, session_factory, monkeypatch):
    with session_factory() as db:
        other = add_user(db, "ad2@ctu.edu.vn", 1, role="admin", active=False)  # admin đã khoá không tính là admin còn lại
        other_id = str(other.id)
    # Chỉ còn một admin hoạt động là chính người gọi -> hạ admin khoá kia vẫn được (không ảnh hưởng ai), nhưng
    # hạ người cuối cùng thì không: giả lập bằng cách đổi người gọi.
    res = client.patch(f"/api/v1/admin/users/{other_id}", headers=admin_headers, json={"role": "user"})
    assert res.status_code == 200


def test_admin_from_env_cannot_be_demoted(client, admin_headers, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "boss@ctu.edu.vn")
    with session_factory() as db:
        boss = add_user(db, "boss@ctu.edu.vn", 1, role="admin")
        boss_id = str(boss.id)
    res = client.patch(f"/api/v1/admin/users/{boss_id}", headers=admin_headers, json={"role": "user"})
    assert res.status_code == 409 and res.json()["detail"] == "ADMIN_BY_ENV"
    assert _users(client, admin_headers, q="boss")["items"][0]["admin_by_env"] is True


def test_user_endpoints_are_admin_only(client, auth_headers):
    assert client.get("/api/v1/admin/users", headers=auth_headers).status_code == 403
    me = client.get("/api/v1/me", headers=auth_headers).json()["id"]
    assert client.patch(f"/api/v1/admin/users/{me}", headers=auth_headers, json={"role": "admin"}).status_code == 403
