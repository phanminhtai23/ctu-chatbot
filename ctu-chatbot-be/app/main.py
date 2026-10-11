import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.api.v1 import api_router
from app.core.config import settings
from app.services.chat.graph import build_chat_graph
from app.services.llm.gemini import GeminiClient
from app.services.rag.embeddings import GeminiEmbedder
from app.services.rag.store import Retriever, VectorStore, default_chroma_path, ensure_index

logger = logging.getLogger("app")


def build_retriever() -> Retriever | None:
    """Kho vector ChromaDB (nhúng, không cần server) chứa các Điều của quy định.

    Lỗi ở đây (thiếu key embedding, mất mạng...) không được làm app chết: chatbot vẫn chạy nhưng không có ngữ cảnh.
    """
    try:
        store = VectorStore(GeminiEmbedder.from_settings(), path=default_chroma_path())
        count = ensure_index(store)
        logger.info("RAG sẵn sàng: %d Điều trong ChromaDB", count)
        return Retriever(store)
    except Exception:  # noqa: BLE001
        logger.exception("Không dựng được RAG; chatbot chạy không có ngữ cảnh quy định")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Checkpointer Postgres của LangGraph: lưu lịch sử chat theo thread_id (= id cuộc trò chuyện).
    # Kết nối bắt buộc autocommit + dict_row + prepare_threshold=0 (theo yêu cầu của PostgresSaver).
    pool = ConnectionPool(
        conninfo=settings.database_url.replace("postgresql+psycopg2://", "postgresql://"),
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    pool.open(wait=True)
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()  # tạo bảng checkpoint nếu chưa có (chạy an toàn nhiều lần)

    app.state.chat_graph = build_chat_graph(GeminiClient.from_settings(), checkpointer, build_retriever())
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="CTU Chatbot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
