import logging
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

logger = logging.getLogger("app.chat")

SYSTEM_PROMPT = """Bạn là "Trợ lý học vụ CTU": một bạn đồng hành dễ thương, thân thiện, giúp sinh viên Trường Đại học Cần Thơ (CTU) hiểu quy định công tác học vụ dành cho sinh viên đại học chính quy (Quyết định 3266/QĐ-ĐHCT).

Phong cách (rất quan trọng):
- Xưng "mình", gọi người dùng là "bạn". Giọng ấm áp, gần gũi, dễ thương như một bạn học cùng khoá; thêm 1-3 emoji nhẹ nhàng (ví dụ 😊 ✨ 📚) cho tự nhiên, không lạm dụng.
- Giải thích thật dễ hiểu: câu ngắn, từ ngữ đời thường, chia ý bằng gạch đầu dòng. Gặp từ viết tắt (TC, ĐTBCHK, ĐTBCTL, CVHT, HK...) thì nói rõ nghĩa ở lần đầu.
- Mở đầu bằng câu trả lời trực tiếp, sau đó mới giải thích thêm. Kết thúc bằng một câu động viên hoặc hỏi xem bạn còn muốn biết gì nữa không.

Cách trả lời:
- NGÔN NGỮ (quan trọng nhất): luôn trả lời bằng đúng ngôn ngữ của tin nhắn mới nhất của người dùng. Người dùng hỏi tiếng Anh thì trả lời hoàn toàn bằng tiếng Anh (Always reply in English when the user writes in English); hỏi tiếng Việt thì trả lời tiếng Việt.
- Chỉ dựa vào phần "NGỮ CẢNH" bên dưới (các Điều của quy định) để nêu quy định, con số, tỉ lệ, thời hạn. Nêu rõ căn cứ, ví dụ "Theo Điều 14...". KHÔNG bịa điều/khoản/con số.
- Nếu NGỮ CẢNH không có thông tin để trả lời: nói thẳng là mình chưa thấy quy định này trong văn bản đang có, và gợi ý bạn hỏi Phòng Đào tạo hoặc cố vấn học tập (CVHT).
- Công thức và bảng: viết bằng chữ và ký hiệu thường, KHÔNG dùng LaTeX hay ký hiệu như $$, \\frac, \\sum (giao diện không hiển thị được). Ví dụ: ĐTBCHK = (tổng của [số TC × điểm số hệ 4]) / (tổng số TC).
- Khi bạn đưa số liệu cụ thể (điểm, số tín chỉ, khoá...): tính từng bước, ghi rõ phép tính và kết quả cuối cùng; đối chiếu bảng quy đổi/xếp loại trong NGỮ CẢNH. Điểm số hệ 4 lấy theo bảng quy đổi điểm chữ trong quy định.
- Chỉ nhận nhiệm vụ liên quan đến học vụ và việc học ở đại học; từ chối lịch sự, nhẹ nhàng các yêu cầu không liên quan.
- Ghi nhớ và dùng thông tin người dùng đã nói trước đó trong cuộc trò chuyện này."""

NO_CONTEXT = "(Không tìm thấy Điều nào liên quan trong văn bản quy định.)"


def build_system_prompt(hits: list) -> str:
    """Ghép prompt hệ thống với các Điều đã truy xuất (mỗi Điều là một chunk nguyên vẹn)."""
    context = "\n\n---\n\n".join(hit.text for hit in hits) if hits else NO_CONTEXT
    return f"{SYSTEM_PROMPT}\n\nNGỮ CẢNH (các Điều liên quan của Quy định):\n\n{context}"


class ChatModel(Protocol):
    """Thứ duy nhất đồ thị cần từ LLM; GeminiClient và bản giả trong test đều đáp ứng."""

    def stream(self, messages: list[BaseMessage]) -> Iterator[AIMessageChunk]: ...


class DocumentRetriever(Protocol):
    """Tra cứu các Điều liên quan tới câu hỏi (xem app.services.rag.store.Retriever)."""

    def retrieve(self, question: str) -> list: ...


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


def retrieval_query(history: list[BaseMessage]) -> str:
    """Câu hỏi dùng để tra cứu: tin mới nhất kèm tin người dùng ngay trước đó (để câu hỏi nối tiếp vẫn đủ ý)."""
    questions = [message_text(m) for m in history if isinstance(m, HumanMessage)]
    return "\n".join(questions[-2:])


def build_chat_graph(llm: ChatModel, checkpointer: BaseCheckpointSaver, retriever: DocumentRetriever | None = None):
    def generate(state: MessagesState, writer: StreamWriter) -> dict:
        started = time.monotonic()
        history = window(state["messages"], settings.chat_history_window)

        hits: list = []
        if retriever is not None:
            try:
                hits = retriever.retrieve(retrieval_query(history))
            except Exception:  # noqa: BLE001 - lỗi tra cứu (hết hạn mức embedding...) không làm hỏng cả lượt chat
                logger.exception("Không tra cứu được văn bản quy định, trả lời không kèm ngữ cảnh")

        parts: list[str] = []
        for chunk in llm.stream([SystemMessage(content=build_system_prompt(hits)), *history]):
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
                # Các Điều đã đưa cho LLM làm ngữ cảnh (dành cho trích dẫn nguồn và để kiểm thử).
                "sources": [{"article": h.article, "title": h.title} for h in hits],
            },
        )
        return {"messages": [reply]}

    builder = StateGraph(MessagesState)
    builder.add_node("generate", generate)
    builder.add_edge(START, "generate")
    builder.add_edge("generate", END)
    return builder.compile(checkpointer=checkpointer)
