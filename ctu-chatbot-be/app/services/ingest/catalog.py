"""Versioned, source-controlled document workflow for admin uploads."""

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
import unicodedata
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.chat import route_catalog
from app.services.ingest import pdf as pdf_mod
from app.services.ingest.pipeline import IngestContext, IngestPipeline, Job, StepFailed, now_iso
from app.services.rag.chunker import split_into_articles
from app.services.rag.embeddings import Embedder
from app.services.rag.store import VectorStore, default_chroma_path
from app.services.ingest.vision import Vision

logger = logging.getLogger("app.ingest")
_JOB_ID = re.compile(r"^[0-9]{14}-[0-9a-f]{6}$")
_RESERVED = {"regulation", "external", "offtopic", "smalltalk"}
_EMBED_BATCH = 8
_DETAIL_STEPS = (
    ("upload", "Lưu PDF và thông tin version"),
    ("render", "Đọc PDF và tách thành ảnh từng trang"),
    ("ocr", "Nhận dạng chữ (OCR) bằng Gemini"),
    ("normalize", "Chuẩn hóa văn bản"),
    ("chunk", "Tách nội dung theo từng Điều"),
    ("embed", "Vector hóa từng Điều"),
    ("sync", "Lưu tuyến tài liệu vào catalog"),
)


class CatalogError(Exception):
    pass


def _slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")[:36].rstrip("-")
    if len(slug) < 2:
        raise CatalogError("DOCUMENT_NAME_INVALID")
    return f"{slug}-doc" if slug in _RESERVED else slug


class DocumentCatalog:
    def __init__(self, vision_factory, embedder_factory):
        self._vision_factory = vision_factory
        self._embedder_factory = embedder_factory

    @property
    def root(self) -> Path:
        return route_catalog.vector_docs_root()

    def _version_dir(self, slug: str, job_id: str) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", slug) or not _JOB_ID.fullmatch(job_id):
            raise CatalogError("DOCUMENT_VERSION_NOT_FOUND")
        timestamp_dir = self.root / "documents" / job_id
        legacy_dir = self.root / "documents" / slug / "versions" / job_id
        if (timestamp_dir / "job.json").is_file() or not (legacy_dir / "job.json").is_file():
            return timestamp_dir
        return legacy_dir

    def _read_job(self, slug: str, job_id: str) -> dict:
        path = self._version_dir(slug, job_id) / "job.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise CatalogError("DOCUMENT_VERSION_NOT_FOUND") from None
        if value.get("slug") != slug or value.get("id") != job_id:
            raise CatalogError("DOCUMENT_VERSION_NOT_FOUND")
        self._ensure_detailed_steps(value)
        return value

    def _save_job(self, job: dict) -> None:
        directory = self._version_dir(job["slug"], job["id"])
        directory.mkdir(parents=True, exist_ok=True)
        self._atomic_text(directory / "job.json", json.dumps(job, ensure_ascii=False, indent=2) + "\n")
        manifest = {
            "slug": job["slug"],
            "title": job["title"],
            "version": job["id"],
            "filename": job["filename"],
            "size_bytes": job["size_bytes"],
            "created_at": job["created_at"],
            "status": job["status"],
        }
        self._atomic_text(directory / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    @staticmethod
    def _atomic_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            for attempt in range(5):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    @staticmethod
    def _atomic_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    @staticmethod
    def _step(key: str, label: str, status: str) -> dict:
        return {"key": key, "title": label, "status": status}

    @classmethod
    def _ensure_detailed_steps(cls, job: dict) -> None:
        current = {step["key"]: step for step in job.get("steps", [])}
        if all(key in current for key, _ in _DETAIL_STEPS):
            return
        uploaded = current.get("upload", {}).get("status") == "done"
        old_status = job.get("status")
        extracted = old_status in {"extracted", "cleaned", "synced"} or current.get("extract", {}).get("status") == "done"
        cleaned = old_status in {"cleaned", "synced"} or current.get("clean", {}).get("status") == "done"
        synced = old_status == "synced" or current.get("sync", {}).get("status") == "done"
        failed_stage = next(
            (key for key in ("extract", "clean", "sync") if current.get(key, {}).get("status") == "failed"),
            None,
        )
        completed = {
            "render": extracted,
            "ocr": extracted,
            "normalize": cleaned,
            "chunk": cleaned,
            "embed": synced,
            "sync": synced,
        }
        failure_stage = {
            "extract": {"render", "ocr"},
            "clean": {"normalize", "chunk"},
            "sync": {"embed", "sync"},
        }
        steps = []
        for key, title in _DETAIL_STEPS:
            failed = key in failure_stage.get(failed_stage, set())
            done = uploaded if key == "upload" else completed.get(key, False)
            status = "failed" if failed else "done" if done else "pending"
            details = {"error": job.get("error", "")} if failed and job.get("error") else {}
            steps.append({**cls._step(key, title, status), **details})
        job["steps"] = steps

    @staticmethod
    def _update_step(job: dict, key: str, status: str, **details) -> None:
        step = next(item for item in job["steps"] if item["key"] == key)
        # Ghi mốc thời gian để giao diện hiện thời gian từng bước; chi tiết do pipeline truyền vào (render/ocr) được ưu tiên.
        if status == "pending":
            details.setdefault("started_at", None)
            details.setdefault("finished_at", None)
        elif status == "running" and step.get("status") != "running":
            details.setdefault("started_at", now_iso())
            details.setdefault("finished_at", None)
        elif status in {"done", "warning", "failed"}:
            finished = details.get("finished_at") or step.get("finished_at") or now_iso()
            details["finished_at"] = finished
            details.setdefault("started_at", step.get("started_at") or finished)
        step["status"] = status
        step.update(details)

    def upload(self, title: str, filename: str, data: bytes) -> dict:
        if not settings.document_catalog_edit_enabled or not route_catalog.editable():
            raise CatalogError("CATALOG_READ_ONLY")
        safe_title = title.strip()
        if not safe_title or len(safe_title) > 100:
            raise CatalogError("DOCUMENT_NAME_INVALID")
        slug = _slugify(safe_title)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        job_id = f"{stamp}-{uuid.uuid4().hex[:6]}"
        safe_filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if (
            not safe_filename
            or safe_filename in {".", ".."}
            or len(safe_filename) > 200
            or re.search(r'[<>:"|?*]', safe_filename)
            or safe_filename.endswith(".")
        ):
            raise CatalogError("DOCUMENT_NAME_INVALID")
        directory = self.root / "documents" / job_id
        directory.mkdir(parents=True, exist_ok=False)
        self._atomic_bytes(directory / safe_filename, data)
        job = {
            "id": job_id,
            "slug": slug,
            "title": safe_title,
            "filename": safe_filename,
            "size_bytes": len(data),
            "status": "uploaded",
            "created_at": now_iso(),
            "finished_at": None,
            "error": "",
            "ocr_preview": "",
            "clean_preview": "",
            "metrics": {},
            "steps": [
                {
                    **self._step(key, title, "done" if key == "upload" else "pending"),
                    **({"summary": f"{safe_filename} · {len(data):,} byte"} if key == "upload" else {}),
                }
                for key, title in _DETAIL_STEPS
            ],
        }
        self._save_job(job)
        config = route_catalog.load_config()
        existing = next(
            (node for node in config["nodes"] if node.get("document_slug") == slug and node.get("status") != "pending"),
            None,
        )
        draft_id = f"{slug[:24]}-v{job_id[-6:]}"
        draft = {
            "id": draft_id,
            "label": safe_title,
            "kind": "document",
            "prompt": existing["prompt"] if existing else f"Câu hỏi liên quan tới {safe_title}; chỉ chọn tuyến này khi nội dung thuộc tài liệu đó.",
            "collection": f"doc-{slug[:20]}-{job_id}",
            "source": f"documents/{job_id}/clean.md",
            "document_slug": slug,
            "version": job_id,
            "status": "pending",
        }
        nodes = [node for node in config["nodes"] if node["id"] != draft_id]
        nodes.append(draft)
        edges = [edge for edge in config["edges"] if edge["to"] != draft_id]
        edges.append({"from": "router", "to": draft_id, "enabled": False})
        route_catalog.save_config({**config, "nodes": nodes, "edges": edges})
        return job

    def get_job(self, slug: str, job_id: str) -> dict:
        return self._read_job(slug, job_id)

    def source_file(self, slug: str, job_id: str) -> Path:
        job = self._read_job(slug, job_id)
        path = self._version_dir(slug, job_id) / job["filename"]
        if not path.is_file():
            raise CatalogError("DOCUMENT_VERSION_NOT_FOUND")
        return path

    def list_jobs(self, limit: int = 30) -> list[dict]:
        jobs = []
        if not self.root.exists():
            return jobs
        job_files = list(self.root.glob("documents/*/job.json"))
        job_files.extend(self.root.glob("documents/*/versions/*/job.json"))
        for job_file in job_files:
            try:
                job = json.loads(job_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("Bỏ qua manifest tài liệu không hợp lệ: %s", job_file)
                continue
            if job.get("slug") and job.get("id"):
                jobs.append(job)
        jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return jobs[:limit]

    def extract(self, slug: str, job_id: str) -> dict:
        if not settings.document_catalog_edit_enabled or not route_catalog.editable():
            raise CatalogError("CATALOG_READ_ONLY")
        job = self._read_job(slug, job_id)
        if job["status"] not in {"uploaded", "extracted", "failed"}:
            raise CatalogError("EXTRACT_NOT_ALLOWED")

        source_dir = self._version_dir(slug, job_id)
        working = Path(settings.documents_dir)
        if not working.is_absolute():
            working = Path(__file__).resolve().parents[3] / working
        working = working / "catalog-staging" / job_id
        if working.exists():
            shutil.rmtree(working)
        working.mkdir(parents=True)
        shutil.copyfile(source_dir / job["filename"], working / "source.pdf")
        pipeline_job = Job(id=job_id, filename=job["filename"], size_bytes=job["size_bytes"])

        def save_pipeline_progress(_: Job) -> None:
            for detail in pipeline_job.steps:
                if detail.key not in {"render", "ocr"}:
                    continue
                state = {
                    "started_at": detail.started_at,
                    "finished_at": detail.finished_at,
                    "summary": detail.summary,
                    "progress": detail.progress,
                    "metrics": detail.metrics,
                    "rows": detail.rows,
                    "preview": detail.preview,
                    "error": detail.error,
                }
                self._update_step(job, detail.key, detail.status, **state)
            self._save_job(job)

        pipeline = IngestPipeline(
            IngestContext(
                job=pipeline_job,
                directory=working,
                vision=self._vision_factory(),
                embedder=self._embedder_factory(),
                chroma_path=default_chroma_path(),
                save=save_pipeline_progress,
            )
        )
        try:
            pipeline._run_step("render", pipeline._render)
            save_pipeline_progress(pipeline_job)
            pipeline._run_step("ocr", pipeline._ocr)
            save_pipeline_progress(pipeline_job)
            raw = (working / "ocr.txt").read_text(encoding="utf-8")
            self._atomic_text(source_dir / "ocr.txt", raw)
            job["status"] = "extracted"
            job["error"] = ""
            job["ocr_preview"] = raw[:4000]
            job["metrics"] = {
                "pages": pipeline_job.step("render").metrics[0]["value"],
                "ocr_characters": len(raw),
            }
            self._update_step(
                job,
                "ocr",
                pipeline_job.step("ocr").status,
                summary=f"Đã trích xuất {len(raw):,} ký tự",
            )
            self._update_step(job, "normalize", "pending", summary="", error="")
            self._update_step(job, "chunk", "pending", summary="", error="")
            self._update_step(job, "embed", "pending", summary="", error="")
            self._update_step(job, "sync", "pending", summary="", error="")
            self._save_job(job)
            return job
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
            save_pipeline_progress(pipeline_job)
            failed = next((step for step in job["steps"] if step["status"] == "failed"), None)
            if failed is None:
                self._update_step(job, "ocr", "failed", error=str(exc))
            self._save_job(job)
            raise CatalogError("EXTRACT_FAILED") from exc
        finally:
            shutil.rmtree(working, ignore_errors=True)

    def clean(self, slug: str, job_id: str) -> dict:
        if not settings.document_catalog_edit_enabled or not route_catalog.editable():
            raise CatalogError("CATALOG_READ_ONLY")
        job = self._read_job(slug, job_id)
        if job["status"] not in {"extracted", "cleaned", "failed"} or not (self._version_dir(slug, job_id) / "ocr.txt").exists():
            raise CatalogError("CLEAN_NOT_ALLOWED")
        directory = self._version_dir(slug, job_id)
        try:
            self._update_step(job, "normalize", "running", summary="", error="")
            self._save_job(job)
            raw = (directory / "ocr.txt").read_text(encoding="utf-8")
            from app.services.ingest.normalize import normalize_ocr

            result = normalize_ocr(raw)
            if not result.articles:
                raise ValueError("Không tìm thấy tiêu đề 'Điều N. ...' trong OCR")
            self._update_step(
                job,
                "normalize",
                "done",
                summary=f"{result.chapters} chương, {len(result.articles)} Điều",
                metrics=[
                    {"label": "Chương", "value": str(result.chapters)},
                    {"label": "Điều", "value": str(len(result.articles))},
                    {"label": "Dòng phần ban hành bỏ đi", "value": str(result.removed_front_lines)},
                    {"label": "Câu nối lại ở chỗ ngắt trang", "value": str(result.joined_page_breaks)},
                    {"label": "Đoạn OCR lặp đã bỏ", "value": str(result.repeated_fragments)},
                ],
                preview=result.markdown[:1000],
            )
            self._update_step(job, "chunk", "running", summary="", error="")
            self._save_job(job)
            chunks = split_into_articles(result.markdown)
            if not chunks:
                raise ValueError("Không tạo được chunk theo Điều từ văn bản đã chuẩn hóa")
            self._atomic_text(directory / "clean.md", result.markdown)
            self._update_step(
                job,
                "chunk",
                "done",
                summary=f"Đã tạo {len(chunks)} chunk theo Điều",
                metrics=[{"label": "Số chunk", "value": str(len(chunks))}],
            )
            job["status"] = "cleaned"
            job["error"] = ""
            job["clean_preview"] = result.markdown[:6000]
            job["metrics"] = {
                **job.get("metrics", {}),
                "chapters": result.chapters,
                "articles": len(chunks),
                "clean_characters": len(result.markdown),
            }
            self._save_job(job)
            return job
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
            running = next((step for step in job["steps"] if step["status"] == "running"), None)
            if running:
                self._update_step(job, running["key"], "failed", error=str(exc))
            self._save_job(job)
            raise CatalogError("CLEAN_FAILED") from exc

    def _sync_file(
        self,
        source: Path,
        collection: str,
        embedder: Embedder,
        progress: Callable[[int, int], None] | None = None,
    ) -> dict:
        markdown = source.read_text(encoding="utf-8")
        chunks = split_into_articles(markdown)
        if not chunks:
            raise CatalogError(f"NO_CHUNKS:{source}")
        digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        store = VectorStore(embedder, path=default_chroma_path(), collection=collection)
        if store.count() and store.source_hash == digest:
            return {"collection": collection, "articles": len(chunks), "unchanged": True}
        if store.count():
            store.delete_collection(collection)
            store = VectorStore(embedder, path=default_chroma_path(), collection=collection)
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), _EMBED_BATCH):
            vectors.extend(embedder.embed_documents([chunk.text for chunk in chunks[start : start + _EMBED_BATCH]]))
            if progress:
                progress(min(start + _EMBED_BATCH, len(chunks)), len(chunks))
        store.index_vectors(chunks, vectors, source_hash=digest)
        return {"collection": collection, "articles": len(chunks), "unchanged": False}

    def sync_job(self, slug: str, job_id: str) -> dict:
        if not settings.document_catalog_sync_enabled:
            raise CatalogError("CATALOG_SYNC_DISABLED")
        job = self._read_job(slug, job_id)
        if job["status"] not in {"cleaned", "synced"}:
            raise CatalogError("SYNC_NOT_ALLOWED")
        source = self._version_dir(slug, job_id) / "clean.md"
        collection = f"doc-{slug[:20]}-{job_id}"
        try:
            self._update_step(
                job,
                "embed",
                "running",
                summary="Đang tạo embedding",
                progress={"done": 0, "total": 0, "unit": "Điều"},
                error="",
            )
            self._save_job(job)

            def embedding_progress(done: int, total: int) -> None:
                self._update_step(
                    job,
                    "embed",
                    "running",
                    summary=f"Đã vector hóa {done}/{total} Điều",
                    progress={"done": done, "total": total, "unit": "Điều"},
                )
                self._save_job(job)

            result = self._sync_file(source, collection, self._embedder_factory(), embedding_progress)
            self._update_step(
                job,
                "embed",
                "done",
                summary=f"{result['articles']} Điều đã vector hóa",
                progress={"done": result["articles"], "total": result["articles"], "unit": "Điều"},
                metrics=[
                    {"label": "Collection", "value": collection},
                    {"label": "Số Điều", "value": str(result["articles"])},
                    {"label": "Không đổi nội dung", "value": "Có" if result["unchanged"] else "Không"},
                ],
            )
            self._update_step(job, "sync", "running", summary="", error="")
            self._save_job(job)
            config = route_catalog.load_config()
            nodes = list(config["nodes"])
            existing = next(
                (node for node in nodes if node.get("document_slug") == slug and node.get("status") != "pending"),
                None,
            )
            draft = next((node for node in nodes if node.get("document_slug") == slug and node.get("status") == "pending"), None)
            route_id = slug
            prompt = (
                existing["prompt"]
                if existing
                else draft["prompt"]
                if draft
                else f"Câu hỏi liên quan tới {job['title']}; chỉ chọn tuyến này khi nội dung thuộc tài liệu đó."
            )
            node = {
                "id": route_id,
                "label": job["title"],
                "kind": "document",
                "prompt": prompt,
                "collection": collection,
                "source": f"documents/{job_id}/clean.md",
                "document_slug": slug,
                "version": job_id,
                "status": "synced",
            }
            nodes = [candidate for candidate in nodes if candidate.get("document_slug") != slug and candidate["id"] != route_id]
            nodes.append(node)
            edges = list(config["edges"])
            edge = next((item for item in edges if item["to"] == route_id), None)
            edges = [item for item in edges if item["to"] != route_id and item["to"] not in {n["id"] for n in config["nodes"] if n.get("document_slug") == slug}]
            edges.append({"from": "router", "to": route_id, "enabled": edge["enabled"] if edge else True})
            route_catalog.save_config({**config, "nodes": nodes, "edges": edges})
            job["status"] = "synced"
            job["error"] = ""
            job["metrics"]["collection"] = collection
            self._update_step(job, "sync", "done", summary=f"Đã lưu tuyến {route_id} vào catalog")
            job["finished_at"] = now_iso()
            self._save_job(job)
            return {"job": job, "sync": result}
        except Exception as exc:
            job["error"] = str(exc)
            running = next((step for step in job["steps"] if step["status"] == "running"), None)
            if running:
                self._update_step(job, running["key"], "failed", error=str(exc))
            self._save_job(job)
            raise CatalogError("SYNC_FAILED") from exc

    def sync_catalog(self) -> dict:
        if not settings.document_catalog_sync_enabled:
            raise CatalogError("CATALOG_SYNC_DISABLED")
        config = route_catalog.load_config()
        documents = [
            node
            for node in config["nodes"]
            if node["kind"] == "document" and node.get("status") != "pending"
        ]
        embedder = self._embedder_factory()
        results = []
        for node in documents:
            source = route_catalog.source_path(node["source"])
            results.append(self._sync_file(source, node["collection"], embedder))
        return {"documents": results, "count": len(results)}
