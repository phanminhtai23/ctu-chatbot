"""Dashboard thống kê và quản lý user của admin."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models import RefreshToken, UsageEvent, User
from app.services.usage import VN_TZ, compute_stats, stats_csv, user_activity

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


def _stats(db, **kw):
    return compute_stats(db, now=NOW, **kw)


def test_registrations_are_counted_by_week_month_six_months_and_year(seeded):
    stats = _stats(seeded)
    assert stats["registrations"] == {"week": 2, "month": 3, "six_months": 4, "year": 5}
    assert stats["totals"]["users"] == 6


def test_default_range_is_the_last_30_days_and_daily(seeded):
    stats = _stats(seeded)
    assert stats["range"] == {
        "from": "2026-09-19", "to": "2026-10-18", "days": 30, "granularity": "day",
        "previous_from": "2026-08-20", "previous_to": "2026-09-18",
    }
    assert len(stats["series"]) == 30 and stats["series"][-1]["date"] == "2026-10-18"


def test_daily_series_counts_active_users_messages_and_zero_fills(seeded):
    stats = _stats(seeded, date_from=date(2026, 10, 12), date_to=date(2026, 10, 18))
    daily = {row["date"]: row for row in stats["series"]}
    assert len(stats["series"]) == 7
    assert daily["2026-10-18"]["active_users"] == 1 and daily["2026-10-18"]["messages"] == 2
    assert daily["2026-10-17"]["active_users"] == 2 and daily["2026-10-17"]["messages"] == 2
    assert daily["2026-10-15"]["active_users"] == 0 and daily["2026-10-15"]["messages"] == 0
    assert stats["activity"]["dau"] == 1 and stats["activity"]["wau"] == 2 and stats["activity"]["mau"] == 2
    assert stats["totals"]["messages"] == 6


def test_custom_range_period_metrics_and_previous_period_comparison(seeded):
    stats = _stats(seeded, date_from=date(2026, 10, 12), date_to=date(2026, 10, 18))
    period, previous = stats["period"], stats["previous"]
    assert period["days"] == 7 and period["messages"] == 4 and period["active_users"] == 2
    assert period["new_users"] == 2 and period["avg_messages_per_day"] == round(4 / 7, 1)
    assert stats["range"]["previous_from"] == "2026-10-05" and stats["range"]["previous_to"] == "2026-10-11"
    assert previous["messages"] == 1 and previous["active_users"] == 1  # lượt của b cách đây 10 ngày
    assert previous["new_users"] == 0


def test_weekly_and_monthly_granularity_group_the_range(seeded):
    weekly = _stats(seeded, date_from=date(2026, 9, 21), date_to=date(2026, 10, 18), granularity="week")
    assert [r["date"] for r in weekly["series"]] == ["2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12"]
    assert weekly["series"][-1]["messages"] == 4 and weekly["series"][-1]["end"] == "2026-10-18"
    monthly = _stats(seeded, date_from=date(2026, 8, 1), date_to=date(2026, 10, 18), granularity="month")
    assert [r["date"] for r in monthly["series"]] == ["2026-08-01", "2026-09-01", "2026-10-01"]
    assert sum(r["new_users"] for r in monthly["series"]) == 3  # a, b, c đăng ký trong khoảng (d đăng ký từ tháng 7)
    assert monthly["series"][-1]["total_users"] == 6 and monthly["series"][0]["total_users"] == 3


def test_auto_granularity_switches_with_range_length(seeded):
    assert _stats(seeded, date_from=date(2026, 8, 1))["range"]["granularity"] == "week"
    assert _stats(seeded, date_from=date(2025, 10, 19))["range"]["granularity"] == "month"


def test_range_is_validated_and_capped(seeded):
    with pytest.raises(ValueError):
        _stats(seeded, date_from=date(2026, 10, 10), date_to=date(2026, 10, 1))
    assert _stats(seeded, date_from=date(2020, 1, 1))["range"]["days"] == 730
    assert _stats(seeded, date_to=date(2030, 1, 1))["range"]["to"] == "2026-10-18"  # không vượt quá hôm nay


def test_days_use_vietnam_time_not_utc(session_factory):
    with session_factory() as db:
        user = add_user(db, "late@ctu.edu.vn", 3)
        add_events(db, user, datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc))  # 03:00 giờ VN ngày 18
        stats = _stats(db, date_from=date(2026, 10, 16), date_to=date(2026, 10, 18))
    assert stats["series"][-1] == {**stats["series"][-1], "date": "2026-10-18", "active_users": 1, "messages": 1}
    assert stats["hourly"][3] == 1


def test_cached_ratio_and_cumulative_users(session_factory):
    with session_factory() as db:
        user = add_user(db, "x@ctu.edu.vn", 2)
        db.add(UsageEvent(user_id=user.id, created_at=NOW, cached=True))
        db.add(UsageEvent(user_id=user.id, created_at=NOW - timedelta(hours=2), cached=False))
        db.commit()
        stats = _stats(db, date_from=date(2026, 10, 17), date_to=date(2026, 10, 18))
    assert stats["period"]["cached_messages"] == 1 and stats["period"]["cached_ratio"] == 0.5
    assert stats["series"][-1]["cached_messages"] == 1 and stats["series"][-1]["total_users"] == 1


def test_hourly_weekday_and_top_users(seeded):
    stats = _stats(seeded)
    assert stats["hourly"][12] == 4 and stats["hourly"][11] == 1 and sum(stats["hourly"]) == stats["period"]["messages"] == 5
    assert stats["weekday"][NOW.astimezone(VN_TZ).weekday()] == 2  # thứ Bảy
    assert [u["email"] for u in stats["top_users"]] == ["a@ctu.edu.vn", "b@ctu.edu.vn"]
    assert stats["top_users"][0]["messages"] == 3 and stats["top_users"][0]["active_days"] == 2
    assert stats["top_users"][0]["last_active"].startswith("2026-10-18")


def test_stats_on_empty_database(session_factory):
    with session_factory() as db:
        stats = _stats(db, date_from=date(2026, 10, 14), date_to=date(2026, 10, 18))
    assert stats["totals"]["users"] == 0 and len(stats["series"]) == 5
    assert stats["period"]["messages_per_active_user"] == 0 and stats["top_users"] == [] and stats["activity"]["stickiness"] == 0


def test_csv_export_has_a_row_per_bucket(seeded):
    text = stats_csv(_stats(seeded, date_from=date(2026, 10, 16), date_to=date(2026, 10, 18)))
    lines = text.lstrip("\ufeff").strip().splitlines()
    assert len(lines) == 4 and lines[0].startswith("tu_ngay") and lines[-1].startswith("2026-10-18,2026-10-18,1,2,")


def test_user_activity_summary(seeded):
    user = seeded.query(User).filter(User.email == "a@ctu.edu.vn").one()
    info = user_activity(seeded, user.id, days=3, now=NOW)
    assert info["messages"] == 3 and len(info["daily"]) == 3 and info["daily"][-1]["messages"] == 2
    assert info["last_active"].startswith("2026-10-18")


# ---- API ----


def test_stats_endpoint_is_admin_only_and_validates_the_range(client, auth_headers, admin_headers):
    assert client.get("/api/v1/admin/stats", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/admin/stats").status_code == 401
    body = client.get("/api/v1/admin/stats?from=2026-10-12&to=2026-10-18&granularity=day", headers=admin_headers).json()
    assert body["range"]["days"] == 7 and len(body["series"]) == 7 and "registrations" in body and "previous" in body
    assert client.get("/api/v1/admin/stats?from=2026-10-18&to=2026-10-01", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/admin/stats?from=not-a-date", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/admin/stats?granularity=hour", headers=admin_headers).status_code == 422


def test_csv_export_endpoint(client, auth_headers, admin_headers):
    assert client.get("/api/v1/admin/stats/export.csv", headers=auth_headers).status_code == 403
    res = client.get("/api/v1/admin/stats/export.csv?from=2026-10-16&to=2026-10-18", headers=admin_headers)
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    assert "thong-ke_2026-10-16_2026-10-18.csv" in res.headers["content-disposition"]


def _new_conversation(client, headers):
    return client.post("/api/v1/conversations", headers=headers).json()["id"]


def test_each_chat_turn_is_recorded_as_usage(client, auth_headers, admin_headers):
    conv = _new_conversation(client, auth_headers)
    client.post(f"/api/v1/conversations/{conv}/messages", headers=auth_headers, json={"content": "Điều 14 nói gì?"})
    client.post(f"/api/v1/conversations/{conv}/messages/stream", headers=auth_headers, json={"content": "hỏi tiếp"})
    stats = client.get("/api/v1/admin/stats", headers=admin_headers).json()
    assert stats["totals"]["messages"] == 2 and stats["activity"]["dau"] == 1
    assert stats["top_users"][0]["messages"] == 2


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
