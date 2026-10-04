import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FeedbackType = Literal["answer_issue", "general"]
FeedbackCategory = Literal["wrong_answer", "wrong_citation", "outdated", "bug", "suggestion", "other"]

ALLOWED_CATEGORIES: dict[str, set[str]] = {
    "answer_issue": {"wrong_answer", "wrong_citation", "outdated", "other"},
    "general": {"bug", "suggestion", "other"},
}


class FeedbackCreate(BaseModel):
    type: FeedbackType
    category: FeedbackCategory
    message: str = Field(default="", max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=64)
    message_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _check(self) -> "FeedbackCreate":
        self.message = self.message.strip()
        if self.category not in ALLOWED_CATEGORIES[self.type]:
            raise ValueError(f"category '{self.category}' is not valid for type '{self.type}'")
        if self.category == "other" and not self.message:
            raise ValueError("message is required when category is 'other'")
        if self.type == "answer_issue" and not self.message_id:
            raise ValueError("message_id is required for answer_issue")
        return self


class FeedbackCreated(BaseModel):
    id: uuid.UUID
