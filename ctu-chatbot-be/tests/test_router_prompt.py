import json

import pytest
from langchain_core.messages import AIMessageChunk

from app.api.deps import get_llm
from app.core.config import settings
from app.main import app
from app.services.chat import route_catalog
from app.services.ingest import router_prompt
from app.services.ingest.catalog import DocumentCatalog
from tests.test_ingest import FakeEmbedder, FakeVision, make_pdf


class ScriptedLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def stream(self, messages):
        self.calls.append(messages)
        yield AIMessageChunk(content=self.reply)


GOOD = json.dumps(
    {"router_prompt": "Router mới.", "node_prompt": "Chọn khi hỏi về học phí.", "changes": ["Thêm học phí"]},
    ensure_ascii=False,
)


@pytest.fixture()
def catalog(tmp_path, monkeypatch):
    root = tmp_path / "vector-docs"
    root.mkdir()
    monkeypatch.setattr(settings, "vector_docs_dir", str(root))
    monkeypatch.setattr(settings, "chroma_path", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "document_catalog_edit_enabled", True)
    manager = DocumentCatalog(FakeVision, FakeEmbedder)
    job = manager.upload("Học phí", "hp.pdf", make_pdf())
    route_id = next(n["id"] for n in route_catalog.load_config()["nodes"] if n.get("document_slug") == job["slug"])
    return manager, route_id


def test_propose_sends_current_prompts_and_feedback(catalog):
    _, route_id = catalog
    llm = ScriptedLLM("```json\n" + GOOD + "\n```")
    config = route_catalog.load_config()
    result = router_prompt.propose(llm, config, route_id, "Quy định học phí 2026", "ngắn hơn nữa", {"router_prompt": "cũ", "node_prompt": "cũ"})
    assert result["proposal"]["node_prompt"] == "Chọn khi hỏi về học phí."
    assert result["proposal"]["changes"] == ["Thêm học phí"]
    assert result["current"]["router_prompt"] == config["router_prompt"]
    sent = llm.calls[0][1].content
    assert config["router_prompt"] in sent and "Quy định học phí 2026" in sent and "ngắn hơn nữa" in sent


def test_propose_rejects_garbled_reply_and_unknown_route(catalog):
    _, route_id = catalog
    config = route_catalog.load_config()
    with pytest.raises(router_prompt.ProposalError, match="PROPOSAL_INVALID"):
        router_prompt.propose(ScriptedLLM("xin lỗi tôi không biết"), config, route_id, "mô tả")
    with pytest.raises(router_prompt.ProposalError, match="DOCUMENT_NOT_FOUND"):
        router_prompt.propose(ScriptedLLM(GOOD), config, "external", "mô tả")
    with pytest.raises(router_prompt.ProposalError, match="PROPOSAL_INPUT_INVALID"):
        router_prompt.propose(ScriptedLLM(GOOD), config, route_id, "   ")


def test_apply_updates_router_and_node_prompt(catalog):
    _, route_id = catalog
    saved = router_prompt.apply(route_catalog.load_config(), route_id, "Router mới.", "Chọn khi hỏi học phí.", "Mô tả")
    node = next(n for n in saved["nodes"] if n["id"] == route_id)
    assert saved["router_prompt"] == "Router mới." and node["prompt"] == "Chọn khi hỏi học phí." and node["description"] == "Mô tả"
    assert route_catalog.load_config()["router_prompt"] == "Router mới."


def test_admin_api_propose_then_apply(catalog, client, admin_headers):
    _, route_id = catalog
    app.dependency_overrides[get_llm] = lambda: ScriptedLLM(GOOD)
    body = {"route_id": route_id, "description": "Quy định học phí"}
    proposed = client.post("/api/v1/admin/documents/catalog/router-prompt/proposals", headers=admin_headers, json=body)
    assert proposed.status_code == 200
    assert route_catalog.load_config()["router_prompt"] != "Router mới."  # đề xuất chưa được lưu
    draft = proposed.json()["proposal"]
    applied = client.post(
        "/api/v1/admin/documents/catalog/router-prompt/apply",
        headers=admin_headers,
        json={"route_id": route_id, "router_prompt": draft["router_prompt"], "node_prompt": draft["node_prompt"]},
    )
    assert applied.status_code == 200 and route_catalog.load_config()["router_prompt"] == "Router mới."
    bad = client.post("/api/v1/admin/documents/catalog/router-prompt/proposals", headers=admin_headers, json={**body, "route_id": "external"})
    assert bad.status_code == 404
    app.dependency_overrides.pop(get_llm, None)
