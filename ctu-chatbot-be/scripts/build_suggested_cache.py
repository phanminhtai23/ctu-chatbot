"""Sinh `app/data/suggested.json`: các câu hỏi gợi ý khi mới mở chat kèm câu trả lời ĐÃ KIỂM CHỨNG.

Với mỗi câu, chạy bot thật (RAG + bộ luật + công cụ máy tính) tối đa vài lần cho tới khi câu trả lời qua bộ kiểm tra
đáp án (`tests/answer_checks.py`) rồi ghi lại. Từ đó, bấm câu gợi ý trả lời ngay từ file này, không gọi LLM.

Chạy lại khi đổi câu hỏi/prompt:   python scripts/build_suggested_cache.py   (chỉ sinh các câu chưa có; thêm --force để sinh lại tất cả)
Mất vài phút (giãn cách giữa các lần gọi LLM để không vượt quota free).
"""

import dataclasses
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.messages import HumanMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.chat.graph import build_chat_graph  # noqa: E402
from app.services.chat.suggested import DATA_FILE  # noqa: E402
from app.services.llm.gemini import GeminiClient  # noqa: E402
from app.services.rag.embeddings import GeminiEmbedder  # noqa: E402
from app.services.rag.store import Retriever, VectorStore, default_chroma_path  # noqa: E402
from tests.answer_checks import case_problems, friendly_problems  # noqa: E402
from tests.rag_cases import ARTICLE_CASES, FORMULA_CASES, c  # noqa: E402
from tests.rag_cases_hard import CREDITS_HARD, GRADUATION_HARD, WARNING_HARD  # noqa: E402
from tests.rag_cases_scholarship import SCHOLARSHIP_CASES  # noqa: E402

MAX_ATTEMPTS = 4
MIN_LLM_INTERVAL = 5.0  # giây giữa hai lần gọi LLM (một câu hỏi có thể gọi nhiều lần: trích số liệu, công cụ, trả lời)


def pick(cases, case_id):
    return next(case for case in cases if case.id == case_id)


# (id, nhóm hiển thị, câu hỏi, kỳ vọng). Thứ tự ở đây = thứ tự hiện trên giao diện. Chọn các tình huống hay gặp và quan trọng:
# tốt nghiệp loại xuất sắc, học bổng, cảnh báo học tập, hạng tốt nghiệp.
SUGGESTIONS = [
    (
        "xuat-sac",
        "Điểm trung bình",
        "Chương trình 151 tín chỉ, mình đã học 100 tín chỉ với ĐTBCTL 3,2. Mình có thể tốt nghiệp loại xuất sắc không?",
        dataclasses.replace(
            pick(CREDITS_HARD, "k05"),
            question="Chương trình 151 tín chỉ, mình đã học 100 tín chỉ với ĐTBCTL 3,2. Mình có thể tốt nghiệp loại xuất sắc không?",
            must=((r"3[,.]47",), (r"cải thiện",), (r"điều kiện|điểm m\b",)),
            lead=r"không (thể|được|đạt)|không nhé|không bạn",
        ),
    ),
    (
        "hb-so-sanh",
        "Học bổng",
        "Hai bạn: A có ĐTBCHK 3,8 và ĐRL 89; B có ĐTBCHK 3,6 và ĐRL 90. Ai được xét học bổng trước?",
        dataclasses.replace(
            pick(SCHOLARSHIP_CASES, "h01"),
            question="Hai bạn: A có ĐTBCHK 3,8 và ĐRL 89; B có ĐTBCHK 3,6 và ĐRL 90. Ai được xét học bổng trước?",
            must=(
                (r"mức xuất sắc|loại xuất sắc",),
                (r"\btốt\b|mức giỏi|loại giỏi",),
                (r"\bb\b[^.\n]{0,160}(trước|đầu tiên|ưu tiên|xuất sắc)|(người thứ hai|bạn thứ hai)",),
            ),
            forbid=(r"\ba\b[^.\n]{0,40}(được xét trước|được ưu tiên|giành được học bổng)",),
        ),
    ),
    (
        "canh-bao",
        "Cảnh báo học tập",
        pick(WARNING_HARD, "w04").question,
        pick(WARNING_HARD, "w04"),
    ),
    (
        "tot-nghiep",
        "Tốt nghiệp",
        pick(GRADUATION_HARD, "t08").question,
        # 8/120 = 6,67%: bắt buộc nêu đúng con số này (lần sinh trước từng ghi nhầm 5,67% mà vẫn qua bộ kiểm tra cũ).
        dataclasses.replace(
            pick(GRADUATION_HARD, "t08"),
            must=((r"khá",), (r"6[,.]67",)),
            forbid=(r"5[,.]67",),
        ),
    ),
]


class ThrottledLLM:
    """Giãn cách các lần gọi LLM; vẫn cho đồ thị dùng công cụ nếu client gốc hỗ trợ."""

    def __init__(self, inner, interval: float):
        self._inner = inner
        self._interval = interval
        self._last = 0.0
        self.supports_tools = getattr(inner, "supports_tools", False)

    def stream(self, messages, tools=None):
        wait = self._last + self._interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        yield from (self._inner.stream(messages, tools=tools) if tools else self._inner.stream(messages))


def main() -> None:
    if not settings.gemini_api_keys:
        raise SystemExit("Chưa có GEMINI_API_KEY_* trong .env")
    store = VectorStore(GeminiEmbedder.from_settings(), path=default_chroma_path())
    graph = build_chat_graph(ThrottledLLM(GeminiClient.from_settings(), MIN_LLM_INTERVAL), InMemorySaver(), Retriever(store))

    # Mặc định giữ lại các câu ĐÃ có trong file (cùng id và cùng câu hỏi) để khỏi tốn LLM; `--force` = sinh lại tất cả.
    existing = {}
    if DATA_FILE.exists() and "--force" not in sys.argv:
        existing = {item["id"]: item for item in json.loads(DATA_FILE.read_text(encoding="utf-8")).get("items", [])}

    items = []
    for item_id, category, question, case in SUGGESTIONS:
        if item_id in existing and existing[item_id]["question"] == question:
            print(f"[{item_id}] giữ câu trả lời đã có", flush=True)
            items.append({**existing[item_id], "category": category})
            continue
        accepted = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            result = graph.invoke({"messages": [HumanMessage(content=question)]}, config)
            reply = result["messages"][-1]
            answer = str(reply.content).strip()
            problems = case_problems(case, answer) + friendly_problems(answer)
            print(f"[{item_id}] lần {attempt}: {'ĐẠT' if not problems else 'chưa đạt: ' + '; '.join(problems)}", flush=True)
            if not problems:
                accepted = {
                    "id": item_id,
                    "category": category,
                    "question": question,
                    "answer": answer,
                    "sources": list(reply.additional_kwargs.get("sources") or []),
                }
                break
        if accepted is None:
            raise SystemExit(f"Câu {item_id} không có câu trả lời nào qua bộ kiểm tra sau {MAX_ATTEMPTS} lần")
        items.append(accepted)

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": settings.llm_model,
        "items": items,
    }
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã ghi {len(items)} câu vào {DATA_FILE}")


if __name__ == "__main__":
    main()
