"""Kho vector cho kiến thức bổ sung (hỏi-đáp do admin nhập): một collection riêng trong cùng thư mục ChromaDB.

Vector tạo từ CÂU HỎI (so khớp câu hỏi người dùng với câu hỏi đã nhập thì chính xác hơn so với nhúng cả câu trả lời);
câu trả lời nằm trong metadata để đưa thẳng vào prompt.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

import chromadb

from app.services.rag.embeddings import Embedder

COLLECTION = "knowledge-qa"


@dataclass(frozen=True)
class KbHit:
    id: str
    question: str
    answer: str
    score: float  # độ giống (cosine) giữa câu hỏi người dùng và câu hỏi đã nhập


class KnowledgeStore:
    def __init__(self, embedder: Embedder, path: Path | str | None = None, collection: str = COLLECTION):
        self._embedder = embedder
        if path is None:
            self._client = chromadb.EphemeralClient()
            collection = f"{collection}-{uuid.uuid4().hex[:8]}"  # EphemeralClient dùng chung trong một process
        else:
            self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})

    def count(self) -> int:
        return self._collection.count()

    def ids(self) -> set[str]:
        return set(self._collection.get()["ids"])

    def upsert(self, entries: list[tuple[str, str, str]]) -> None:
        """entries: [(id, câu hỏi, câu trả lời)]. Đã có thì ghi đè."""
        if not entries:
            return
        vectors = self._embedder.embed_documents([question for _id, question, _answer in entries])
        self._collection.upsert(
            ids=[entry_id for entry_id, _q, _a in entries],
            embeddings=vectors,
            documents=[question for _id, question, _a in entries],
            metadatas=[{"answer": answer} for _id, _q, answer in entries],
        )

    def delete(self, ids: list[str]) -> None:
        existing = [i for i in ids if i in self.ids()] if ids else []
        if existing:
            self._collection.delete(ids=existing)

    def clear(self) -> None:
        existing = self._collection.get()["ids"]
        if existing:
            self._collection.delete(ids=existing)

    def search(self, query: str, k: int, min_score: float = 0.0) -> list[KbHit]:
        total = self.count()
        if total == 0:
            return []
        result = self._collection.query(query_embeddings=[self._embedder.embed_query(query)], n_results=min(k, total))
        hits = []
        for entry_id, question, meta, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            score = round(1.0 - float(distance), 4)
            if score >= min_score:
                hits.append(KbHit(entry_id, question, str(meta.get("answer", "")), score))
        return hits
