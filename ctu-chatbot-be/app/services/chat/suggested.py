"""Câu hỏi gợi ý khi mới mở chat, kèm câu trả lời đã kiểm chứng được lưu sẵn (cache).

Bấm vào một câu gợi ý thì trả lời ngay từ file `app/data/suggested.json`, KHÔNG gọi LLM, embedding hay công cụ nào:
nhanh, miễn phí và luôn đúng. File được sinh bởi `scripts/build_suggested_cache.py` (chạy bot thật và chỉ nhận câu trả
lời qua được bộ kiểm tra) rồi kiểm lại bằng test offline.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "suggested.json"
CHUNK_SIZE = 24  # chia câu trả lời thành các đoạn nhỏ khi stream để giao diện hiện dần như bình thường


@dataclass(frozen=True)
class SuggestedAnswer:
    id: str
    category: str
    question: str
    answer: str
    sources: list[dict] = field(default_factory=list)  # [{article, title}]


def normalize(text: str) -> str:
    """Chuẩn hóa để so khớp: không phân biệt hoa thường, dấu cách thừa, dấu câu cuối và dạng Unicode."""
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(" ?!.。")


@lru_cache(maxsize=1)
def load() -> tuple[SuggestedAnswer, ...]:
    if not DATA_FILE.exists():
        return ()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return tuple(
        SuggestedAnswer(
            id=item["id"],
            category=item["category"],
            question=item["question"],
            answer=item["answer"],
            sources=list(item.get("sources") or []),
        )
        for item in data.get("items", [])
    )


@lru_cache(maxsize=1)
def _index() -> dict[str, SuggestedAnswer]:
    return {normalize(item.question): item for item in load()}


def lookup(text: str) -> SuggestedAnswer | None:
    """Câu người dùng gửi có đúng là một câu gợi ý không (sau khi chuẩn hóa)?"""
    return _index().get(normalize(text))


def chunks(answer: str, size: int = CHUNK_SIZE) -> list[str]:
    return [answer[i : i + size] for i in range(0, len(answer), size)] or [""]
