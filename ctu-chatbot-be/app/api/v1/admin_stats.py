from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.services.usage import Granularity, compute_stats, stats_csv

router = APIRouter(prefix="/admin/stats", tags=["admin"], dependencies=[Depends(require_admin)])


def _stats(db: Session, date_from: date | None, date_to: date | None, granularity: Granularity) -> dict:
    try:
        return compute_stats(db, date_from, date_to, granularity)
    except ValueError:
        raise HTTPException(422, detail="INVALID_RANGE") from None


@router.get("")
def get_stats(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    granularity: Granularity = "auto",
    db: Session = Depends(get_db),
) -> dict:
    """Số liệu cho dashboard trong khoảng [from, to] (mặc định 30 ngày gần nhất), gom theo ngày/tuần/tháng, kèm kỳ liền
    trước để so sánh, DAU/WAU/MAU, giờ cao điểm, tần suất sử dụng và người dùng nhiều nhất."""
    return _stats(db, date_from, date_to, granularity)


@router.get("/export.csv")
def export_csv(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    granularity: Granularity = "auto",
    db: Session = Depends(get_db),
) -> Response:
    stats = _stats(db, date_from, date_to, granularity)
    name = f"thong-ke_{stats['range']['from']}_{stats['range']['to']}.csv"
    return Response(
        stats_csv(stats),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
