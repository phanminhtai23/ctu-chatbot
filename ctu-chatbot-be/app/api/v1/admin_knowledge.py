import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models import KnowledgeEntry, User
from app.services import knowledge as kb
from app.services.rag.embeddings import EmbeddingError
from app.services.rag.knowledge import KnowledgeStore

router = APIRouter(prefix="/admin/knowledge", tags=["admin"], dependencies=[Depends(require_admin)])

MAX_QUESTION = 500
MAX_ANSWER = 4000


def get_knowledge_store_optional(request: Request) -> KnowledgeStore | None:
    retriever = getattr(request.app.state, "retriever", None)
    return getattr(retriever, "knowledge", None)


def require_knowledge_store(store: KnowledgeStore | None = Depends(get_knowledge_store_optional)) -> KnowledgeStore:
    if store is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="KNOWLEDGE_UNAVAILABLE")
    return store


class EntryIn(BaseModel):
    question: str
    answer: str

    @field_validator("question", "answer")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("question")
    @classmethod
    def _question(cls, v: str) -> str:
        if not v or len(v) > MAX_QUESTION:
            raise ValueError(f"question must be 1-{MAX_QUESTION} characters")
        return v

    @field_validator("answer")
    @classmethod
    def _answer(cls, v: str) -> str:
        if not v or len(v) > MAX_ANSWER:
            raise ValueError(f"answer must be 1-{MAX_ANSWER} characters")
        return v


class EntryPatch(BaseModel):
    question: str | None = None
    answer: str | None = None

    @field_validator("question", "answer")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class TestIn(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def _query(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > MAX_QUESTION:
            raise ValueError("query must be 1-500 characters")
        return v


def _item(entry: KnowledgeEntry) -> dict:
    return {
        "id": str(entry.id),
        "question": entry.question,
        "answer": entry.answer,
        "status": kb.status_of(entry),
        "embedded_at": entry.embedded_at.isoformat() if entry.embedded_at else None,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def _stats(db: Session, store: KnowledgeStore | None) -> dict:
    entries = db.scalars(select(KnowledgeEntry)).all()
    embedded = sum(1 for e in entries if kb.status_of(e) == "embedded")
    return {
        "total": len(entries),
        "embedded": embedded,
        "pending": len(entries) - embedded,
        # Số vector thật sự trong ChromaDB; lệch với "embedded" nghĩa là kho vector bị mất/đổi (cần "Nhúng lại tất cả").
        "vector_count": store.count() if store is not None else None,
    }


@router.get("")
def list_entries(
    q: str = Query("", max_length=100),
    state: Literal["all", "pending", "embedded"] = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    store: KnowledgeStore | None = Depends(get_knowledge_store_optional),
) -> dict:
    conditions = []
    if q.strip():
        like = f"%{q.strip().lower()}%"
        conditions.append(or_(func.lower(KnowledgeEntry.question).like(like), func.lower(KnowledgeEntry.answer).like(like)))
    rows = db.scalars(select(KnowledgeEntry).where(*conditions).order_by(KnowledgeEntry.created_at.desc())).all()
    if state != "all":
        rows = [e for e in rows if kb.status_of(e) == state]
    return {
        "total": len(rows),
        "items": [_item(e) for e in rows[offset : offset + limit]],
        "stats": _stats(db, store),
        "min_score": settings.kb_min_score,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_entry(body: EntryIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    entry = KnowledgeEntry(question=body.question, answer=body.answer, question_key=kb.question_key(body.question), created_by=admin.id)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="DUPLICATE_QUESTION") from None
    db.refresh(entry)
    return _item(entry)


@router.patch("/{entry_id}")
def update_entry(entry_id: uuid.UUID, body: EntryPatch, db: Session = Depends(get_db)) -> dict:
    entry = db.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Entry not found")
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(v is None or not v for v in changes.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="EMPTY_FIELD")
    question = changes.get("question", entry.question)
    answer = changes.get("answer", entry.answer)
    if len(question) > MAX_QUESTION or len(answer) > MAX_ANSWER:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="TOO_LONG")
    entry.question, entry.answer, entry.question_key = question, answer, kb.question_key(question)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="DUPLICATE_QUESTION") from None
    db.refresh(entry)
    return _item(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    store: KnowledgeStore | None = Depends(get_knowledge_store_optional),
) -> Response:
    entry = db.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Entry not found")
    if store is not None:
        store.delete([str(entry.id)])  # gỡ khỏi vector DB để chatbot không còn trả lời theo mục này
    db.delete(entry)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _embed(db: Session, store: KnowledgeStore, entries: list[KnowledgeEntry]) -> dict:
    try:
        done = kb.embed_entries(db, store, entries)
    except EmbeddingError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="EMBEDDING_UNAVAILABLE") from None
    return {"embedded": done, "stats": _stats(db, store)}


@router.post("/embed")
def embed_pending(
    force: bool = Query(False, description="true = embedding lại TẤT CẢ (ví dụ sau khi đổi model embedding hoặc mất kho vector)"),
    db: Session = Depends(get_db),
    store: KnowledgeStore = Depends(require_knowledge_store),
) -> dict:
    """Đưa các mục chưa embedding (hoặc đã sửa) vào vector DB."""
    entries = db.scalars(select(KnowledgeEntry).order_by(KnowledgeEntry.created_at)).all()
    if force:
        store.clear()
    else:
        entries = [e for e in entries if kb.status_of(e) == "pending"]
    return _embed(db, store, list(entries))


@router.post("/{entry_id}/embed")
def embed_one(entry_id: uuid.UUID, db: Session = Depends(get_db), store: KnowledgeStore = Depends(require_knowledge_store)) -> dict:
    entry = db.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return _embed(db, store, [entry])


@router.post("/test")
def test_query(body: TestIn, store: KnowledgeStore = Depends(require_knowledge_store)) -> dict:
    """Thử tra cứu như chatbot: mục nào khớp câu hỏi và độ giống bao nhiêu (`used` = đủ điểm để được đưa vào prompt)."""
    try:
        hits = store.search(body.query, 5)
    except EmbeddingError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="EMBEDDING_UNAVAILABLE") from None
    return {
        "min_score": settings.kb_min_score,
        "strong_score": settings.kb_strong_score,
        "hits": [
            {"id": h.id, "question": h.question, "answer": h.answer, "score": h.score, "used": h.score >= settings.kb_min_score}
            for h in hits
        ],
    }
