"""Ghi và thống kê mức sử dụng chatbot cho trang admin.

Ngày/giờ tính theo giờ Việt Nam (UTC+7, không có giờ mùa hè) để "hôm nay" và "giờ cao điểm" khớp với người dùng.
Số liệu nhỏ (vài nghìn user) nên gom nhóm bằng Python cho đơn giản và chạy giống nhau trên Postgres lẫn SQLite khi test.
"""

import csv
import io
import logging
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, UsageEvent, User

logger = logging.getLogger("app.usage")

VN_TZ = timezone(timedelta(hours=7))
REGISTRATION_WINDOWS = {"week": 7, "month": 30, "six_months": 182, "year": 365}
MAX_RANGE_DAYS = 730
DEFAULT_RANGE_DAYS = 30
TOP_USERS = 10

Granularity = Literal["auto", "day", "week", "month"]


def record_usage(db: Session, user_id: uuid.UUID, conversation_id: uuid.UUID | None, cached: bool = False) -> None:
    """Ghi một lượt dùng. Lỗi ghi thống kê không bao giờ được làm hỏng câu trả lời cho người dùng."""
    try:
        db.add(UsageEvent(user_id=user_id, conversation_id=conversation_id, cached=cached))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Không ghi được lượt dùng", exc_info=True)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)  # SQLite trả về datetime không múi giờ


def _local(value: datetime) -> datetime:
    return _aware(value).astimezone(VN_TZ)


def _local_day(value: datetime) -> date:
    return _local(value).date()


def _day_start_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=VN_TZ).astimezone(timezone.utc)


def _daterange(end: date, days: int) -> list[date]:
    return [end - timedelta(days=i) for i in range(days - 1, -1, -1)]


def resolve_range(date_from: date | None, date_to: date | None, today: date, days: int | None = None) -> tuple[date, date]:
    """Khoảng ngày [start, end] (gồm cả hai đầu) để thống kê. `days` = N ngày gần nhất (tính theo ngày hôm nay của server,
    nên "hôm nay" luôn là ngày giờ Việt Nam bất kể múi giờ của trình duyệt). Mặc định 30 ngày; không vượt quá hôm nay."""
    end = min(date_to or today, today)
    span = days if days and date_from is None else DEFAULT_RANGE_DAYS
    start = date_from or end - timedelta(days=span - 1)
    if start > end:
        raise ValueError("from must not be after to")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        start = end - timedelta(days=MAX_RANGE_DAYS - 1)
    return start, end


def resolve_granularity(granularity: Granularity, days: int) -> Literal["day", "week", "month"]:
    if granularity != "auto":
        return granularity
    return "day" if days <= 62 else ("week" if days <= 240 else "month")


def _bucket_start(day: date, granularity: str) -> date:
    if granularity == "week":
        return day - timedelta(days=day.weekday())  # thứ Hai đầu tuần
    if granularity == "month":
        return day.replace(day=1)
    return day


def _next_bucket(start: date, granularity: str) -> date:
    if granularity == "week":
        return start + timedelta(days=7)
    if granularity == "month":
        return (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start + timedelta(days=1)


def _metrics(events: list, users: list, convs: list[datetime], start: date, end: date) -> dict:
    """Các chỉ số tổng hợp của một khoảng ngày (dùng cho cả khoảng đang xem lẫn khoảng liền trước để so sánh)."""
    days = (end - start).days + 1
    per_day_users: dict[date, set] = defaultdict(set)
    messages = cached = 0
    for e in events:
        day = _local_day(e.created_at)
        if start <= day <= end:
            per_day_users[day].add(e.user_id)
            messages += 1
            cached += 1 if e.cached else 0
    active = set().union(*per_day_users.values()) if per_day_users else set()
    return {
        "days": days,
        "messages": messages,
        "cached_messages": cached,
        "active_users": len(active),
        "new_users": sum(1 for u in users if start <= _local_day(u.created_at) <= end),
        "conversations": sum(1 for c in convs if start <= _local_day(c) <= end),
        "avg_messages_per_day": round(messages / days, 1),
        "avg_active_users_per_day": round(sum(len(v) for v in per_day_users.values()) / days, 1),
        "messages_per_active_user": round(messages / len(active), 1) if active else 0,
        "cached_ratio": round(cached / messages, 3) if messages else 0,
    }


def compute_stats(
    db: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: Granularity = "auto",
    now: datetime | None = None,
    days: int | None = None,
) -> dict:
    now = _aware(now) if now else datetime.now(timezone.utc)
    today = _local_day(now)
    start, end = resolve_range(date_from, date_to, today, days)
    days = (end - start).days + 1
    gran = resolve_granularity(granularity, days)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    users = db.execute(select(User.id, User.email, User.name, User.created_at, User.is_active, User.role)).all()
    conv_times = [r[0] for r in db.execute(select(Conversation.created_at)).all()]
    # Chỉ cần sự kiện từ đầu khoảng liền trước (để so sánh) và từ 30 ngày trước ngày cuối (để tính MAU).
    load_from = min(prev_start, end - timedelta(days=29))
    events = db.execute(
        select(UsageEvent.user_id, UsageEvent.created_at, UsageEvent.cached).where(
            UsageEvent.created_at >= _day_start_utc(load_from)
        )
    ).all()
    total_messages = db.scalar(select(func.count()).select_from(UsageEvent)) or 0

    # ---- chuỗi thời gian theo ngày/tuần/tháng ----
    buckets: list[date] = []
    cursor = _bucket_start(start, gran)
    while cursor <= end:
        buckets.append(cursor)
        cursor = _next_bucket(cursor, gran)
    users_in: dict[date, set] = defaultdict(set)
    msgs: Counter[date] = Counter()
    cached_msgs: Counter[date] = Counter()
    new_users: Counter[date] = Counter()
    convs: Counter[date] = Counter()
    hourly = [0] * 24
    weekday = [0] * 7
    per_user: Counter = Counter()
    days_by_user: dict = defaultdict(set)
    last_seen: dict = {}
    for e in events:
        local = _local(e.created_at)
        day = local.date()
        if not (start <= day <= end):
            continue
        b = _bucket_start(day, gran)
        users_in[b].add(e.user_id)
        msgs[b] += 1
        cached_msgs[b] += 1 if e.cached else 0
        hourly[local.hour] += 1
        weekday[local.weekday()] += 1
        per_user[e.user_id] += 1
        days_by_user[e.user_id].add(day)
        last_seen[e.user_id] = max(last_seen.get(e.user_id, local), local)
    created_days = [_local_day(u.created_at) for u in users]
    for d in created_days:
        if start <= d <= end:
            new_users[_bucket_start(d, gran)] += 1
    for c in conv_times:
        d = _local_day(c)
        if start <= d <= end:
            convs[_bucket_start(d, gran)] += 1
    series = []
    for i, b in enumerate(buckets):
        bucket_end = min(end, _next_bucket(b, gran) - timedelta(days=1))
        series.append(
            {
                "date": b.isoformat(),
                "end": bucket_end.isoformat(),
                "active_users": len(users_in.get(b, ())),
                "messages": msgs.get(b, 0),
                "cached_messages": cached_msgs.get(b, 0),
                "new_users": new_users.get(b, 0),
                "conversations": convs.get(b, 0),
                "total_users": sum(1 for d in created_days if d <= bucket_end),
            }
        )

    # ---- chỉ số kỳ này và kỳ liền trước ----
    period = _metrics(events, users, conv_times, start, end)
    previous = _metrics(events, users, conv_times, prev_start, prev_end)

    # ---- DAU / WAU / MAU tính tới ngày cuối của khoảng ----
    def active_between(a: date, b: date) -> int:
        return len({e.user_id for e in events if a <= _local_day(e.created_at) <= b})

    dau, wau, mau = active_between(end, end), active_between(end - timedelta(days=6), end), active_between(end - timedelta(days=29), end)

    by_id = {u.id: u for u in users}
    top = [
        {
            "email": by_id[uid].email,
            "name": by_id[uid].name,
            "messages": count,
            "active_days": len(days_by_user[uid]),
            "last_active": last_seen[uid].isoformat(),
        }
        for uid, count in per_user.most_common(TOP_USERS)
        if uid in by_id
    ]
    created_today = [d for d in created_days]
    return {
        "generated_at": now.isoformat(),
        "range": {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": days,
            "granularity": gran,
            "previous_from": prev_start.isoformat(),
            "previous_to": prev_end.isoformat(),
        },
        "totals": {
            "users": len(users),
            "active_accounts": sum(1 for u in users if u.is_active),
            "admins": sum(1 for u in users if u.role == "admin"),
            "conversations": len(conv_times),
            "messages": total_messages,
        },
        "period": period,
        "previous": previous,
        "activity": {
            "dau": dau,
            "wau": wau,
            "mau": mau,
            "stickiness": round(dau / mau, 3) if mau else 0,
        },
        # Mốc cố định tính từ hôm nay, không phụ thuộc bộ lọc: đăng ký mới trong 1 tuần / 1 tháng / 6 tháng / 1 năm.
        "registrations": {
            key: sum(1 for d in created_today if (today - d).days < span) for key, span in REGISTRATION_WINDOWS.items()
        },
        "series": series,
        "hourly": hourly,
        "weekday": weekday,
        "top_users": top,
    }


def stats_csv(stats: dict) -> str:
    """Bảng số liệu theo ngày/tuần/tháng của khoảng đang xem, dạng CSV (có BOM để Excel đọc đúng tiếng Việt)."""
    out = io.StringIO()
    out.write("﻿")
    writer = csv.writer(out)
    writer.writerow(["tu_ngay", "den_ngay", "nguoi_dung_hoat_dong", "luot_hoi", "luot_hoi_co_san", "dang_ky_moi", "cuoc_tro_chuyen_moi", "tong_nguoi_dung"])
    for row in stats["series"]:
        writer.writerow(
            [row["date"], row["end"], row["active_users"], row["messages"], row["cached_messages"], row["new_users"], row["conversations"], row["total_users"]]
        )
    return out.getvalue()


def user_activity(db: Session, user_id: uuid.UUID, days: int = 30, now: datetime | None = None) -> dict:
    """Mức dùng của một user: tổng lượt, lần dùng đầu/cuối và số lượt từng ngày gần đây."""
    now = _aware(now) if now else datetime.now(timezone.utc)
    today = _local_day(now)
    times = [r[0] for r in db.execute(select(UsageEvent.created_at).where(UsageEvent.user_id == user_id)).all()]
    per_day = Counter(_local_day(t) for t in times)
    return {
        "messages": len(times),
        "conversations": db.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)) or 0,
        "first_active": min(times).isoformat() if times else None,
        "last_active": max(times).isoformat() if times else None,
        "daily": [{"date": d.isoformat(), "messages": per_day.get(d, 0)} for d in _daterange(today, days)],
    }
