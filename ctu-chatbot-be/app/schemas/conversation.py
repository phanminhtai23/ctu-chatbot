import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_ATTACHMENTS = 3  # số tệp tối đa kèm theo một tin nhắn
DEFAULT_ATTACHMENT_PROMPT = "Hãy đọc tệp đính kèm và tóm tắt nội dung chính giúp mình."  # khi người dùng chỉ gửi tệp, không gõ chữ


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class SourceOut(BaseModel):
    """Một tham chiếu tới văn bản quy định: bấm vào để xem đúng đoạn trong PDF."""

    article: int | None = None  # số Điều của quy chế; None nếu là nguồn web
    n: int | None = None  # số thứ tự [n] mà câu trả lời dùng để trích nguồn web
    title: str
    url: str | None = None  # chỉ có ở nguồn web (câu hỏi ngoài quy chế được tìm trên web)


class AttachmentOut(BaseModel):
    """Tệp (PDF / ảnh) đính kèm một tin nhắn của người dùng; `url` mở được trong tab mới để xem lại."""

    id: str
    filename: str
    content_type: str
    size_bytes: int
    url: str


class ChatMessageOut(BaseModel):
    id: str  # id tin nhắn trong LangGraph; dùng làm `message_id` khi gửi feedback
    role: Literal["user", "assistant"]
    content: str
    created_at: str | None
    duration_seconds: float | None = None  # thời gian chờ chatbot trả lời (chỉ tin của bot)
    sources: list[SourceOut] = Field(default_factory=list)  # tham chiếu quy định (chỉ tin của bot)
    cached: bool = False  # câu trả lời có sẵn của câu hỏi gợi ý (không gọi LLM)
    author_name: str | None = None  # tin của người dùng do người khác gửi trong cuộc trò chuyện được chia sẻ
    attachments: list[AttachmentOut] = Field(default_factory=list)  # tệp đính kèm (chỉ tin của người dùng)


class ConversationDetail(ConversationOut):
    messages: list[ChatMessageOut]
    access: str = "owner"  # quyền của người đang xem: owner | chat | view
    owner_name: str = ""  # tên chủ cuộc trò chuyện (hiện khi xem cuộc trò chuyện được chia sẻ)
    shared: bool = False  # cuộc trò chuyện đang được chia sẻ cho ai đó (để FE cập nhật tin mới của người khác)


class SendMessageIn(BaseModel):
    content: str = Field(default="", max_length=4000)
    # Tệp đã tải lên qua POST /me/files (của chính người gửi). Chỉ gửi tệp, không gõ chữ cũng được.
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)

    @field_validator("content")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _not_empty(self) -> "SendMessageIn":
        if not self.content and not self.attachment_ids:
            raise ValueError("content must not be blank")
        return self

    @property
    def text(self) -> str:
        return self.content or DEFAULT_ATTACHMENT_PROMPT


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
