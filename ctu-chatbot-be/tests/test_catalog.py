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


def test_update_document_renames_and_describes_every_version(catalog):
    manager, _ = catalog
    job = manager.upload("Quy chế học vụ", "rule.pdf", make_pdf())
    route_id = next(n["id"] for n in route_catalog.load_config()["nodes"] if n.get("document_slug") == job["slug"])
    node = manager.update_document(route_id, "  QĐ 3266  ", "3266/QĐ-ĐHCT", "https://ctu.edu.vn/qd3266.pdf")
    assert node["label"] == "QĐ 3266"
    assert node["official_url"] == "https://ctu.edu.vn/qd3266.pdf" and node["decision_no"] == "3266/QĐ-ĐHCT"
    assert manager.get_job(job["slug"], job["id"])["title"] == "QĐ 3266"
    with pytest.raises(CatalogError, match="DOCUMENT_NAME_INVALID"):
        manager.update_document(route_id, "   ", "", "")
    for bad in ("javascript:alert(1)", "ctu.edu.vn/x", "https://a b.vn", "ftp://x.vn/f"):
        with pytest.raises(CatalogError, match="DOCUMENT_URL_INVALID"):
            manager.update_document(route_id, "QĐ 3266", "", bad)
    cleared = manager.update_document(route_id, "QĐ 3266", "", "")
    assert "official_url" not in cleared and "decision_no" not in cleared


def test_delete_document_removes_route_versions_and_files(catalog):
    manager, root = catalog
    job = manager.upload("Tài liệu thử", "x.pdf", make_pdf())
    route_id = next(n["id"] for n in route_catalog.load_config()["nodes"] if n.get("document_slug") == job["slug"])
    result = manager.delete_document(route_id)
    assert result["versions"] == 1 and route_id in result["deleted"]
    config = route_catalog.load_config()
    assert all(n["id"] != route_id for n in config["nodes"])
    assert all(e["to"] != route_id for e in config["edges"])
    assert not (root / "documents" / job["id"]).exists()


def test_built_in_regulation_cannot_be_deleted(catalog):
    manager, _ = catalog
    with pytest.raises(CatalogError, match="DOCUMENT_PROTECTED"):
        manager.delete_document("regulation")
    with pytest.raises(CatalogError, match="DOCUMENT_NOT_FOUND"):
        manager.delete_document("external")


def test_admin_api_updates_and_deletes_document(catalog, client, admin_headers):
    manager, _ = catalog
    client.app.state.document_catalog = manager
    job = client.post(
        "/api/v1/admin/documents/catalog/jobs?title=Tai%20lieu&filename=a.pdf",
        headers={**admin_headers, "Content-Type": "application/pdf"},
        content=make_pdf(),
    ).json()
    route_id = next(n["id"] for n in route_catalog.load_config()["nodes"] if n.get("document_slug") == job["slug"])
    url = f"/api/v1/admin/documents/catalog/documents/{route_id}"
    patched = client.patch(url, headers=admin_headers, json={"label": "Mới", "decision_no": "1/QĐ", "official_url": "https://ctu.edu.vn/a.pdf"})
    assert patched.status_code == 200 and patched.json()["label"] == "Mới"
    bad_url = client.patch(url, headers=admin_headers, json={"label": "Mới", "official_url": "javascript:alert(1)"})
    assert bad_url.status_code == 400
    assert client.delete(url, headers=admin_headers).status_code == 200
    assert client.delete(url, headers=admin_headers).status_code == 404
    assert client.delete("/api/v1/admin/documents/catalog/documents/regulation", headers=admin_headers).status_code == 409


def _sync_all(manager, job):
    manager.extract(job["slug"], job["id"])
    manager.clean(job["slug"], job["id"])
    return manager.sync_job(job["slug"], job["id"])["job"]


def test_each_new_upload_is_its_own_route_even_with_the_same_title(catalog):
    manager, _ = catalog
    first = manager.upload("Quy chế", "a.pdf", make_pdf())
    second = manager.upload("Quy chế", "b.pdf", make_pdf())
    assert first["slug"] != second["slug"]
    assert second["slug"].startswith("quy-che-")


def test_upload_with_route_id_adds_a_version_to_the_same_document(catalog):
    manager, _ = catalog
    first = manager.upload("Học phí", "v1.pdf", make_pdf())
    _sync_all(manager, first)
    second = manager.upload("bỏ qua", "v2.pdf", make_pdf(), route_id=first["slug"])
    assert second["slug"] == first["slug"] and second["title"] == "Học phí"
    assert second["id"] != first["id"]
    with pytest.raises(CatalogError, match="DOCUMENT_NOT_FOUND"):
        manager.upload("x", "v3.pdf", make_pdf(), route_id="khong-co")


def test_activate_version_switches_back_and_forth(catalog):
    manager, _ = catalog
    first = manager.upload("Học phí", "v1.pdf", make_pdf())
    _sync_all(manager, first)
    second = manager.upload("Học phí", "v2.pdf", make_pdf(), route_id=first["slug"])
    _sync_all(manager, second)
    node = lambda: next(n for n in route_catalog.load_config()["nodes"] if n["id"] == first["slug"])  # noqa: E731
    assert node()["version"] == second["id"]
    back = manager.activate_version(first["slug"], first["id"])
    assert back["version"] == first["id"] and node()["collection"].endswith(first["id"])
    assert node()["source"] == f"documents/{first['id']}/clean.md"
    manager.activate_version(first["slug"], second["id"])
    assert node()["version"] == second["id"]


def test_activate_requires_a_synced_version(catalog):
    manager, _ = catalog
    first = manager.upload("Học phí", "v1.pdf", make_pdf())
    _sync_all(manager, first)
    pending = manager.upload("Học phí", "v2.pdf", make_pdf(), route_id=first["slug"])
    with pytest.raises(CatalogError, match="ACTIVATE_NOT_ALLOWED"):
        manager.activate_version(first["slug"], pending["id"])
    with pytest.raises(CatalogError, match="DOCUMENT_VERSION_NOT_FOUND"):
        manager.activate_version("regulation", first["id"])  # version của tài liệu khác


def _with_builtin_current(root):
    current = root / "documents" / "qd3266" / "current"
    current.mkdir(parents=True)
    (current / "clean.md").write_text("### Điều 1. Phạm vi" + chr(10) + "Nội dung bản mặc định." + chr(10), encoding="utf-8")


def test_builtin_regulation_can_get_versions_and_switch_back(catalog):
    manager, root = catalog
    _with_builtin_current(root)
    assert [j["id"] for j in manager.list_jobs() if j["slug"] == "qd3266"] == ["current"]

    uploaded = manager.upload("bỏ qua", "old.pdf", make_pdf(), route_id="regulation")
    assert uploaded["slug"] == "qd3266" and uploaded["title"] == "Quy chế học vụ"
    _sync_all(manager, uploaded)
    nodes = {n["id"]: n for n in route_catalog.load_config()["nodes"]}
    assert nodes["regulation"]["version"] == uploaded["id"] and nodes["regulation"]["document_slug"] == "qd3266"
    assert [n for n in nodes if n.startswith("qd3266")] == []  # không sinh tuyến thứ hai: id `regulation` được giữ
    assert {j["id"] for j in manager.list_jobs() if j["slug"] == "qd3266"} == {"current", uploaded["id"]}

    back = manager.activate_version("regulation", "current")
    assert "document_slug" not in back and "version" not in back and back["collection"] == "qd3266"
    assert back["source"] == "documents/qd3266/current/clean.md"
    again = manager.activate_version("regulation", uploaded["id"])
    assert again["version"] == uploaded["id"] and again["document_slug"] == "qd3266"

    with pytest.raises(CatalogError, match="DOCUMENT_PROTECTED"):
        manager.delete_document("regulation")
    with pytest.raises(CatalogError, match="SYNC_NOT_ALLOWED"):
        manager.sync_job("qd3266", "current")
    with pytest.raises(CatalogError, match="EXTRACT_NOT_ALLOWED"):
        manager.extract("qd3266", "current")


def test_slugify_keeps_vietnamese_d():
    from app.services.ingest.catalog import _slugify

    assert _slugify("QĐ 4544 Quy định công tác học vụ") == "qd-4544-quy-dinh-cong-tac-hoc-vu"
    assert _slugify("Đại học Cần Thơ") == "dai-hoc-can-tho"


def test_source_schema_keeps_document_url():
    from app.schemas.conversation import SourceOut

    source = SourceOut(article=18, title="Cảnh báo học vụ", document_url="/api/v1/documents/catalog/qd/20261108081530-7d8a7d/source")
    assert source.model_dump()["document_url"].endswith("/source")
