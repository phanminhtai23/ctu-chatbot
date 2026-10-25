import os

import pytest

from app.core.config import settings
from app.services.chat import route_catalog
from app.services.ingest.catalog import CatalogError, DocumentCatalog
from app.services.rag.chunker import split_into_articles
from app.services.rag.store import Retriever, VectorStore
from tests.test_ingest import FakeEmbedder, FakeVision, make_pdf


@pytest.fixture()
def catalog(tmp_path, monkeypatch):
    root = tmp_path / "vector-docs"
    root.mkdir()
    monkeypatch.setattr(settings, "vector_docs_dir", str(root))
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "runtime-documents"))
    monkeypatch.setattr(settings, "chroma_path", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "document_catalog_edit_enabled", True)
    monkeypatch.setattr(settings, "document_catalog_sync_enabled", True)
    return DocumentCatalog(FakeVision, FakeEmbedder), root


def test_upload_extract_clean_and_sync_keep_each_source_version(catalog):
    manager, root = catalog
    original_filename = "QD 3266 - Quy chế.pdf"
    uploaded = manager.upload("Quy chế học vụ", original_filename, make_pdf())
    version = root / "documents" / uploaded["id"]
    assert uploaded["status"] == "uploaded"
    assert (version / original_filename).read_bytes() == make_pdf()
    assert uploaded["filename"] == original_filename
    assert [step["key"] for step in uploaded["steps"]] == [
        "upload",
        "render",
        "ocr",
        "normalize",
        "chunk",
        "embed",
        "sync",
    ]
    assert (version / "job.json").exists() and (version / "manifest.json").exists()
    assert manager.list_jobs()[0]["id"] == uploaded["id"]
    pending = next(
        node for node in route_catalog.load_config()["nodes"] if node.get("document_slug") == uploaded["slug"]
    )
    assert pending["status"] == "pending"
    assert pending not in route_catalog.enabled_nodes(route_catalog.load_config())

    extracted = manager.extract(uploaded["slug"], uploaded["id"])
    assert extracted["status"] == "extracted"
    assert (version / "ocr.txt").exists()
    assert "Điều 1" in extracted["ocr_preview"]
    assert next(step for step in extracted["steps"] if step["key"] == "render")["status"] == "done"
    assert next(step for step in extracted["steps"] if step["key"] == "ocr")["status"] == "done"

    cleaned = manager.clean(uploaded["slug"], uploaded["id"])
    assert cleaned["status"] == "cleaned"
    assert (version / "clean.md").exists()
    assert "### Điều 1." in cleaned["clean_preview"]
    assert next(step for step in cleaned["steps"] if step["key"] == "normalize")["status"] == "done"
    assert next(step for step in cleaned["steps"] if step["key"] == "chunk")["status"] == "done"

    synced = manager.sync_job(uploaded["slug"], uploaded["id"])
    node = next(n for n in route_catalog.load_config()["nodes"] if n.get("document_slug") == uploaded["slug"])
    store = VectorStore(FakeEmbedder(), path=settings.chroma_path, collection=node["collection"])
    assert synced["job"]["status"] == "synced"
    assert next(step for step in synced["job"]["steps"] if step["key"] == "embed")["status"] == "done"
    assert next(step for step in synced["job"]["steps"] if step["key"] == "sync")["status"] == "done"
    assert store.count() == 4
    assert node["source"] == f"documents/{uploaded['id']}/clean.md"
    assert any(edge["to"] == uploaded["slug"] and edge["enabled"] for edge in route_catalog.load_config()["edges"])
    assert manager.source_file(uploaded["slug"], uploaded["id"]) == version / original_filename


def test_stage_order_is_enforced(catalog):
    manager, _ = catalog
    uploaded = manager.upload("Tài liệu đào tạo", "training.pdf", make_pdf())
    with pytest.raises(CatalogError, match="CLEAN_NOT_ALLOWED"):
        manager.clean(uploaded["slug"], uploaded["id"])
    with pytest.raises(CatalogError, match="SYNC_NOT_ALLOWED"):
        manager.sync_job(uploaded["slug"], uploaded["id"])


def test_legacy_jobs_keep_stage_results_when_detail_steps_are_migrated(catalog):
    manager, _ = catalog
    legacy_job = {
        "status": "failed",
        "error": "normalization failed",
        "steps": [
            {"key": "upload", "status": "done"},
            {"key": "extract", "status": "done"},
            {"key": "clean", "status": "failed"},
            {"key": "sync", "status": "pending"},
        ],
    }

    manager._ensure_detailed_steps(legacy_job)

    steps = {step["key"]: step["status"] for step in legacy_job["steps"]}
    assert steps["upload"] == "done"
    assert steps["render"] == steps["ocr"] == "done"
    assert steps["normalize"] == steps["chunk"] == "failed"
    assert steps["embed"] == steps["sync"] == "pending"


def test_atomic_job_write_retries_temporary_file_lock(tmp_path, monkeypatch):
    path = tmp_path / "job.json"
    replace = os.replace
    attempts = 0

    def replace_after_transient_lock(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("temporary file lock")
        replace(source, destination)

    monkeypatch.setattr(os, "replace", replace_after_transient_lock)

    DocumentCatalog._atomic_text(path, '{"status":"running"}')

    assert attempts == 3
    assert path.read_text(encoding="utf-8") == '{"status":"running"}'


def test_sync_catalog_loads_committed_clean_text(catalog):
    manager, root = catalog
    regulation_source = root / "documents" / "qd3266" / "current" / "clean.md"
    regulation_source.parent.mkdir(parents=True)
    regulation_source.write_text(
        "# Quy chế\n\n### Điều 1. Quy định chung\nNội dung quy chế mặc định dùng làm dữ liệu kiểm thử.\n",
        encoding="utf-8",
    )
    source = root / "custom.md"
    source.write_text(
        "# Quy định\n\n### Điều 1. Phạm vi\nNội dung đủ dài để tạo một vector dữ liệu kiểm thử.\n",
        encoding="utf-8",
    )
    config = route_catalog.load_config()
    node = {
        "id": "custom-rule",
        "label": "Quy định thử",
        "kind": "document",
        "prompt": "Câu hỏi về nội dung tài liệu kiểm thử.",
        "collection": "doc-custom-rule-v1",
        "source": "custom.md",
    }
    config["nodes"].append(node)
    config["edges"].append({"from": "router", "to": node["id"], "enabled": True})
    route_catalog.save_config(config)

    result = manager.sync_catalog()
    assert result["count"] == 2
    assert next(item for item in result["documents"] if item["collection"] == node["collection"])["articles"] == 1
    assert VectorStore(FakeEmbedder(), path=settings.chroma_path, collection=node["collection"]).count() == 1


def test_route_config_rejects_disabling_every_edge(catalog):
    _, _ = catalog
    config = route_catalog.load_config()
    config["edges"] = [{**edge, "enabled": False} for edge in config["edges"]]
    with pytest.raises(ValueError, match="At least one route edge"):
        route_catalog.save_config(config)


def test_retriever_can_query_a_non_default_document_collection(catalog):
    manager, _ = catalog
    embedder = FakeEmbedder()
    primary = VectorStore(embedder)
    collection = "doc-calendar-test"
    document = primary.for_collection(collection)
    document.index(
        split_into_articles(
            "# Lịch học\n\n### Điều 1. Lịch thi\nLịch thi học kỳ được công bố trên cổng thông tin đào tạo."
        )
    )
    retriever = Retriever(primary)
    hits = retriever.retrieve("Lịch thi học kỳ", collection=collection)
    assert hits and "cổng thông tin đào tạo" in hits[0].text


def test_admin_catalog_api_uploads_and_exposes_routes(catalog, client, admin_headers):
    manager, _ = catalog
    client.app.state.document_catalog = manager
    pdf = make_pdf()
    response = client.post(
        "/api/v1/admin/documents/catalog/jobs?title=Quy%20che%20hoc%20vu&filename=rule.pdf",
        headers={**admin_headers, "Content-Type": "application/pdf"},
        content=pdf,
    )
    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "uploaded"

    detail = client.get(
        f"/api/v1/admin/documents/catalog/jobs/{job['slug']}/{job['id']}",
        headers=admin_headers,
    )
    assert detail.status_code == 200 and detail.json()["filename"] == "rule.pdf"
    source = client.get(f"/api/v1/documents/catalog/{job['slug']}/{job['id']}/source")
    assert source.status_code == 200 and source.content == pdf
    overview = client.get("/api/v1/admin/documents/catalog", headers=admin_headers)
    assert overview.status_code == 200 and overview.json()["editable"] is True


def test_catalog_upload_is_rejected_when_source_is_read_only(catalog, client, admin_headers, monkeypatch):
    manager, _ = catalog
    client.app.state.document_catalog = manager
    monkeypatch.setattr(settings, "document_catalog_edit_enabled", False)
    response = client.post(
        "/api/v1/admin/documents/catalog/jobs?title=Test&filename=test.pdf",
        headers={**admin_headers, "Content-Type": "application/pdf"},
        content=make_pdf(),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "CATALOG_READ_ONLY"
