"""Quy trình admin nạp tài liệu mới: chuẩn hóa, từng bước, kiểm thử, kích hoạt an toàn và API."""

import hashlib
import io
import re

import pytest
from PIL import Image

from app.core.config import settings
from app.services.ingest import storage
from app.services.ingest.manager import JobManager
from app.services.ingest.normalize import normalize_ocr
from app.services.ingest.vision import VisionBlocked
from app.services.rag.chunker import split_into_articles
from app.services.rag.store import Retriever, VectorStore

DIM = 32

PAGE_1 = """--- Trang 1 ---
BỘ GIÁO DỤC VÀ ĐÀO TẠO
QUYẾT ĐỊNH
Ban hành Quy định công tác học vụ
Căn cứ Luật Giáo dục đại học."""
PAGE_2 = """--- Trang 2 ---
2
QUY ĐỊNH CÔNG TÁC HỌC VỤ
*(Ban hành kèm theo Quyết định số 1/QĐ)*
Chương I. NHỮNG VẤN ĐỀ CHUNG
**Điều 1. Phạm vi điều chỉnh**
1. Quy định này áp dụng cho sinh viên đại học chính quy.
Điều 2. Học phí và miễn giảm học phí
1. Học phí đóng theo học kỳ và tính theo tổng số tín chỉ đã đăng ký học"""
PAGE_3 = """--- Trang 3 ---
3
và được nộp đúng hạn tại phòng tài chính.
Chương II. TỔ CHỨC ĐÀO TẠO
Điều 3. Đăng ký học phần
1. Sinh viên đăng ký học phần theo kế hoạch học tập của khóa học.
Điều 4. Cảnh báo học tập
1. Sinh viên bị cảnh báo học tập khi điểm trung bình học kỳ quá thấp."""
RAW = "\n".join([PAGE_1, PAGE_2, PAGE_3])


# ---- chuẩn hóa ----


def test_normalize_drops_front_matter_page_numbers_and_builds_headings():
    result = normalize_ocr(RAW)
    assert result.articles == [1, 2, 3, 4]
    assert result.chapters == 2
    assert result.first_page == 2
    md = result.markdown
    assert "Căn cứ Luật" not in md and "BỘ GIÁO DỤC" not in md
    assert "### Điều 1. Phạm vi điều chỉnh" in md and "## Chương I. NHỮNG VẤN ĐỀ CHUNG" in md
    assert "# QUY ĐỊNH CÔNG TÁC HỌC VỤ" in md
    assert not re.search(r"^\d$", md, flags=re.MULTILINE)  # số trang đã bỏ
    assert [c.article for c in split_into_articles(md)] == [1, 2, 3, 4]


def test_normalize_joins_sentence_broken_across_pages():
    md = normalize_ocr(RAW).markdown
    assert "tổng số tín chỉ đã đăng ký học và được nộp đúng hạn" in md


def test_normalize_removes_repeated_page_headers():
    pages = []
    for n in range(1, 6):
        pages.append(f"--- Trang {n} ---\nTrường Đại học Cần Thơ - Quy định\n" + (f"Chương I. CHUNG\nĐiều {n}. Tiêu đề số {n}\nNội dung điều {n} đủ dài." if n else ""))
    result = normalize_ocr("\n".join(pages))
    assert "Trường Đại học Cần Thơ - Quy định" not in result.markdown
    assert result.removed_running_lines == ["Trường Đại học Cần Thơ - Quy định"]


def test_normalize_warns_when_no_structure():
    result = normalize_ocr("--- Trang 1 ---\nchỉ là một đoạn chữ bình thường")
    assert not result.articles and result.warnings


# ---- đồ giả ----


class FakeEmbedder:
    """Túi từ băm vào DIM chiều: câu càng chung nhiều từ càng giống nhau, đủ để test truy xuất."""

    def __init__(self, constant: bool = False):
        self.constant = constant

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * DIM
        if self.constant:
            return [1.0] + [0.0] * (DIM - 1)
        for word in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeVision:
    def __init__(self, raw: str = RAW, block_groups: bool = False, locate_articles: bool = True):
        self.pages = {int(m.group(1)): m.group(0) for m in re.finditer(r"--- Trang (\d+) ---\n(?:.*\n?)*?(?=--- Trang|\Z)", raw)}
        self.block_groups = block_groups
        self.locate_articles = locate_articles
        self.ocr_calls: list[list[int]] = []

    def ocr(self, images, page_numbers):
        self.ocr_calls.append(list(page_numbers))
        if self.block_groups and len(page_numbers) > 1:
            raise VisionBlocked("blocked")
        return "\n".join(self.pages[p] for p in page_numbers)

    def locate(self, image, page, previous_article):
        if not self.locate_articles:
            return []
        text = self.pages.get(page, "")
        numbers = [int(n) for n in re.findall(r"Điều (\d+)\.", text)]
        if not numbers and previous_article:
            numbers = [previous_article]
        return [{"article": n, "box_2d": [100 + 150 * i, 100, 200 + 150 * i, 900]} for i, n in enumerate(numbers)]


def make_pdf(pages: int = 3) -> bytes:
    images = [Image.new("RGB", (300, 400), "white") for _ in range(pages)]
    buffer = io.BytesIO()
    images[0].save(buffer, "PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _ingest_settings(monkeypatch):
    monkeypatch.setattr(settings, "embedding_dim", DIM)
    monkeypatch.setattr(settings, "ingest_ocr_pages_per_call", 2)
    monkeypatch.setattr(settings, "document_ingest_enabled", True)


def make_manager(vision=None, embedder=None, retriever=None) -> JobManager:
    embedder = embedder or FakeEmbedder()
    return JobManager(retriever, lambda: vision or FakeVision(), lambda: embedder, run_in_thread=False)


def make_retriever() -> Retriever:
    from app.services.rag.store import default_chroma_path

    store = VectorStore(FakeEmbedder(), path=default_chroma_path())
    return Retriever(store)


def steps(job) -> dict[str, str]:
    return {s.key: s.status for s in job.steps}


# ---- quy trình ----


def test_happy_path_runs_every_step_and_activates_the_new_version():
    retriever = make_retriever()
    manager = make_manager(retriever=retriever)
    job = manager.start("quy-dinh.pdf", make_pdf())

    assert job.status == "activated" and job.activated
    status = steps(job)
    assert status["render"] == "done" and status["ocr"] == "done" and status["normalize"] == "done"
    assert status["chunk"] == "done" and status["embed"] == "done" and status["layout"] == "done"
    assert status["test"] in ("done", "warning") and status["activate"] == "done"

    active = storage.read_active()
    assert active["version"] == job.id and active["articles"] == 4
    assert retriever.store.collection_name == active["collection"]
    hit = retriever.retrieve("Cảnh báo học tập là gì")[0]
    assert hit.article == 4
    directory = storage.version_dir(job.id)
    assert (directory / "clean.md").exists() and (directory / "layout.json").exists() and (directory / "pages" / "page-01.jpg").exists()
    assert job.step("ocr").progress == {"done": 3, "total": 3, "unit": "trang"}
    assert any("Điều 2" in r["label"] for r in job.step("chunk").rows)


def test_job_state_is_persisted_and_can_be_read_back():
    manager = make_manager()
    job = manager.start("a.pdf", make_pdf())
    again = manager.get(job.id)
    assert again.status == "activated" and [s.key for s in again.steps] == [s.key for s in job.steps]
    assert manager.list()[0].id == job.id


def test_new_version_is_served_by_the_documents_api(client):
    manager = make_manager(retriever=make_retriever())
    job = manager.start("a.pdf", make_pdf())
    layout = client.get("/api/v1/documents/qd3266/layout").json()
    assert layout["page_count"] == 3 and sorted(layout["articles"], key=int) == ["1", "2", "3", "4"]
    assert client.get("/api/v1/documents/qd3266/pages/2.jpg").headers["content-type"] == "image/jpeg"
    assert storage.read_active()["version"] == job.id


def test_blocked_ocr_group_falls_back_to_page_by_page():
    vision = FakeVision(block_groups=True)
    job = make_manager(vision=vision).start("a.pdf", make_pdf())
    assert job.status == "activated"
    assert [len(c) for c in vision.ocr_calls] == [2, 1, 1, 1]  # nhóm 2 trang bị chặn -> đọc lại từng trang, rồi trang lẻ
    assert any("từ chối cả nhóm" in r["note"] for r in job.step("ocr").rows)


def test_missing_article_stops_the_pipeline_and_keeps_the_old_document():
    raw = RAW.replace("Điều 3. Đăng ký học phần", "Đăng ký học phần (OCR làm mất số Điều)")
    retriever = make_retriever()
    before = retriever.store.collection_name
    job = make_manager(vision=FakeVision(raw), retriever=retriever).start("a.pdf", make_pdf())
    status = steps(job)
    assert job.status == "failed" and status["chunk"] == "failed"
    assert "Điều 3" in job.step("chunk").error
    assert status["embed"] == status["layout"] == status["test"] == status["activate"] == "skipped"
    assert storage.read_active() is None and retriever.store.collection_name == before


def test_failed_tests_reject_the_version_without_touching_the_active_document(monkeypatch):
    from app.services.ingest import pipeline

    monkeypatch.setattr(pipeline, "RETRIEVAL_TOP_K", 1)  # tài liệu thử chỉ 4 Điều: top-5 thì kiểu gì cũng "tìm thấy"
    retriever = make_retriever()
    before = retriever.store.collection_name
    job = make_manager(embedder=FakeEmbedder(constant=True), retriever=retriever).start("a.pdf", make_pdf())
    assert job.status == "rejected" and not job.activated
    assert job.step("test").status == "failed" and job.step("activate").status == "skipped"
    assert "truy xuất" in job.step("test").error.lower()
    assert storage.read_active() is None and retriever.store.collection_name == before


def test_missing_layout_rejects_the_version():
    job = make_manager(vision=FakeVision(locate_articles=False)).start("a.pdf", make_pdf())
    assert job.status == "rejected" and "vị trí" in job.step("test").error


def test_empty_ocr_fails_the_ocr_step():
    job = make_manager(vision=FakeVision("--- Trang 1 ---\nx\n--- Trang 2 ---\n\n--- Trang 3 ---\n")).start("a.pdf", make_pdf())
    assert job.status == "failed" and job.step("ocr").status == "failed"


def test_comparison_with_the_active_version_lists_changed_articles():
    manager = make_manager()
    manager.start("v1.pdf", make_pdf())
    changed = RAW.replace("quá thấp", "dưới 1,00")
    job = manager.start("v2.pdf", make_pdf())  # cùng nội dung -> không đổi
    notes = " ".join(r["note"] for r in job.step("test").rows)
    assert "nội dung đổi 0 Điều" in notes
    job = make_manager(vision=FakeVision(changed)).start("v3.pdf", make_pdf())
    notes = " ".join(r["note"] for r in job.step("test").rows)
    assert "nội dung đổi 1 Điều" in notes and "4" in notes


def test_interrupted_job_is_reported_as_failed():
    manager = make_manager()
    job = manager.start("a.pdf", make_pdf())
    data = job.to_dict()
    data["status"] = "running"
    data["steps"][-1]["status"] = "running"
    storage.atomic_write_text(storage.version_dir(job.id) / "job.json", __import__("json").dumps(data))
    again = manager.get(job.id)
    assert again.status == "failed" and again.steps[-1].error


def test_only_one_job_at_a_time():
    manager = make_manager()
    manager._running = "other"
    from app.services.ingest.manager import IngestBusy

    with pytest.raises(IngestBusy):
        manager.start("a.pdf", make_pdf())


# ---- API ----


@pytest.fixture()
def api(client, admin_headers):
    manager = make_manager(retriever=make_retriever())
    client.app.state.ingest_manager = manager
    return client, admin_headers, manager


def _post(client, headers, body: bytes, name="q.pdf"):
    return client.post(f"/api/v1/admin/documents?filename={name}", headers={**headers, "Content-Type": "application/pdf"}, content=body)


def test_upload_runs_the_pipeline_and_job_is_readable(api):
    client, headers, _ = api
    res = _post(client, headers, make_pdf())
    assert res.status_code == 202
    job_id = res.json()["id"]
    detail = client.get(f"/api/v1/admin/documents/jobs/{job_id}", headers=headers).json()
    assert detail["status"] == "activated" and [s["key"] for s in detail["steps"]][0] == "render"
    overview = client.get("/api/v1/admin/documents", headers=headers).json()
    assert overview["active"]["version"] == job_id and overview["jobs"][0]["id"] == job_id and overview["running_job_id"] is None


def test_upload_rejects_non_pdf_and_oversize(api, monkeypatch):
    client, headers, _ = api
    assert _post(client, headers, b"hello world").status_code == 400
    monkeypatch.setattr(settings, "ingest_max_pdf_mb", 0)
    assert _post(client, headers, make_pdf()).status_code == 413


def test_upload_while_another_job_is_running_is_a_conflict(api):
    client, headers, manager = api
    manager._running = "20260101000000-abcdef"
    res = _post(client, headers, make_pdf())
    assert res.status_code == 409 and res.json()["detail"] == "INGEST_BUSY"


def test_ingest_can_be_disabled(api, monkeypatch):
    client, headers, _ = api
    monkeypatch.setattr(settings, "document_ingest_enabled", False)
    assert _post(client, headers, make_pdf()).status_code == 403


def test_only_admins_can_use_the_endpoints(client, auth_headers):
    assert client.get("/api/v1/admin/documents", headers=auth_headers).status_code == 403
    assert _post(client, auth_headers, make_pdf()).status_code == 403
    assert client.get("/api/v1/admin/documents").status_code == 401


def test_job_id_must_be_well_formed(api):
    client, headers, _ = api
    assert client.get("/api/v1/admin/documents/jobs/..%2F..%2Fetc", headers=headers).status_code == 404
    assert client.get("/api/v1/admin/documents/jobs/20260101000000-abcdef", headers=headers).status_code == 404


# ---- lưu nhiều phiên bản, chuyển qua lại ----

RAW_V2 = RAW.replace("quá thấp", "dưới 1,00 (bản hai)")


def _two_versions(retriever):
    manager = make_manager(retriever=retriever)
    first = manager.start("v1.pdf", make_pdf())
    second = make_manager(vision=FakeVision(RAW_V2), retriever=retriever).start("v2.pdf", make_pdf())
    return manager, first, second


def test_every_version_keeps_its_own_files_and_collection():
    retriever = make_retriever()
    _, first, second = _two_versions(retriever)
    assert first.id != second.id and storage.collection_name(first.id) != storage.collection_name(second.id)
    for job in (first, second):
        directory = storage.version_dir(job.id)
        assert (directory / "source.pdf").exists() and (directory / "clean.md").exists() and (directory / "layout.json").exists()
    assert storage.collection_name(first.id) in retriever.store.collection_names()
    assert "bản hai" in (storage.version_dir(second.id) / "clean.md").read_text(encoding="utf-8")


def test_switch_back_and_forth_changes_what_the_chatbot_retrieves(client):
    retriever = make_retriever()
    manager, first, second = _two_versions(retriever)
    assert storage.read_active()["version"] == second.id
    assert "bản hai" in retriever.retrieve("Cảnh báo học tập")[0].text

    info = manager.switch_to(first.id)
    assert info["version"] == first.id and storage.read_active()["version"] == first.id
    assert retriever.store.collection_name == storage.collection_name(first.id)
    assert "bản hai" not in retriever.retrieve("Cảnh báo học tập")[0].text

    manager.switch_to(second.id)
    assert "bản hai" in retriever.retrieve("Cảnh báo học tập")[0].text
    assert client.get("/api/v1/documents/qd3266/layout").json()["page_count"] == 3


def test_cannot_switch_to_rejected_missing_or_while_running(monkeypatch):
    from app.services.ingest import pipeline
    from app.services.ingest.manager import IngestBusy

    retriever = make_retriever()
    manager, first, _ = _two_versions(retriever)
    monkeypatch.setattr(pipeline, "RETRIEVAL_TOP_K", 1)
    rejected = make_manager(embedder=FakeEmbedder(constant=True), retriever=retriever).start("bad.pdf", make_pdf())
    assert rejected.status == "rejected"
    with pytest.raises(LookupError):
        manager.switch_to(rejected.id)
    with pytest.raises(LookupError):
        manager.switch_to("20200101000000-aaaaaa")
    manager._running = "x"
    with pytest.raises(IngestBusy):
        manager.switch_to(first.id)


def test_prune_keeps_only_the_newest_versions_but_never_the_active_one(monkeypatch):
    monkeypatch.setattr(settings, "ingest_keep_versions", 2)
    retriever = make_retriever()
    manager = make_manager(retriever=retriever)
    jobs = [manager.start(f"v{i}.pdf", make_pdf()) for i in range(4)]
    remaining = {j.id for j in manager.list(limit=50)}
    assert remaining == {jobs[2].id, jobs[3].id}
    names = retriever.store.collection_names()
    assert storage.collection_name(jobs[0].id) not in names and storage.collection_name(jobs[3].id) in names


def test_api_lists_switchable_versions_and_switches(api):
    client, headers, manager = api
    first = _post(client, headers, make_pdf(), "a.pdf").json()["id"]
    second = _post(client, headers, make_pdf(), "b.pdf").json()["id"]
    jobs = {j["id"]: j for j in client.get("/api/v1/admin/documents", headers=headers).json()["jobs"]}
    assert jobs[second]["is_active"] and not jobs[second]["can_activate"]
    assert jobs[first]["can_activate"] and not jobs[first]["is_active"]

    res = client.post(f"/api/v1/admin/documents/versions/{first}/activate", headers=headers)
    assert res.status_code == 200 and res.json()["active"]["version"] == first
    assert client.get("/api/v1/admin/documents", headers=headers).json()["active"]["version"] == first

    assert client.post("/api/v1/admin/documents/versions/20200101000000-aaaaaa/activate", headers=headers).status_code == 404
    assert client.post("/api/v1/admin/documents/versions/bad..id/activate", headers=headers).status_code == 404


def test_api_can_return_to_the_built_in_document_and_download_the_pdf(api):
    client, headers, _ = api
    job_id = _post(client, headers, make_pdf(), "goc.pdf").json()["id"]
    pdf = client.get(f"/api/v1/admin/documents/jobs/{job_id}/source", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert "goc.pdf" in pdf.headers["content-disposition"]

    res = client.post("/api/v1/admin/documents/versions/default/activate", headers=headers)
    assert res.status_code == 200 and storage.read_active() is None
    assert client.get("/api/v1/documents/qd3266/layout").json()["page_count"] == 21  # bản kèm repo


def test_switching_requires_admin(client, auth_headers):
    assert client.post("/api/v1/admin/documents/versions/default/activate", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/admin/documents/jobs/20260101000000-abcdef/source", headers=auth_headers).status_code == 403
