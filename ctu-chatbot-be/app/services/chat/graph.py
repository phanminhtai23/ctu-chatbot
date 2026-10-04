import time
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Protocol

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import StreamWriter

from app.core.config import settings
from app.services.chat.text import message_text
from app.services.llm.gemini import LLMError

# CHƯA có kho tài liệu (RAG) nối vào: chưa có `admin-document-vectorization`. Vì vậy prompt yêu cầu
# bot không bịa điều/khoản/con số cụ thể. Khi có RAG, thêm node `retrieve` trước `generate`.
SYSTEM_PROMPT = """Bạn là trợ lý hỏi đáp về quy chế công tác học vụ dành cho sinh viên Trường Đại học Cần Thơ (CTU).

Quy tắc:
- NGÔN NGỮ (quan trọng nhất): luôn trả lời bằng đúng ngôn ngữ của tin nhắn mới nhất của người dùng. Người dùng hỏi tiếng Anh thì trả lời hoàn toàn bằng tiếng Anh (Always reply in English when the user writes in English); hỏi tiếng Việt thì trả lời tiếng Việt. Chỉ khi không xác định được ngôn ngữ mới dùng tiếng Việt.
- Trả lời ngắn gọn, rõ ràng, thân thiện.
- Hiện tại bạn CHƯA được cung cấp văn bản quy chế chính thức để tra cứu. Vì vậy KHÔNG được bịa số điều, số khoản, con số, tỉ lệ hay thời hạn cụ thể của CTU. Nếu không chắc, hãy nói thẳng là chưa chắc và khuyên sinh viên đối chiếu văn bản quy định chính thức hoặc hỏi phòng đào tạo/cố vấn học tập.
- Có thể giải thích khái niệm chung (ví dụ cách tính điểm trung bình có trọng số theo tín chỉ) nhưng nói rõ đó là cách hiểu chung, không phải trích dẫn quy chế.
- Chỉ nhận nhiệm vụ liên quan đến học vụ và việc học ở đại học; lịch sự từ chối các yêu cầu không liên quan.
- Ghi nhớ và dùng thông tin người dùng đã nói trước đó trong cuộc trò chuyện này."""


class ChatModel(Protocol):
    """Thứ duy nhất đồ thị cần từ LLM; GeminiClient và bản giả trong test đều đáp ứng."""

    def stream(self, messages: list[BaseMessage]) -> Iterator[AIMessageChunk]: ...


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def window(messages: list[BaseMessage], size: int) -> list[BaseMessage]:
    """`size` tin gần nhất gửi cho LLM (lịch sử đầy đủ vẫn nằm trong checkpoint).

    Gemini yêu cầu lượt đầu là của người dùng, nên bỏ các tin của bot nằm đầu đoạn bị cắt.
    """
    recent = messages[-size:] if size > 0 else list(messages)
    while recent and not isinstance(recent[0], HumanMessage):
        recent = recent[1:]
    return recent


def build_chat_graph(llm: ChatModel, checkpointer: BaseCheckpointSaver):
    def generate(state: MessagesState, writer: StreamWriter) -> dict:
        started = time.monotonic()
        history = window(state["messages"], settings.chat_history_window)

        parts: list[str] = []
        for chunk in llm.stream([SystemMessage(content=SYSTEM_PROMPT), *history]):
            text = message_text(chunk)
            if text:
                parts.append(text)
                writer({"token": text})  # đẩy từng đoạn ra cho client (chỉ có tác dụng khi stream_mode="custom")

        answer = "".join(parts)
        if not answer.strip():
            raise LLMError("Gemini returned an empty reply (có thể bị chặn nội dung)")

        reply = AIMessage(
            content=answer,
            additional_kwargs={
                "created_at": now_iso(),
                # Thời gian chờ chatbot trả lời, lưu cùng tin nhắn nên mở lại cuộc trò chuyện vẫn hiển thị.
                "duration_seconds": round(time.monotonic() - started, 1),
            },
        )
        return {"messages": [reply]}

    builder = StateGraph(MessagesState)
    builder.add_node("generate", generate)
    builder.add_edge(START, "generate")
    builder.add_edge("generate", END)
    return builder.compile(checkpointer=checkpointer)
