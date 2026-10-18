from fastapi import APIRouter
from pydantic import BaseModel

from app.services.chat import suggested

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


class SuggestionOut(BaseModel):
    id: str
    category: str
    question: str


# Công khai (không cần đăng nhập): chỉ là danh sách câu hỏi mẫu, dùng cho cả trang chủ lẫn khung chat.
@router.get("", response_model=list[SuggestionOut])
def list_suggestions() -> list[SuggestionOut]:
    """Các câu hỏi gợi ý. Gửi đúng nội dung câu hỏi vào chat sẽ nhận câu trả lời có sẵn, không gọi LLM."""
    return [SuggestionOut(id=s.id, category=s.category, question=s.question) for s in suggested.load()]
