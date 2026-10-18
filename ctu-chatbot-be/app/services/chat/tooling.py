"""Vòng lặp gọi công cụ (tính toán, so sánh số) cho đồ thị chat.

Model được gắn sẵn công cụ ngay từ lần gọi đầu tiên và vẫn stream chữ bình thường nếu không cần tới công cụ
(không tốn thêm lần gọi). Nếu model yêu cầu gọi công cụ, ta chạy công cụ, đưa kết quả lại cho model rồi để nó
viết tiếp câu trả lời. LLM nhỏ tự tính nhẩm/so sánh hay sai ở các mốc "đúng bằng ngưỡng"; công cụ thì không.
"""

import json
import logging
import uuid
from collections.abc import Iterator, Sequence

from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage

from app.services.chat.text import message_text
from app.services.tools.calculator import CALCULATOR_TOOLS

logger = logging.getLogger("app.chat")

MAX_TOOL_ROUNDS = 4  # số lần model được gọi công cụ liên tiếp trước khi dừng (tránh vòng lặp vô hạn)


def _run_tool(by_name: dict, name: str, args: dict) -> str:
    tool = by_name.get(name)
    if tool is None:
        return f"LỖI: không có công cụ tên {name!r}."
    try:
        return str(tool.invoke(args))
    except Exception as exc:  # noqa: BLE001 - lỗi công cụ được báo lại cho model, không làm hỏng lượt chat
        logger.warning("Công cụ %s lỗi: %s", name, exc)
        return f"LỖI khi gọi công cụ {name}: {exc}"


def stream_with_tools(
    llm,
    messages: Sequence[BaseMessage],
    tools: Sequence = CALCULATOR_TOOLS,
    max_rounds: int = MAX_TOOL_ROUNDS,
    tool_log: list | None = None,
) -> Iterator[AIMessageChunk]:
    """Trả về các đoạn chữ của câu trả lời cuối cùng. `tool_log` (nếu có) được ghi {name, args, result} mỗi lần gọi."""
    by_name = {t.name: t for t in tools}
    conversation = list(messages)
    for _ in range(max_rounds + 1):
        aggregate: AIMessageChunk | None = None
        for chunk in llm.stream(conversation, tools=list(tools)):
            aggregate = chunk if aggregate is None else aggregate + chunk
            if message_text(chunk):
                yield chunk
        calls = list(getattr(aggregate, "tool_calls", None) or [])
        if not calls:
            return

        conversation.append(aggregate)  # giữ nguyên tin của model (kể cả chữ ký suy luận) khi gửi lại
        for call in calls:
            name, args = call.get("name", ""), call.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            result = _run_tool(by_name, name, args)
            if tool_log is not None:
                tool_log.append({"name": name, "args": args, "result": result})
            conversation.append(ToolMessage(content=result, tool_call_id=call.get("id") or str(uuid.uuid4()), name=name))
    logger.warning("Model gọi công cụ quá %d lượt; dừng", max_rounds)
