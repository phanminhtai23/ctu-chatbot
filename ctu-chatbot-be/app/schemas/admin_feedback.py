import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.feedback import FeedbackCategory, FeedbackType

FeedbackStatus = Literal["new", "reviewed", "resolved"]


class AdminFeedbackOut(BaseModel):
    id: uuid.UUID
    type: FeedbackType
    category: FeedbackCategory
    message: str
    user_email: str
    created_at: datetime
    status: FeedbackStatus
    conversation_id: str | None
    message_id: str | None
    # Chưa có bảng conversations/messages nên chưa có nội dung hội thoại đi kèm.
    question: str | None = None
    answer: str | None = None


class FeedbackStatusUpdate(BaseModel):
    status: FeedbackStatus
