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
    # Câu hỏi / câu trả lời bị báo cáo (chỉ có ở loại answer_issue).
    question: str | None = None
    answer: str | None = None


class FeedbackStatusUpdate(BaseModel):
    status: FeedbackStatus
