"""Ghi và thống kê mức sử dụng chatbot cho trang admin.

Ngày/giờ tính theo giờ Việt Nam (UTC+7, không có giờ mùa hè) để "hôm nay" và "giờ cao điểm" khớp với người dùng.
Số liệu nhỏ (vài nghìn user) nên gom nhóm bằng Python cho đơn giản và chạy giống nhau trên Postgres lẫn SQLite khi test.
"""

import logging
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, UsageEvent, User

logger = logging.getLogger("app.usage")

VN_TZ = timezone(timedelta(hours=7))
REGISTRATION_WINDOWS = {"week": 7, "month": 30, "six_months": 182, "year": 365}
MAX_DAYS = 365
TOP_USERS = 10


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


def _local_day(value: datetime) -> date:
    return _aware(value).astimezone(VN_TZ).date()


def _daterange(end: date, days: int) -> list[date]:
    return [end - timedelta(days=i) for i in range(days - 1, -1, -1)]


def compute_stats(db: Session, days: int = 30, now: datetime | None = None) -> dict:
    days = max(1, min(MAX_DAYS, days))
    now = _aware(now) if now else datetime.now(timezone.utc)
    today = now.astimezone(VN_TZ).date()
    window = _daterange(today, days)
    window_start = window[0]

    users = db.execute(select(User.id, User.email, User.name, User.created_at, User.is_active, User.role)).all()
    events = db.execute(select(UsageEvent.user_id, UsageEvent.created_at)).all()

    # Đăng ký mới theo mốc thời gian (tính theo ngày, bao gồm hôm nay).
    created_days = [_local_day(u.created_at) for u in users]
    registrations = {
        key: sum(1 for d in created_days if (today - d).days < span) for key, span in REGISTRATION_WINDOWS.items()
    }
    reg_by_day = Counter(created_days)

    per_day_users: dict[date, set] = defaultdict(set)
    per_day_msgs: Counter[date] = Counter()
    hourly = [0] * 24
    weekday = [0] * 7
    window_msgs_by_user: Counter = Counter()
    window_days_by_user: dict = defaultdict(set)
    active_ids_7d: set = set()
    active_ids_30d: set = set()
    for event in events:
        local = _aware(event.created_at).astimezone(VN_TZ)
        day = local.date()
        age = (today - day).days
        if age < 7:
            active_ids_7d.add(event.user_id)
        if age < 30:
            active_ids_30d.add(event.user_id)
        if day >= window_start:
            per_day_users[day].add(event.user_id)
            per_day_msgs[day] += 1
            hourly[local.hour] += 1
            weekday[local.weekday()] += 1
            window_msgs_by_user[event.user_id] += 1
            window_days_by_user[event.user_id].add(day)

    usage_daily = [
        {"date": d.isoformat(), "active_users": len(per_day_users.get(d, ())), "messages": per_day_msgs.get(d, 0)} for d in window
    ]
    window_messages = sum(per_day_msgs.values())
    user_days = sum(len(v) for v in per_day_users.values())  # tổng (user, ngày có dùng)
    by_id = {u.id: u for u in users}
    top = [
        {
            "email": by_id[uid].email,
            "name": by_id[uid].name,
            "messages": count,
            "active_days": len(window_days_by_user[uid]),
        }
        for uid, count in window_msgs_by_user.most_common(TOP_USERS)
        if uid in by_id
    ]

    return {
        "generated_at": now.isoformat(),
        "days": days,
        "totals": {
            "users": len(users),
            "active_accounts": sum(1 for u in users if u.is_active),
            "admins": sum(1 for u in users if u.role == "admin"),
            "conversations": db.scalar(select(func.count()).select_from(Conversation)) or 0,
            "messages": len(events),
            "messages_today": per_day_msgs.get(today, 0) if days >= 1 else 0,
            "active_today": len(per_day_users.get(today, ())),
            "active_7d": len(active_ids_7d),
            "active_30d": len(active_ids_30d),
        },
        "registrations": registrations,
        "registrations_daily": [{"date": d.isoformat(), "count": reg_by_day.get(d, 0)} for d in window],
        "usage_daily": usage_daily,
        "hourly": hourly,
        "weekday": weekday,
        "frequency": {
            "window_messages": window_messages,
            "avg_messages_per_day": round(window_messages / days, 1),
            "avg_active_users_per_day": round(user_days / days, 1),
            "avg_messages_per_active_user_per_day": round(window_messages / user_days, 1) if user_days else 0,
            "avg_messages_per_user": round(window_messages / len(window_msgs_by_user), 1) if window_msgs_by_user else 0,
            "top_users": top,
        },
    }


def user_activity(db: Session, user_id: uuid.UUID, days: int = 30, now: datetime | None = None) -> dict:
    """Mức dùng của một user: tổng lượt, lần dùng đầu/cuối và số lượt từng ngày gần đây."""
    now = _aware(now) if now else datetime.now(timezone.utc)
    today = now.astimezone(VN_TZ).date()
    times = [r[0] for r in db.execute(select(UsageEvent.created_at).where(UsageEvent.user_id == user_id)).all()]
    per_day = Counter(_local_day(t) for t in times)
    return {
        "messages": len(times),
        "conversations": db.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)) or 0,
        "first_active": min(times).isoformat() if times else None,
        "last_active": max(times).isoformat() if times else None,
        "daily": [{"date": d.isoformat(), "messages": per_day.get(d, 0)} for d in _daterange(today, days)],
    }
