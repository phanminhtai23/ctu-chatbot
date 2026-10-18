import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import chromadb

from app.core.config import settings
from app.services.rag.chunker import Chunk, split_into_articles
from app.services.rag.embeddings import Embedder

logger = logging.getLogger("app.rag")

COLLECTION = "qd3266"
_BACKEND_DIR = Path(__file__).resolve().parents[3]  # .../ctu-chatbot-be


@dataclass(frozen=True)
class Hit:
    article: int
    title: str
    chapter: str
    text: str
    score: float  # độ giống (cosine, càng cao càng giống); 1.0 với điều được nêu thẳng trong câu hỏi
    explicit: bool = False

    @property
    def heading(self) -> str:
        return f"Điều {self.article}. {self.title}"


def default_source_path() -> Path:
    if settings.rag_source_path:
        return Path(settings.rag_source_path)
    return _BACKEND_DIR.parent / "vector-docs" / "qd3266-clean.md"


def default_chroma_path() -> Path:
    path = Path(settings.chroma_path)
    return path if path.is_absolute() else _BACKEND_DIR / path


class VectorStore:
    """ChromaDB nhúng: dữ liệu nằm trong một thư mục, không cần chạy server.

    `path=None` dùng bộ nhớ trong (test). Embedding luôn do `embedder` tạo và truyền vào, không dùng
    embedding mặc định của Chroma (nó thiên về tiếng Anh).
    """

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

    @property
    def source_hash(self) -> str | None:
        return (self._collection.metadata or {}).get("source_hash")

    def index(self, chunks: list[Chunk], source_hash: str = "") -> None:
        """Xoá dữ liệu cũ rồi nạp lại toàn bộ (văn bản chỉ vài chục Điều nên làm lại từ đầu cho đơn giản)."""
        existing = self._collection.get()["ids"]
        if existing:
            self._collection.delete(ids=existing)
        if not chunks:
            return
        vectors = self._embedder.embed_documents([c.text for c in chunks])
        self._collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[{"article": c.article, "title": c.title, "chapter": c.chapter} for c in chunks],
        )
        if source_hash:
            # Chroma chỉ cho đổi metadata của collection, không cho đổi `hnsw:space` sau khi tạo.
            self._collection.modify(metadata={"source_hash": source_hash})

    def index_vectors(self, chunks: list[Chunk], vectors: list[list[float]], source_hash: str = "") -> None:
        """Như `index` nhưng vector đã được tạo sẵn (để nơi gọi tự chia lô và báo tiến độ). Không xoá dữ liệu cũ."""
        self._collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[{"article": c.article, "title": c.title, "chapter": c.chapter} for c in chunks],
        )
        if source_hash:
            self._collection.modify(metadata={"source_hash": source_hash})

    def vector_dimensions(self) -> set[int]:
        """Số chiều của mọi vector đang lưu (đúng ra chỉ có một giá trị)."""
        embeddings = self._collection.get(include=["embeddings"])["embeddings"]
        return {len(e) for e in embeddings} if embeddings is not None else set()

    def switch_collection(self, name: str) -> None:
        """Chuyển sang collection khác (khi admin kích hoạt phiên bản tài liệu mới); các truy vấn sau đó dùng bản mới."""
        self._collection = self._client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})

    @property
    def collection_name(self) -> str:
        return self._collection.name

    def collection_names(self) -> list[str]:
        return [c.name if hasattr(c, "name") else str(c) for c in self._client.list_collections()]

    def delete_collection(self, name: str) -> None:
        self._client.delete_collection(name)

    def search(self, query: str, k: int) -> list[Hit]:
        if self.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=[self._embedder.embed_query(query)],
            n_results=min(k, self.count()),
        )
        hits = []
        for text, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
            hits.append(Hit(int(meta["article"]), meta["title"], meta["chapter"], text, round(1.0 - float(distance), 4)))
        return hits

    def titles(self) -> dict[int, str]:
        """Số Điều -> tiêu đề, dùng cho tra cứu theo từ khoá trong tiêu đề."""
        metas = self._collection.get(include=["metadatas"])["metadatas"]
        return {int(m["article"]): m["title"] for m in metas}

    def get_article(self, article: int) -> Hit | None:
        got = self._collection.get(ids=[f"dieu-{article}"])
        if not got["ids"]:
            return None
        meta = got["metadatas"][0]
        return Hit(int(meta["article"]), meta["title"], meta["chapter"], got["documents"][0], 1.0, explicit=True)


_ARTICLE_MENTION = re.compile(r"điều\s+(\d{1,2})\b", re.IGNORECASE)
_TITLE_SPLIT = re.compile(r"[,.]| và ")
# Cụm quá phổ biến trong câu hỏi: khớp tiêu đề bằng những cụm này chỉ sinh nhiễu.
_GENERIC_PHRASES = {"học kỳ", "học phần", "tín chỉ", "sinh viên", "học tập", "kết quả", "chương trình"}
_MAX_TITLE_HITS = 2


def title_phrases(title: str) -> list[str]:
    """Các cụm từ (từ 2 từ trở lên, không quá phổ biến) trích từ tiêu đề một Điều."""
    phrases = []
    for part in _TITLE_SPLIT.split(title.lower()):
        part = part.strip()
        if len(part.split()) >= 2 and part not in _GENERIC_PHRASES:
            phrases.append(part)
    return phrases


class Retriever:
    """Lấy các Điều liên quan: Điều nêu thẳng trong câu hỏi + Điều giống nhất về ngữ nghĩa + Điều có tiêu đề
    trùng cụm từ trong câu hỏi (cứu những câu như "học phí bao nhiêu" mà embedding xếp Điều 10 quá thấp)."""

    def __init__(self, store: VectorStore, top_k: int | None = None):
        self._store = store
        self._top_k = top_k or settings.rag_top_k
        self._phrases: dict[int, list[str]] | None = None

    def reset(self) -> None:
        """Xoá bộ nhớ đệm tiêu đề (gọi sau khi kho vector chuyển sang phiên bản tài liệu khác)."""
        self._phrases = None

    @property
    def store(self) -> VectorStore:
        return self._store

    def _title_matches(self, question: str, exclude: set[int]) -> list[int]:
        if self._phrases is None:
            self._phrases = {n: title_phrases(t) for n, t in self._store.titles().items()}
        lowered = question.lower()
        found = [n for n, phrases in self._phrases.items() if n not in exclude and any(p in lowered for p in phrases)]
        return sorted(found)[:_MAX_TITLE_HITS]

    def retrieve(self, question: str) -> list[Hit]:
        hits: list[Hit] = []
        seen: set[int] = set()
        for match in _ARTICLE_MENTION.finditer(question):
            number = int(match.group(1))
            if number in seen:
                continue
            hit = self._store.get_article(number)
            if hit is not None:
                hits.append(hit)
                seen.add(number)
        explicit = len(hits)
        # Xin thêm `explicit` kết quả vì Điều đã nêu thẳng thường cũng nằm trong kết quả ngữ nghĩa và bị bỏ trùng.
        for hit in self._store.search(question, self._top_k + explicit):
            if hit.article not in seen and len(hits) < self._top_k + explicit:
                hits.append(hit)
                seen.add(hit.article)
        for number in self._title_matches(question, seen):
            hit = self._store.get_article(number)
            if hit is not None:
                hits.append(hit)
                seen.add(number)
        return hits


def ensure_index(store: VectorStore, source: Path | None = None) -> int:
    """Nạp văn bản vào Chroma nếu chưa có hoặc file nguồn đã đổi. Trả về số chunk trong kho."""
    source = source or default_source_path()
    markdown = source.read_text(encoding="utf-8")
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    if store.count() > 0 and store.source_hash == digest:
        return store.count()
    chunks = split_into_articles(markdown)
    logger.info("Đang vector hóa %d Điều từ %s", len(chunks), source.name)
    store.index(chunks, source_hash=digest)
    return store.count()
