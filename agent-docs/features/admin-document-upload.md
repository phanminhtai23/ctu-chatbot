# Feature: admin-document-upload

- **Status:** implemented
- **Scope:** FE, BE, Chroma, source-controlled `vector-docs/`
- **Env:** local source editing; production reads committed versions and has a manual Chroma sync action

## Current staged workflow

The admin page `/admin/documents` separates source review from vectorization and shows a persisted, detailed progress flow:

1. **Upload** writes a version to `vector-docs/documents/<timestamp-id>/<original-filename>` and adds a disabled draft node to `vector-docs/routes.json`.
2. **Extract** reports PDF rendering and OCR separately, including page progress, metrics, warnings, and a reviewable OCR preview.
3. **Clean** reports normalization and per-article chunking separately, with cleanup metrics and a reviewable Markdown preview.
4. **Sync version** reports embedding progress and collection details, then promotes the draft route node. Each document route uses its own collection.
5. Commit/push the version directory and `vector-docs/routes.json`. The Docker image includes all of `vector-docs/`.
6. After production deploy, an admin manually presses **Sync catalog vào vector DB**. This rebuilds/updates the committed document collections in persistent Chroma; production does not write to the source tree.

The route canvas shows the classifier, web search, built-in regulation, and document nodes. Selecting a node exposes its route prompt; each router-to-route edge can be disabled. Route prompts and edge changes are saved to `vector-docs/routes.json`, so make them locally and commit/push them. Pending document nodes are visible but cannot receive chat traffic until sync promotes them.

Answers routed to a versioned document cite the matching article and link directly to that version's source PDF; the built-in regulation keeps its page-layout reference viewer.

Production Compose sets `DOCUMENT_CATALOG_EDIT_ENABLED=false`, `DOCUMENT_CATALOG_SYNC_ENABLED=true`, `DOCUMENT_INGEST_ENABLED=false`, and `VECTOR_DOCS_DIR=/vector-docs`. This leaves source edits local while allowing manual indexing after deployment.

**API:** `GET /admin/documents/catalog`, `POST /admin/documents/catalog/jobs`, stage actions under `/admin/documents/catalog/jobs/{slug}/{id}/{extract|clean|sync}`, `POST /admin/documents/catalog/sync`, `GET/PUT /admin/documents/catalog/routes`, and public `GET /documents/catalog/{slug}/{version}/source` for cited PDFs.

**Tests:** `tests/test_catalog.py`, `tests/test_graph_routing.py`, `tests/test_scope.py`, and `tests/test_ingest.py`.

The committed QĐ 3266 source is organized under `vector-docs/documents/qd3266/current/`; previous regulations are kept under their own document folder. Admin uploads use a timestamp-named folder directly under `vector-docs/documents/`, and keep the original PDF filename. See `vector-docs/README.md` for the layout and file roles.

### UI layout (2026-10-27)

`/admin/documents` has two tabs: **Quy trình tài liệu** (default) and **Sơ đồ tuyến**. The workflow tab shows a four-stage summary (Upload, Extract, Clean, Sync) above a vertical timeline (`components/admin/DocumentPipeline.tsx`). Each stage lists its sub-steps and previews. The stage action button sits inside the stage waiting for the admin. Only Sync is tagged "Ảnh hưởng chatbot"; earlier stages only write draft files. Upload is file-first: choose a PDF, the name is pre-filled from the filename, then press **Lưu thành version mới**. The route graph is compact and its pending-draft count shows on the tab.

### Historical implementation — legacy automatic ingest

The previous upload flow ran an automatic ingest pipeline, tested retrieval, and activated a version in server-side storage. It remains available through the legacy endpoints and `app/services/ingest/manager.py`, but it is not the staged catalog flow documented above. Its `DOCUMENT_INGEST_ENABLED` flag is disabled in production. Do not use its old 8/9-step UI description or `ctu-chatbot-be/data/documents/` paths when documenting or operating the current catalog.
