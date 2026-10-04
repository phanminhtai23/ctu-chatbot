from collections.abc import Iterator

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage


class FakeLLM:
    """LLM giả: ghi lại các lần gọi để test xem lịch sử có được gửi kèm không."""

    def __init__(self):
        self.calls: list[list[BaseMessage]] = []
        self.error: Exception | None = None

    def stream(self, messages: list[BaseMessage]) -> Iterator[AIMessageChunk]:
        self.calls.append(list(messages))
        if self.error is not None:
            raise self.error
        last_user = [m for m in messages if isinstance(m, HumanMessage)][-1]
        text = f"trả lời #{len(self.calls)} cho: {last_user.content}"
        # Chia thành nhiều đoạn nhỏ như Gemini thật.
        words = text.split(" ")
        for i, word in enumerate(words):
            yield AIMessageChunk(content=word + (" " if i < len(words) - 1 else ""))


class FakeApiError(Exception):
    """Giống lỗi của Gemini SDK: có `code` (HTTP status) và nội dung chứa trạng thái."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
