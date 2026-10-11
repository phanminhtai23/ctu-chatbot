import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class SourceOut(BaseModel):
    """Một tham chiếu tới văn bản quy định: bấm vào để xem đúng đoạn trong PDF."""

    article: int
    title: str


class ChatMessageOut(BaseModel):
    id: str  # id tin nhắn trong LangGraph; dùng làm `message_id` khi gửi feedback
    role: Literal["user", "assistant"]
    content: str
    created_at: str | None
    duration_seconds: float | None = None  # thời gian chờ chatbot trả lời (chỉ tin của bot)
    sources: list[SourceOut] = Field(default_factory=list)  # tham chiếu quy định (chỉ tin của bot)


class ConversationDetail(ConversationOut):
    messages: list[ChatMessageOut]


class SendMessageIn(BaseModel):
    content: str = Field(max_length=4000)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be blank")
        return v


class SendMessageOut(BaseModel):
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    conversation: ConversationOut


class RenameConversationIn(BaseModel):
    title: str = Field(max_length=200)

    @field_validator("title")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("title must not be blank")
        return v
