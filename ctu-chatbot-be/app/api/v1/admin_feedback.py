import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_chat_graph, require_admin
from app.db.session import get_db
from app.models import Feedback, User
from app.schemas.admin_feedback import AdminFeedbackOut, FeedbackStatusUpdate
from app.services.chat.service import find_exchange

router = APIRouter(prefix="/admin/feedback", tags=["admin"], dependencies=[Depends(require_admin)])


def _to_out(item: Feedback, user_email: str, graph=None) -> AdminFeedbackOut:
    question, answer = item.question, item.answer
    if item.type == "answer_issue" and answer is None and graph is not None:
        question, answer = find_exchange(graph, item.conversation_id, item.message_id)  # phản hồi cũ chưa có bản chụp
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
        question=question,
        answer=answer,
    )


@router.get("", response_model=list[AdminFeedbackOut])
def list_feedback(db: Session = Depends(get_db), graph=Depends(get_chat_graph)):
    rows = db.execute(
        select(Feedback, User.email)
        .join(User, User.id == Feedback.user_id)
        .order_by(Feedback.created_at.desc())
    ).all()
    return [_to_out(item, email, graph) for item, email in rows]


@router.get("/unread-count")
def unread_feedback_count(db: Session = Depends(get_db)):
    """Số phản hồi chưa đọc (status = new) để hiện huy hiệu trên tab admin."""
    count = db.scalar(select(func.count()).select_from(Feedback).where(Feedback.status == "new"))
    return {"count": count or 0}


@router.patch("/{feedback_id}", response_model=AdminFeedbackOut)
def update_feedback_status(
    feedback_id: uuid.UUID,
    body: FeedbackStatusUpdate,
    db: Session = Depends(get_db),
    graph=Depends(get_chat_graph),
):
    item = db.get(Feedback, feedback_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    item.status = body.status
    db.commit()
    db.refresh(item)
    return _to_out(item, db.get(User, item.user_id).email, graph)
