import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from langgraph.checkpoint.memory import InMemorySaver

from app import models  # noqa: F401
from app.api.deps import get_chat_graph
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db, get_sessionmaker
from app.main import app
from app.models import User
from app.services.chat.graph import build_chat_graph
from app.services.rate_limit import chat_limiter
from tests.fakes import FakeLLM


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch):
    # Test không được phụ thuộc .env của máy (Client ID thật, mở domain...): ép cấu hình cố định.
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "web_search_enabled", False)  # bộ phân loại phạm vi thêm một lần gọi LLM; test nào cần thì bật
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "allowed_email_domains", ["ctu.edu.vn", "edu.ctu.vn"])


@pytest.fixture(autouse=True)
def _reset_chat_limiter():
    # Bộ đếm giới hạn chat nằm trong bộ nhớ process: test này không được dùng hết lượt của test khác.
    chat_limiter.reset()
    yield
    chat_limiter.reset()


@pytest.fixture(autouse=True)
def _isolated_documents(monkeypatch, tmp_path):
    # Tài liệu admin đã nạp nằm trong documents_dir: test không được đọc/ghi dữ liệu thật của máy dev.
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "documents"))
    monkeypatch.setattr(settings, "chroma_path", str(tmp_path / "chroma"))


@pytest.fixture(autouse=True)
def _no_cached_delay(monkeypatch):
    from app.services.chat import service

    monkeypatch.setattr(service, "_sleep", lambda _s: None)


@pytest.fixture(autouse=True)
def _reset_turn_queue():
    # Hàng đợi lượt chat cũng nằm trong bộ nhớ process; tạo lại cho mỗi test.
    from app.services.chat import queue

    queue.turn_queue = None
    yield
    queue.turn_queue = None


@pytest.fixture()
def session_factory():
    # SQLite in-memory: test không phụ thuộc container Postgres.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture()
def fake_llm():
    return FakeLLM()


@pytest.fixture()
def checkpointer():
    # Bộ nhớ trong thay cho PostgresSaver: test không cần container Postgres.
    return InMemorySaver()


@pytest.fixture()
def chat_graph(fake_llm, checkpointer):
    return build_chat_graph(fake_llm, checkpointer)


@pytest.fixture()
def client(session_factory, chat_graph):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_chat_graph] = lambda: chat_graph
    app.dependency_overrides[get_sessionmaker] = lambda: session_factory  # response streaming tự mở session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login_headers(client, email):
    res = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture()
def auth_headers(client):
    return _login_headers(client, "b2100001@student.ctu.edu.vn")


@pytest.fixture()
def admin_headers(client, session_factory):
    email = "admin@student.ctu.edu.vn"
    headers = _login_headers(client, email)
    # Nâng role bằng cách sửa DB trực tiếp — đúng cách cấp quyền admin trong thực tế.
    with session_factory() as db:
        db.query(User).filter(User.email == email).update({"role": "admin"})
        db.commit()
    return headers
