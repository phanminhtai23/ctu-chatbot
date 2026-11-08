"""Nhờ LLM viết lại prompt phân loại (router) khi có tài liệu mới.

Bản đề xuất KHÔNG được lưu: admin xem so sánh với bản đang dùng rồi mới đồng ý (apply), từ chối hoặc phản hồi để sinh lại.
"""

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.chat import route_catalog
from app.services.chat.scope import message_text

logger = logging.getLogger("app.ingest")

ROUTER_MAX = 8000
NODE_MAX = 4000

SYSTEM_PROMPT = """Bạn là kỹ sư prompt cho chatbot học vụ của Trường Đại học Cần Thơ (CTU).
Chatbot có một bước PHÂN LOẠI: mỗi câu hỏi của sinh viên được gửi cho một mô hình cùng với prompt sau, và mô hình chỉ trả về id của một tuyến dữ liệu:

<prompt_phan_loai>
{router_prompt}
Chọn DUY NHẤT một id trong các tuyến đang bật:
- <id>: <tên tuyến>. <prompt của tuyến>
...
Chỉ trả về chính xác một id, không giải thích.
</prompt_phan_loai>

Nhiệm vụ: quản trị viên vừa thêm / chỉnh một TÀI LIỆU mới. Hãy viết lại hai thứ:
1. "node_prompt": prompt của tuyến tài liệu mới (một đoạn ngắn, 1-3 câu). Nêu rõ tài liệu quy định về chủ đề nào, khi nào NÊN chọn tuyến này và khi nào KHÔNG (đặc biệt phân biệt với các tuyến tài liệu khác dễ nhầm).
2. "router_prompt": prompt chung ở đầu bước phân loại. Giữ nguyên ý và giọng văn của bản hiện tại; chỉ sửa khi tài liệu mới thật sự đòi hỏi (ví dụ thêm quy tắc ưu tiên khi hai tài liệu cùng chủ đề). Nếu không cần đổi thì trả về y nguyên bản hiện tại.

Quy tắc: viết tiếng Việt, ngắn gọn, không bịa nội dung ngoài mô tả quản trị viên cung cấp, không nhắc tên model hay hướng dẫn kỹ thuật, không đụng tới prompt của các tuyến khác. Không đưa id tuyến vào router_prompt.
Chỉ trả về MỘT đối tượng JSON, không kèm giải thích hay markdown, đúng dạng:
{"router_prompt": "...", "node_prompt": "...", "changes": ["ý thay đổi 1", "ý thay đổi 2"]}
"changes" liệt kê ngắn gọn (tối đa 5 ý) những gì đã đổi so với bản hiện tại và vì sao."""


class ProposalError(Exception):
    pass


def _parse(reply: str) -> dict:
    text = reply.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ProposalError("PROPOSAL_INVALID")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProposalError("PROPOSAL_INVALID") from exc
    router, node = data.get("router_prompt"), data.get("node_prompt")
    changes = data.get("changes", [])
    if (
        not isinstance(router, str)
        or not isinstance(node, str)
        or not router.strip()
        or not node.strip()
        or len(router.strip()) > ROUTER_MAX
        or len(node.strip()) > NODE_MAX
    ):
        raise ProposalError("PROPOSAL_INVALID")
    if not isinstance(changes, list):
        changes = []
    return {
        "router_prompt": router.strip(),
        "node_prompt": node.strip(),
        "changes": [str(item).strip()[:300] for item in changes if str(item).strip()][:5],
    }


def _describe(node: dict) -> str:
    extra = []
    if node.get("decision_no"):
        extra.append(f"số quyết định: {node['decision_no']}")
    if node.get("description"):
        extra.append(f"mô tả: {node['description']}")
    suffix = f" ({'; '.join(extra)})" if extra else ""
    return f"- {node['id']}: {node['label']}. {node['prompt']}{suffix}"


def propose(
    llm,
    config: dict,
    route_id: str,
    description: str,
    feedback: str = "",
    previous: dict | None = None,
) -> dict:
    """Trả về {current, proposal}. `previous` là bản đề xuất lần trước (khi admin phản hồi để sinh lại)."""
    node = next((n for n in config["nodes"] if n["id"] == route_id and n["kind"] == "document"), None)
    if node is None:
        raise ProposalError("DOCUMENT_NOT_FOUND")
    description = description.strip()
    if not description or len(description) > 2000 or len(feedback) > 1000:
        raise ProposalError("PROPOSAL_INPUT_INVALID")
    others = [n for n in config["nodes"] if n["id"] != route_id and n.get("status") != "pending"]
    parts = [
        f"PROMPT PHÂN LOẠI HIỆN TẠI (router_prompt):\n{config['router_prompt']}",
        "CÁC TUYẾN KHÁC ĐANG CÓ:\n" + "\n".join(_describe(n) for n in others),
        f"TUYẾN TÀI LIỆU CẦN VIẾT LẠI:\n- id: {node['id']}\n- tên: {node['label']}\n- số quyết định: {node.get('decision_no') or '(chưa có)'}\n"
        f"- node_prompt hiện tại: {node['prompt']}",
        f"MÔ TẢ TÀI LIỆU DO QUẢN TRỊ VIÊN NHẬP:\n{description}",
    ]
    if previous and feedback.strip():
        parts.append(
            "BẢN ĐỀ XUẤT LẦN TRƯỚC (quản trị viên chưa hài lòng):\n"
            + json.dumps(
                {"router_prompt": previous.get("router_prompt", ""), "node_prompt": previous.get("node_prompt", "")},
                ensure_ascii=False,
            )
        )
    if feedback.strip():
        parts.append(f"PHẢN HỒI CỦA QUẢN TRỊ VIÊN (hãy sửa theo đúng phản hồi này):\n{feedback.strip()}")
    system = SystemMessage(content=SYSTEM_PROMPT.replace("{router_prompt}", "<router_prompt>"))
    reply = "".join(message_text(chunk) for chunk in llm.stream([system, HumanMessage(content="\n\n".join(parts))]))
    proposal = _parse(reply)
    return {
        "current": {"router_prompt": config["router_prompt"], "node_prompt": node["prompt"]},
        "proposal": proposal,
    }


def apply(config: dict, route_id: str, router_prompt: str, node_prompt: str, description: str = "") -> dict:
    """Ghi bản đã duyệt vào cấu hình: router_prompt chung + prompt của tuyến (mọi version cùng tài liệu)."""
    node = next((n for n in config["nodes"] if n["id"] == route_id and n["kind"] == "document"), None)
    if node is None:
        raise ProposalError("DOCUMENT_NOT_FOUND")
    router_prompt, node_prompt, description = router_prompt.strip(), node_prompt.strip(), description.strip()
    if not router_prompt or len(router_prompt) > ROUTER_MAX or not node_prompt or len(node_prompt) > NODE_MAX:
        raise ProposalError("PROPOSAL_INVALID")
    slug = node.get("document_slug")
    targets = {n["id"] for n in config["nodes"] if (slug and n.get("document_slug") == slug) or n["id"] == route_id}
    nodes = []
    for item in config["nodes"]:
        if item["id"] in targets:
            item = {**item, "prompt": node_prompt}
            if description:
                item["description"] = description[:500]
        nodes.append(item)
    return route_catalog.save_config({**config, "router_prompt": router_prompt, "nodes": nodes})
