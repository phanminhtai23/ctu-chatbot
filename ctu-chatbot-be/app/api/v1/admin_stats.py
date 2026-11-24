from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models import UsageEvent
from app.services.usage import MAX_RANGE_DAYS, Granularity, compute_stats, stats_csv

router = APIRouter(prefix="/admin/stats", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/gemini-quota")
def gemini_quota(db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    pacific = now.astimezone(ZoneInfo("America/Los_Angeles"))
    day_start = pacific.replace(hour=0, minute=0, second=0, microsecond=0)
    next_day = day_start + timedelta(days=1)

    def completed_since(start: datetime) -> int:
        return db.scalar(select(func.count()).select_from(UsageEvent).where(
            UsageEvent.cached.is_(False), UsageEvent.created_at >= start, UsageEvent.created_at <= now,
        )) or 0

    keys = len(settings.gemini_api_keys)
    minute_start = now - timedelta(minutes=1)
    day_start_utc = day_start.astimezone(timezone.utc)
    minute = completed_since(minute_start)
    day = completed_since(day_start_utc)
    rpm_limit = keys * settings.gemini_quota_rpm_per_project
    rpd_limit = keys * settings.gemini_quota_rpd_per_project
    return {
        "model": settings.llm_model, "key_count": keys,
        "rpm_per_project": settings.gemini_quota_rpm_per_project,
        "rpd_per_project": settings.gemini_quota_rpd_per_project,
        "minute": {"completed_chats": minute, "capacity": rpm_limit, "estimated_remaining": max(0, rpm_limit - minute)},
        "day": {"completed_chats": day, "capacity": rpd_limit, "estimated_remaining": max(0, rpd_limit - day)},
        "day_reset_at": next_day.astimezone(timezone.utc).isoformat(), "generated_at": now.isoformat(),
    }


def _stats(db: Session, date_from: date | None, date_to: date | None, granularity: Granularity, days: int | None) -> dict:
    try:
        return compute_stats(db, date_from, date_to, granularity, days=days)
    except ValueError:
        raise HTTPException(422, detail="INVALID_RANGE") from None


@router.get("")
def get_stats(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    granularity: Granularity = "auto",
    days: int | None = Query(None, ge=1, le=MAX_RANGE_DAYS, description="N ngày gần nhất (dùng khi không có `from`)"),
    db: Session = Depends(get_db),
) -> dict:
    """Số liệu cho dashboard trong khoảng [from, to] (mặc định 30 ngày gần nhất), gom theo ngày/tuần/tháng, kèm kỳ liền
    trước để so sánh, DAU/WAU/MAU, giờ cao điểm, tần suất sử dụng và người dùng nhiều nhất."""
    return _stats(db, date_from, date_to, granularity, days)


@router.get("/export.csv")
def export_csv(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    granularity: Granularity = "auto",
    days: int | None = Query(None, ge=1, le=MAX_RANGE_DAYS),
    db: Session = Depends(get_db),
) -> Response:
    stats = _stats(db, date_from, date_to, granularity, days)
    name = f"thong-ke_{stats['range']['from']}_{stats['range']['to']}.csv"
    return Response(
        stats_csv(stats),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
