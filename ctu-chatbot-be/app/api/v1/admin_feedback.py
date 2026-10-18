import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import Feedback, User
from app.schemas.admin_feedback import AdminFeedbackOut, FeedbackStatusUpdate

router = APIRouter(prefix="/admin/feedback", tags=["admin"], dependencies=[Depends(require_admin)])


def _to_out(item: Feedback, user_email: str) -> AdminFeedbackOut:
    return AdminFeedbackOut(
        id=item.id,
        type=item.type,
        category=item.category,
        message=item.message,
        user_email=user_email,
        created_at=item.created_at,
        status=item.status,
        conversation_id=item.conversation_id,
        message_id=item.message_id,
    )


@router.get("", response_model=list[AdminFeedbackOut])
def list_feedback(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Feedback, User.email)
        .join(User, User.id == Feedback.user_id)
        .order_by(Feedback.created_at.desc())
    ).all()
    return [_to_out(item, email) for item, email in rows]


@router.get("/unread-count")
def unread_feedback_count(db: Session = Depends(get_db)):
    """Số phản hồi chưa đọc (status = new) để hiện huy hiệu trên tab admin."""
    count = db.scalar(select(func.count()).select_from(Feedback).where(Feedback.status == "new"))
    return {"count": count or 0}


@router.patch("/{feedback_id}", response_model=AdminFeedbackOut)
def update_feedback_status(
    feedback_id: uuid.UUID, body: FeedbackStatusUpdate, db: Session = Depends(get_db)
):
    item = db.get(Feedback, feedback_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    item.status = body.status
    db.commit()
    db.refresh(item)
    return _to_out(item, db.get(User, item.user_id).email)
