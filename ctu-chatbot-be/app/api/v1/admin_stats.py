from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.services.usage import MAX_DAYS, compute_stats

router = APIRouter(prefix="/admin/stats", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("")
def get_stats(days: int = Query(30, ge=1, le=MAX_DAYS), db: Session = Depends(get_db)) -> dict:
    """Số liệu cho dashboard: tổng quan, đăng ký mới theo tuần/tháng/6 tháng/năm, lượt dùng từng ngày, giờ cao điểm,
    tần suất sử dụng và người dùng nhiều nhất. `days` là độ dài khoảng thời gian cho các biểu đồ theo ngày."""
    return compute_stats(db, days)
