from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Feedback, User
from app.schemas.feedback import FeedbackCreate, FeedbackCreated

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackCreated, status_code=status.HTTP_201_CREATED)
def create_feedback(
    body: FeedbackCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = Feedback(user_id=user.id, **body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return FeedbackCreated(id=item.id)
