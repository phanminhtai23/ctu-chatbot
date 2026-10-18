"""Kiến thức bổ sung do admin nhập: quy tắc dữ liệu và bước "embedding" đưa vào vector DB."""

import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import KnowledgeEntry
from app.services.rag.knowledge import KnowledgeStore

EMBED_GROUP = 16  # embedding theo nhóm, lưu trạng thái sau từng nhóm: lỗi giữa chừng thì các nhóm trước vẫn giữ


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question).strip().lower().rstrip(" ?!.")


def question_key(question: str) -> str:
    return hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


def content_hash(question: str, answer: str) -> str:
    return hashlib.sha256(f"{question}\n{answer}".encode("utf-8")).hexdigest()


def status_of(entry: KnowledgeEntry) -> str:
    """'embedded' (đã vào vector DB và nội dung chưa đổi) | 'pending' (chưa embedding, hoặc đã sửa sau lần embedding gần nhất)."""
    return "embedded" if entry.embedded_hash == content_hash(entry.question, entry.answer) else "pending"


def embed_entries(db: Session, store: KnowledgeStore, entries: list[KnowledgeEntry]) -> int:
    """Embedding các mục vào vector DB và ghi nhận trạng thái. Ném EmbeddingError nếu API embedding lỗi
    (các nhóm đã xong trước đó vẫn được ghi nhận)."""
    done = 0
    for start in range(0, len(entries), EMBED_GROUP):
        group = entries[start : start + EMBED_GROUP]
        store.upsert([(str(e.id), e.question, e.answer) for e in group])
        now = datetime.now(timezone.utc)
        for entry in group:
            entry.embedded_hash = content_hash(entry.question, entry.answer)
            entry.embedded_at = now
        db.commit()
        done += len(group)
    return done
