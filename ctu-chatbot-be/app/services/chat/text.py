from langchain_core.messages import BaseMessage


def message_text(message: BaseMessage) -> str:
    """Gemini có thể trả content là chuỗi hoặc danh sách khối; gom phần chữ lại."""
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)
