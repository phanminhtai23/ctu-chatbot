"""Quy trình nạp tài liệu mới: PDF -> ảnh trang -> OCR -> chuẩn hóa -> chunk theo Điều -> embedding -> vị trí Điều
trên trang -> kiểm thử -> áp dụng.

Mỗi bước ghi lại trạng thái, tiến độ và kết quả (số liệu, danh sách dòng, đoạn xem trước) vào `Job`; giao diện admin
đọc đúng cấu trúc này để vẽ luồng. Bản mới được dựng trong một phiên bản riêng (thư mục + collection Chroma riêng) và CHỈ
được áp dụng khi mọi kiểm thử đạt, nên tài liệu cũ vẫn phục vụ chatbot nếu có bước nào hỏng.
"""

import hashlib
import json
import logging
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.ingest import layout as layout_mod
from app.services.ingest import pdf as pdf_mod
from app.services.ingest import storage
from app.services.ingest.normalize import normalize_ocr
from app.services.ingest.vision import Vision, VisionBlocked, VisionError
from app.services.rag.chunker import Chunk, split_into_articles
from app.services.rag.embeddings import Embedder
from app.services.rag.store import VectorStore

logger = logging.getLogger("app.ingest")

STEP_DEFS = [
    ("render", "Đọc PDF và tách thành ảnh từng trang"),
    ("ocr", "Nhận dạng chữ (OCR) bằng Gemini"),
    ("normalize", "Chuẩn hóa văn bản"),
    ("chunk", "Tách theo từng Điều"),
    ("diff", "So sánh thay đổi với tài liệu đang dùng"),
    ("embed", "Vector hóa (embedding) từng Điều"),
    ("layout", "Xác định vị trí từng Điều trên trang"),
    ("test", "Kiểm thử bản mới"),
    ("activate", "Áp dụng cho chatbot"),
]
EMBED_BATCH = 8
RETRIEVAL_TOP_K = 5
MIN_CHUNK_CHARS = 40
MIN_LAYOUT_COVERAGE = 0.5  # dưới mức này thì bản mới bị từ chối; dưới 100% chỉ cảnh báo

# Trạng thái bước: pending | running | done | warning | failed | skipped
# Trạng thái lần nạp: running | activated | rejected (kiểm thử chưa đạt) | failed (một bước bị lỗi)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Step:
    key: str
    title: str
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    summary: str = ""
    progress: dict | None = None  # {"done": 3, "total": 19, "unit": "trang"}
    metrics: list[dict] = field(default_factory=list)  # [{"label": "Số trang", "value": "21"}]
    rows: list[dict] = field(default_factory=list)  # [{"label": ..., "status": ok|warn|fail|info, "note": ...}]
    # Bước so sánh: [{article, title, kind: added|removed|changed|same, lines: [{op: '+'|'-', text}], more}]
    changes: list[dict] = field(default_factory=list)
    preview: str = ""
    error: str = ""

    def metric(self, label: str, value: object) -> None:
        self.metrics.append({"label": label, "value": str(value)})

    def row(self, label: str, status: str = "ok", note: str = "") -> None:
        self.rows.append({"label": label, "status": status, "note": note})


@dataclass
class Job:
    id: str
    filename: str
    size_bytes: int
    created_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    status: str = "running"
    activated: bool = False
    steps: list[Step] = field(default_factory=lambda: [Step(k, t) for k, t in STEP_DEFS])

    def step(self, key: str) -> Step:
        return next(s for s in self.steps if s.key == key)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        steps = [Step(**s) for s in data.get("steps", [])]
        return cls(**{**data, "steps": steps})


class StepFailed(Exception):
    """Bước không thể tiếp tục: dừng cả quy trình, giữ nguyên tài liệu đang dùng."""


@dataclass
class IngestContext:
    job: Job
    directory: Path
    vision: Vision
    embedder: Embedder
    chroma_path: Path
    save: Callable[[Job], None]
    on_activate: Callable[[dict], None] = lambda info: None
    sleep: Callable[[float], None] = time.sleep


class IngestPipeline:
    def __init__(self, ctx: IngestContext):
        self.ctx = ctx
        self.job = ctx.job
        self.state: dict = {}

    # ---- điều phối ----

    def run(self) -> Job:
        steps = [
            ("render", self._render),
            ("ocr", self._ocr),
            ("normalize", self._normalize),
            ("chunk", self._chunk),
            ("diff", self._diff),
            ("embed", self._embed),
            ("layout", self._layout),
            ("test", self._test),
            ("activate", self._activate),
        ]
        failed = False
        try:
            for key, fn in steps:
                if failed:
                    self.job.step(key).status = "skipped"
                    continue
                try:
                    self._run_step(key, fn)
                except StepFailed:
                    failed = True
            if failed:
                self.job.status = "failed"
            else:
                self.job.status = "activated" if self.job.activated else "rejected"
        except Exception:  # noqa: BLE001 - lỗi ngoài dự kiến của chính quy trình
            logger.exception("Quy trình nạp tài liệu lỗi ngoài dự kiến")
            self.job.status = "failed"
        finally:
            self.job.finished_at = now_iso()
            self.ctx.save(self.job)
        return self.job

    def _run_step(self, key: str, fn: Callable[[Step], None]) -> None:
        step = self.job.step(key)
        step.status, step.started_at = "running", now_iso()
        self.ctx.save(self.job)
        try:
            fn(step)
            if step.status == "running":
                step.status = "done"
        except StepFailed as exc:
            step.status, step.error = "failed", str(exc)
            raise
        except VisionError as exc:
            step.status, step.error = "failed", f"Gemini lỗi: {exc}"
            raise StepFailed(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("Bước %s lỗi:\n%s", key, traceback.format_exc())
            step.status, step.error = "failed", f"{type(exc).__name__}: {exc}"
            raise StepFailed(str(exc)) from exc
        finally:
            step.finished_at = now_iso()
            self.ctx.save(self.job)

    def _progress(self, step: Step, done: int, total: int, unit: str) -> None:
        step.progress = {"done": done, "total": total, "unit": unit}
        self.ctx.save(self.job)

    # ---- 1. render ----

    def _render(self, step: Step) -> None:
        source = self.ctx.directory / "source.pdf"
        count = pdf_mod.page_count(source)
        if count < 1:
            raise StepFailed("PDF không có trang nào")
        if count > settings.ingest_max_pages:
            raise StepFailed(f"PDF có {count} trang, vượt giới hạn {settings.ingest_max_pages} trang")
        pages_dir = self.ctx.directory / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        sizes: dict[int, tuple[int, int]] = {}
        for number in range(1, count + 1):
            data = pdf_mod.render_pages(source, [number], pdf_mod.VIEWER_DPI, pdf_mod.VIEWER_QUALITY)[number]
            (pages_dir / f"page-{number:02d}.jpg").write_bytes(data)
            sizes[number] = pdf_mod.jpeg_size(data)
            self._progress(step, number, count, "trang")
        self.state.update(page_count=count, page_sizes=sizes)
        step.metric("Số trang", count)
        step.metric("Dung lượng PDF", f"{self.job.size_bytes / 1024 / 1024:.1f} MB")
        width, height = sizes[1]
        step.metric("Ảnh mỗi trang", f"{width}×{height}px")
        step.summary = f"Đã tách {count} trang"

    # ---- 2. OCR ----

    def _ocr(self, step: Step) -> None:
        source = self.ctx.directory / "source.pdf"
        count = self.state["page_count"]
        group = max(1, settings.ingest_ocr_pages_per_call)
        texts: list[str] = []
        calls = split_calls = 0
        done = 0
        for first in range(1, count + 1, group):
            pages = list(range(first, min(first + group, count + 1)))
            images = pdf_mod.render_pages(source, pages, pdf_mod.OCR_DPI, pdf_mod.OCR_QUALITY)
            try:
                calls += 1
                text = self.ctx.vision.ocr([images[p] for p in pages], pages)
                texts.append(_ensure_page_marker(text, pages[0]))
            except VisionBlocked:
                # Gemini từ chối cả nhóm (thường vì chép nguyên văn nhiều trang): thử từng trang một.
                split_calls += 1
                step.row(f"Trang {pages[0]}–{pages[-1]}", "warn", "Gemini từ chối cả nhóm, đọc lại từng trang")
                for page in pages:
                    try:
                        calls += 1
                        texts.append(_ensure_page_marker(self.ctx.vision.ocr([images[page]], [page]), page))
                    except VisionBlocked:
                        texts.append(f"--- Trang {page} ---\n")
                        step.row(f"Trang {page}", "fail", "Gemini từ chối đọc trang này, để trống")
            done += len(pages)
            self._progress(step, done, count, "trang")
        raw = "\n".join(texts)
        (self.ctx.directory / "ocr.txt").write_text(raw, encoding="utf-8")
        self.state["raw_text"] = raw
        chars = len(raw)
        step.metric("Số ký tự", f"{chars:,}")
        step.metric("Số lần gọi Gemini", calls)
        step.preview = raw[:700]
        if chars < 200:
            raise StepFailed("Gần như không đọc được chữ nào từ PDF (file trắng hoặc ảnh quá mờ?)")
        if any(r["status"] == "fail" for r in step.rows):
            step.status = "warning"
        step.summary = f"Đã đọc {count} trang, {chars:,} ký tự" + (f" (có {split_calls} nhóm phải đọc lại từng trang)" if split_calls else "")

    # ---- 3. chuẩn hóa ----

    def _normalize(self, step: Step) -> None:
        result = normalize_ocr(self.state["raw_text"])
        if not result.articles:
            raise StepFailed("Không tìm thấy tiêu đề 'Điều N. ...' nào trong văn bản OCR")
        (self.ctx.directory / "clean.md").write_text(result.markdown, encoding="utf-8")
        self.state.update(markdown=result.markdown, first_page=result.first_page)
        step.metric("Chương", result.chapters)
        step.metric("Điều", len(result.articles))
        step.metric("Bắt đầu từ trang", result.first_page)
        step.metric("Dòng phần ban hành bỏ đi", result.removed_front_lines)
        step.metric("Câu nối lại ở chỗ ngắt trang", result.joined_page_breaks)
        step.metric("Đoạn OCR lặp đã bỏ", result.repeated_fragments)
        for text in result.removed_running_lines:
            step.row(text[:80], "info", "Dòng tiêu đề/chân trang lặp lại, đã bỏ")
        for warning in result.warnings:
            step.row(warning, "warn")
        step.preview = result.markdown[:900]
        step.summary = f"{result.chapters} chương, {len(result.articles)} Điều"
        if result.warnings:
            step.status = "warning"

    # ---- 4. chunk ----

    def _chunk(self, step: Step) -> None:
        try:
            chunks = split_into_articles(self.state["markdown"])
        except ValueError as exc:
            raise StepFailed(f"{exc}. Có thể OCR đọc nhầm số Điều hoặc lặp tiêu đề.") from exc
        numbers = [c.article for c in chunks]
        missing = sorted(set(range(min(numbers), max(numbers) + 1)) - set(numbers))
        if missing:
            raise StepFailed(
                "Số Điều không liên tục, thiếu: " + ", ".join(f"Điều {n}" for n in missing) + ". OCR có thể bỏ sót tiêu đề."
            )
        for chunk in chunks:
            body = len(chunk.text)
            step.row(chunk.heading, "ok" if body >= MIN_CHUNK_CHARS else "warn", f"{body:,} ký tự")
        short = [c.article for c in chunks if len(c.text) < MIN_CHUNK_CHARS]
        self.state["chunks"] = chunks
        step.metric("Số Điều", len(chunks))
        step.metric("Điều dài nhất", f"{max(len(c.text) for c in chunks):,} ký tự")
        step.metric("Điều ngắn nhất", f"{min(len(c.text) for c in chunks):,} ký tự")
        step.summary = f"{len(chunks)} Điều (Điều {min(numbers)}–{max(numbers)}), mỗi Điều một chunk"
        if short:
            step.status = "warning"

    # ---- 5. so sánh thay đổi ----

    def _diff(self, step: Step) -> None:
        chunks: list[Chunk] = self.state["chunks"]
        old = _load_active_chunks()
        if old is None:
            step.summary = "Không có tài liệu đang dùng để so sánh (đây là bản đầu tiên)"
            self.state["changed_articles"] = set()
            return
        new = {c.article: c for c in chunks}
        changes: list[dict] = []
        counts = {"added": 0, "removed": 0, "changed": 0, "same": 0}
        for number in sorted(set(new) | set(old)):
            if number not in old:
                kind, lines, more = "added", _preview_lines(new[number].text, "+"), 0
            elif number not in new:
                kind, lines, more = "removed", _preview_lines(old[number].text, "-"), 0
            elif _squash(new[number].text) == _squash(old[number].text):
                kind, lines, more = "same", [], 0
            else:
                kind = "changed"
                lines, more = _line_diff(old[number].text, new[number].text)
            counts[kind] += 1
            title = (new.get(number) or old[number]).title
            changes.append({"article": number, "title": title, "kind": kind, "lines": lines, "more": more})
        step.changes = changes
        for label, key in (("Điều mới", "added"), ("Điều bị bỏ", "removed"), ("Điều có nội dung khác", "changed"), ("Điều giữ nguyên", "same")):
            step.metric(label, counts[key])
        self.state["changed_articles"] = {c["article"] for c in changes if c["kind"] in ("removed", "changed")}
        step.summary = (
            f"Thêm {counts['added']}, bỏ {counts['removed']}, đổi nội dung {counts['changed']}, giữ nguyên {counts['same']} Điều"
        )
        stale = _suggested_articles() & self.state["changed_articles"]
        if stale:
            step.row(
                "Câu hỏi gợi ý có sẵn cần soát lại",
                "warn",
                "Các câu trả lời lưu sẵn dựa vào Điều " + ", ".join(str(n) for n in sorted(stale)) + " đã đổi",
            )
            step.status = "warning"

    # ---- 6. embedding ----

    def _embed(self, step: Step) -> None:
        chunks: list[Chunk] = self.state["chunks"]
        collection = storage.collection_name(self.job.id)
        store = VectorStore(self.ctx.embedder, path=self.ctx.chroma_path, collection=collection)
        existing = store.count()
        if existing:  # chạy lại cùng mã: dọn collection cũ
            store.delete_collection(collection)
            store = VectorStore(self.ctx.embedder, path=self.ctx.chroma_path, collection=collection)
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[start : start + EMBED_BATCH]
            vectors.extend(self.ctx.embedder.embed_documents([c.text for c in batch]))
            self._progress(step, len(vectors), len(chunks), "Điều")
        digest = hashlib.sha256(self.state["markdown"].encode("utf-8")).hexdigest()
        store.index_vectors(chunks, vectors, source_hash=digest)
        self.state.update(store=store, collection=collection, digest=digest)
        step.metric("Số vector", len(vectors))
        step.metric("Số chiều", len(vectors[0]) if vectors else 0)
        step.metric("Collection", collection)
        step.summary = f"Đã lưu {len(vectors)} vector vào ChromaDB (chưa áp dụng cho chatbot)"

    # ---- 7. vị trí Điều trên trang ----

    def _layout(self, step: Step) -> None:
        count, first = self.state["page_count"], self.state["first_page"]
        chunks: list[Chunk] = self.state["chunks"]
        titles = {c.article: c.title for c in chunks}
        pages_dir = self.ctx.directory / "pages"
        articles: dict[int, dict] = {}
        previous: int | None = None
        pages = list(range(first, count + 1))
        for done, page in enumerate(pages, 1):
            image = (pages_dir / f"page-{page:02d}.jpg").read_bytes()
            blocks = self.ctx.vision.locate(image, page, previous)
            previous = layout_mod.blocks_to_highlights(blocks, page, previous, articles)
            self._progress(step, done, len(pages), "trang")
        layout = layout_mod.build_layout(
            articles, titles, self.state["page_sizes"], document="QD3266", title=_document_title(self.state["markdown"])
        )
        storage.atomic_write_text(self.ctx.directory / "layout.json", json.dumps(layout, ensure_ascii=False, indent=1))
        missing = sorted(set(titles) - set(articles))
        self.state.update(layout_articles=set(articles), layout_missing=missing)
        for number in missing:
            step.row(f"Điều {number}. {titles[number]}", "warn", "Chưa xác định được vị trí trên trang")
        step.metric("Điều có vị trí", f"{len(articles)}/{len(titles)}")
        step.metric("Số trang đã xét", len(pages))
        step.summary = f"Đã định vị {len(articles)}/{len(titles)} Điều trên ảnh trang"
        if missing:
            step.status = "warning"

    # ---- 8. kiểm thử ----

    def _test(self, step: Step) -> None:
        chunks: list[Chunk] = self.state["chunks"]
        store: VectorStore = self.state["store"]
        failures: list[str] = []

        # a) Kho vector đủ và đúng chiều.
        stored = store.count()
        dims = store.vector_dimensions()
        ok_count = stored == len(chunks)
        step.row("Số vector trong kho khớp số Điều", "ok" if ok_count else "fail", f"{stored}/{len(chunks)}")
        if not ok_count:
            failures.append("Số vector trong kho không khớp số Điều")
        ok_dim = dims == {settings.embedding_dim}
        step.row("Số chiều vector", "ok" if ok_dim else "fail", f"{sorted(dims)} (cần {settings.embedding_dim})")
        if not ok_dim:
            failures.append("Số chiều vector không đúng cấu hình")

        # b) Mỗi Điều phải tự tìm lại được bằng chính tiêu đề của nó (kiểm tra embedding + truy xuất end-to-end).
        found = 0
        details: list[tuple[Chunk, int | None]] = []
        for done, chunk in enumerate(chunks, 1):
            hits = store.search(chunk.title, RETRIEVAL_TOP_K)
            rank = next((i for i, h in enumerate(hits, 1) if h.article == chunk.article), None)
            found += rank is not None
            details.append((chunk, rank))
            self._progress(step, done, len(chunks), "Điều")
        rate = found / len(chunks)
        passed_rate = rate >= settings.ingest_min_retrieval_pass
        step.row(
            f"Truy xuất: tìm lại được Điều bằng tiêu đề (top {RETRIEVAL_TOP_K})",
            "ok" if passed_rate else "fail",
            f"{found}/{len(chunks)} = {rate:.0%} (cần ≥ {settings.ingest_min_retrieval_pass:.0%})",
        )
        for chunk, rank in details:
            if rank is None:
                step.row(f"  {chunk.heading}", "warn", f"không nằm trong top {RETRIEVAL_TOP_K}")
        if not passed_rate:
            failures.append("Tỉ lệ truy xuất đúng Điều quá thấp")

        # c) Vị trí trên trang (để bấm tham chiếu mở được PDF).
        covered = len(self.state["layout_articles"] & {c.article for c in chunks})
        coverage = covered / len(chunks)
        layout_status = "ok" if coverage == 1 else ("warn" if coverage >= MIN_LAYOUT_COVERAGE else "fail")
        step.row("Vị trí Điều trên trang", layout_status, f"{covered}/{len(chunks)} Điều")
        if layout_status == "fail":
            failures.append("Quá nhiều Điều chưa xác định được vị trí trên trang")

        step.metric("Truy xuất đúng", f"{rate:.0%}")
        step.metric("Điều có vị trí", f"{covered}/{len(chunks)}")
        self.state["tests_passed"] = not failures
        if failures:
            step.status = "failed"
            step.error = "; ".join(failures)
            step.summary = "Chưa đạt: " + "; ".join(failures)
        else:
            step.status = "warning" if any(r["status"] == "warn" for r in step.rows) else "done"
            step.summary = f"Đạt: truy xuất đúng {rate:.0%}, {covered}/{len(chunks)} Điều có vị trí"

    # ---- 9. áp dụng ----

    def _activate(self, step: Step) -> None:
        if not self.state.get("tests_passed"):
            step.status = "skipped"
            step.summary = "Không áp dụng vì kiểm thử chưa đạt. Chatbot vẫn dùng tài liệu cũ."
            return
        info = {
            "version": self.job.id,
            "collection": self.state["collection"],
            "filename": self.job.filename,
            "activated_at": now_iso(),
            "articles": len(self.state["chunks"]),
            "pages": self.state["page_count"],
        }
        storage.write_active(info)
        self.ctx.on_activate(info)
        self.job.activated = True
        step.metric("Phiên bản", self.job.id)
        step.summary = "Chatbot đang dùng tài liệu mới (không cần khởi động lại)"


# ---- hàm phụ ----


def _ensure_page_marker(text: str, first_page: int) -> str:
    """Gemini đôi khi quên dòng '--- Trang N ---' ở đầu nhóm: thêm lại để bước chuẩn hóa biết số trang."""
    import re

    stripped = text.strip("\n")
    if not re.match(r"^\s*-{2,}\s*Trang\s+\d+", stripped, flags=re.IGNORECASE):
        stripped = f"--- Trang {first_page} ---\n{stripped}"
    return stripped + "\n"


def _document_title(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip().capitalize()
    return "Văn bản quy định"


def _squash(text: str) -> str:
    return " ".join(text.split())


_MAX_DIFF_LINES = 40
_MAX_LINE_CHARS = 400


def _preview_lines(text: str, op: str, limit: int = 6) -> list[dict]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return [{"op": op, "text": ln[:_MAX_LINE_CHARS]} for ln in lines[:limit]]


def _line_diff(old_text: str, new_text: str) -> tuple[list[dict], int]:
    """Các dòng bị xoá (-) và dòng thêm vào (+) giữa hai bản của một Điều. Trả về (dòng, số dòng bị cắt bớt)."""
    import difflib

    old = [" ".join(ln.split()) for ln in old_text.splitlines() if ln.strip()]
    new = [" ".join(ln.split()) for ln in new_text.splitlines() if ln.strip()]
    out: list[dict] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        out.extend({"op": "-", "text": ln[:_MAX_LINE_CHARS]} for ln in old[i1:i2])
        out.extend({"op": "+", "text": ln[:_MAX_LINE_CHARS]} for ln in new[j1:j2])
    return out[:_MAX_DIFF_LINES], max(0, len(out) - _MAX_DIFF_LINES)


def _load_active_chunks() -> dict[int, Chunk] | None:
    active = storage.read_active()
    try:
        if active:
            markdown = (storage.version_dir(active["version"]) / "clean.md").read_text(encoding="utf-8")
        else:
            from app.services.rag.store import default_source_path

            markdown = default_source_path().read_text(encoding="utf-8")
        return {c.article: c for c in split_into_articles(markdown)}
    except (OSError, ValueError):
        return None


def _suggested_articles() -> set[int]:
    from app.services.chat import suggested

    return {int(s["article"]) for item in suggested.load() for s in item.sources if isinstance(s.get("article"), int)}
