"""Điều phối các lần nạp tài liệu: mỗi lần chạy trong một thread nền, chỉ một lần tại một thời điểm,
trạng thái được ghi ra đĩa (job.json) nên xem lại được sau khi tải lại trang hoặc khởi động lại server.
"""

import json
import logging
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from app.core.config import settings
from app.services.ingest import storage
from app.services.ingest.pipeline import IngestContext, IngestPipeline, Job, now_iso
from app.services.ingest.vision import Vision
from app.services.rag.embeddings import Embedder
from app.services.rag.store import Retriever, default_chroma_path

logger = logging.getLogger("app.ingest")


class IngestBusy(Exception):
    """Đang có một lần nạp khác chạy."""


class JobManager:
    def __init__(
        self,
        retriever: Retriever | None,
        vision_factory: Callable[[], Vision],
        embedder_factory: Callable[[], Embedder],
        run_in_thread: bool = True,
    ):
        self._retriever = retriever
        self._vision_factory = vision_factory
        self._embedder_factory = embedder_factory
        self._run_in_thread = run_in_thread
        self._lock = threading.Lock()
        self._running: str | None = None
        self._thread: threading.Thread | None = None

    # ---- lưu / đọc trạng thái ----

    @staticmethod
    def _job_file(job_id: str):
        return storage.version_dir(job_id) / "job.json"

    def _save(self, job: Job) -> None:
        storage.atomic_write_text(self._job_file(job.id), json.dumps(job.to_dict(), ensure_ascii=False))

    def get(self, job_id: str) -> Job | None:
        try:
            data = json.loads(self._job_file(job_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        job = Job.from_dict(data)
        if job.status == "running" and job.id != self._running:
            # Server khởi động lại giữa chừng: tiến trình nền đã mất.
            job.status = "failed"
            for step in job.steps:
                if step.status == "running":
                    step.status, step.error = "failed", "Bị gián đoạn (server khởi động lại)"
                elif step.status == "pending":
                    step.status = "skipped"
        return job

    def list(self, limit: int = 10) -> list[Job]:
        root = storage.versions_root()
        if not root.exists():
            return []
        jobs = [j for d in root.iterdir() if d.is_dir() and (j := self.get(d.name)) is not None]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def active_info(self) -> dict | None:
        return storage.read_active()

    @property
    def running_job_id(self) -> str | None:
        return self._running

    # ---- bắt đầu một lần nạp ----

    def start(self, filename: str, data: bytes) -> Job:
        with self._lock:
            if self._running is not None:
                raise IngestBusy
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            job = Job(id=f"{stamp}-{uuid.uuid4().hex[:6]}", filename=filename, size_bytes=len(data))
            directory = storage.version_dir(job.id)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "source.pdf").write_bytes(data)
            self._save(job)
            self._running = job.id

        def target() -> None:
            try:
                ctx = IngestContext(
                    job=job,
                    directory=directory,
                    vision=self._vision_factory(),
                    embedder=self._embedder_factory(),
                    chroma_path=default_chroma_path(),
                    save=self._save,
                    on_activate=self._activate,
                )
                IngestPipeline(ctx).run()
            except Exception:  # noqa: BLE001 - dựng vision/embedder lỗi (thiếu key...)
                logger.exception("Không chạy được quy trình nạp tài liệu")
                job.status, job.finished_at = "failed", now_iso()
                first = job.steps[0]
                first.status, first.error = "failed", "Không khởi động được (thiếu API key Gemini?)"
                for step in job.steps[1:]:
                    step.status = "skipped"
                self._save(job)
            finally:
                with self._lock:
                    self._running = None

        if self._run_in_thread:
            self._thread = threading.Thread(target=target, name=f"ingest-{job.id}", daemon=True)
            self._thread.start()
        else:
            target()
        return job

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    # ---- áp dụng phiên bản mới cho chatbot đang chạy ----

    def _activate(self, info: dict) -> None:
        self._apply(info["collection"])
        self._cleanup(info)

    def _apply(self, collection: str) -> None:
        if self._retriever is not None:
            self._retriever.store.switch_collection(collection)
            self._retriever.reset()
        from app.api.v1 import documents

        documents.clear_layout_cache()

    # ---- chuyển qua lại giữa các phiên bản đã nạp ----

    def can_activate(self, job: Job) -> bool:
        """Phiên bản từng qua kiểm thử và còn đủ dữ liệu (vector, layout, ảnh trang) thì chuyển lại được."""
        if not job.activated or job.status == "running":
            return False
        directory = storage.version_dir(job.id)
        has_files = (directory / "layout.json").exists() and (directory / "pages").is_dir()
        if self._retriever is None:  # không có kho vector (test): chỉ kiểm tra tệp
            return has_files
        return has_files and storage.collection_name(job.id) in self._retriever.store.collection_names()

    def default_available(self) -> bool:
        """Còn bản mặc định kèm hệ thống (collection `qd3266` + dữ liệu trang) để quay về không."""
        if not (storage.LEGACY_DATA_DIR / "layout.json").exists():
            return False
        return self._retriever is None or storage.LEGACY_COLLECTION in self._retriever.store.collection_names()

    def switch_to(self, version: str) -> dict:
        """Áp dụng lại một phiên bản đã nạp. IngestBusy nếu đang có lần nạp chạy; LookupError nếu không chuyển được."""
        with self._lock:
            if self._running is not None:
                raise IngestBusy
            job = self.get(version)
            if job is None or not self.can_activate(job):
                raise LookupError(version)
            layout = json.loads((storage.version_dir(version) / "layout.json").read_text(encoding="utf-8"))
            info = {
                "version": version,
                "collection": storage.collection_name(version),
                "filename": job.filename,
                "activated_at": now_iso(),
                "articles": len(layout.get("articles", {})),
                "pages": int(layout.get("page_count", 0)),
            }
            storage.write_active(info)
            self._apply(info["collection"])
            return info

    def switch_to_default(self) -> None:
        """Quay về tài liệu mặc định kèm hệ thống (bỏ con trỏ `active.json`)."""
        with self._lock:
            if self._running is not None:
                raise IngestBusy
            if not self.default_available():
                raise LookupError("default")
            storage.clear_active()
            self._apply(storage.LEGACY_COLLECTION)

    def source_path(self, version: str):
        path = storage.version_dir(version) / "source.pdf"
        return path if path.exists() else None

    def _cleanup(self, info: dict) -> None:
        """Giữ tối đa `ingest_keep_versions` phiên bản gần nhất (để chuyển lại), xoá cũ hơn cùng collection của chúng."""
        try:
            kept = storage.prune_versions({info["version"]}, settings.ingest_keep_versions)
            if self._retriever is not None:
                store = self._retriever.store
                keep = {info["collection"], storage.LEGACY_COLLECTION}
                keep |= {storage.collection_name(d.name) for d in storage.versions_root().iterdir() if d.is_dir()}
                for name in store.collection_names():
                    if name.startswith("qd3266-") and name not in keep:
                        store.delete_collection(name)
            if kept:
                logger.info("Đã xoá phiên bản tài liệu cũ: %s", ", ".join(kept))
        except Exception:  # noqa: BLE001 - dọn dẹp hỏng không được làm hỏng việc áp dụng
            logger.warning("Dọn phiên bản cũ lỗi", exc_info=True)
