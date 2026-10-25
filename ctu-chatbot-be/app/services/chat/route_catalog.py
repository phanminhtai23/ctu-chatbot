"""Load and validate the source-controlled chat routing graph."""

import json
import os
import re
import tempfile
from pathlib import Path

from app.core.config import settings

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ROUTE_ID = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_COLLECTION = re.compile(r"^[a-zA-Z0-9_-]{1,63}$")
_KINDS = {"document", "web", "smalltalk", "offtopic"}

DEFAULT_CONFIG = {
    "version": 1,
    "router_prompt": "Phân loại câu hỏi của sinh viên CTU vào đúng tuyến dữ liệu. Chỉ chọn một tuyến phù hợp nhất.",
    "nodes": [
        {
            "id": "regulation",
            "label": "Quy chế học vụ",
            "kind": "document",
            "prompt": "Câu hỏi về quy chế đào tạo, tín chỉ, điểm, học bổng, đăng ký học phần, cảnh báo học tập, tốt nghiệp và các quy định học vụ.",
            "collection": "qd3266",
            "source": "documents/qd3266/current/clean.md",
        },
        {
            "id": "external",
            "label": "Tìm kiếm web",
            "kind": "web",
            "prompt": "Thông tin mới hoặc chi tiết về trường như học phí, lịch, ký túc xá, tuyển sinh, thủ tục, liên hệ và thông báo.",
        },
        {
            "id": "offtopic",
            "label": "Ngoài phạm vi",
            "kind": "offtopic",
            "prompt": "Chủ đề không liên quan đến Trường Đại học Cần Thơ hoặc việc học.",
        },
        {
            "id": "smalltalk",
            "label": "Chào hỏi",
            "kind": "smalltalk",
            "prompt": "Chào hỏi, cảm ơn hoặc hỏi chatbot là ai và có thể giúp gì.",
        },
    ],
    "edges": [
        {"from": "router", "to": "regulation", "enabled": True},
        {"from": "router", "to": "external", "enabled": True},
        {"from": "router", "to": "offtopic", "enabled": True},
        {"from": "router", "to": "smalltalk", "enabled": True},
    ],
}


def vector_docs_root() -> Path:
    configured = settings.vector_docs_dir.strip()
    path = Path(configured) if configured else _REPO_ROOT / "vector-docs"
    return path if path.is_absolute() else (_REPO_ROOT / path).resolve()


def routes_path() -> Path:
    return vector_docs_root() / "routes.json"


def validate_config(value: object) -> dict:
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Route config must be a version 1 object")
    router_prompt = value.get("router_prompt")
    nodes = value.get("nodes")
    edges = value.get("edges")
    if not isinstance(router_prompt, str) or not router_prompt.strip() or len(router_prompt) > 8000:
        raise ValueError("router_prompt must contain 1–8000 characters")
    if not isinstance(nodes, list) or not nodes or len(nodes) > 100:
        raise ValueError("nodes must contain between 1 and 100 routes")
    if not isinstance(edges, list) or len(edges) > 200:
        raise ValueError("edges must be a list of at most 200 entries")

    normalized_nodes = []
    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("Each route node must be an object")
        node_id = node.get("id")
        label = node.get("label")
        kind = node.get("kind")
        prompt = node.get("prompt")
        if not isinstance(node_id, str) or not _ROUTE_ID.fullmatch(node_id) or node_id in node_ids:
            raise ValueError(f"Invalid or duplicate route id: {node_id!r}")
        if not isinstance(label, str) or not label.strip() or len(label) > 100:
            raise ValueError(f"Route {node_id} needs a label of at most 100 characters")
        if kind not in _KINDS:
            raise ValueError(f"Route {node_id} has an unsupported kind")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            raise ValueError(f"Route {node_id} needs a prompt of at most 4000 characters")
        node_ids.add(node_id)
        normalized = {"id": node_id, "label": label.strip(), "kind": kind, "prompt": prompt.strip()}
        if kind == "document":
            collection = node.get("collection")
            source = node.get("source")
            if not isinstance(collection, str) or not _COLLECTION.fullmatch(collection):
                raise ValueError(f"Route {node_id} has an invalid Chroma collection")
            if not isinstance(source, str) or not source or Path(source).is_absolute() or ".." in Path(source).parts:
                raise ValueError(f"Route {node_id} has an invalid source path")
            normalized.update(collection=collection, source=Path(source).as_posix())
            if node.get("document_slug"):
                normalized["document_slug"] = node["document_slug"]
            if node.get("version"):
                normalized["version"] = node["version"]
            if node.get("status") is not None:
                if node["status"] not in {"pending", "synced"}:
                    raise ValueError(f"Route {node_id} has an invalid document status")
                normalized["status"] = node["status"]
        normalized_nodes.append(normalized)

    normalized_edges = []
    edge_keys: set[tuple[str, str]] = set()
    enabled_targets: set[str] = set()
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("from") != "router":
            raise ValueError("Edges must originate from the router node")
        target = edge.get("to")
        enabled = edge.get("enabled")
        key = ("router", target)
        if target not in node_ids or not isinstance(enabled, bool) or key in edge_keys:
            raise ValueError(f"Invalid or duplicate route edge: {edge!r}")
        edge_keys.add(key)
        if enabled:
            enabled_targets.add(target)
        normalized_edges.append({"from": "router", "to": target, "enabled": enabled})
    if not enabled_targets:
        raise ValueError("At least one route edge must remain enabled")
    if {target for _, target in edge_keys} != node_ids:
        raise ValueError("Every route node must have exactly one edge")
    return {
        "version": 1,
        "router_prompt": router_prompt.strip(),
        "nodes": normalized_nodes,
        "edges": normalized_edges,
    }


def load_config() -> dict:
    path = routes_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return validate_config(DEFAULT_CONFIG)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read route config {path}: {exc}") from exc
    return validate_config(raw)


def save_config(value: object) -> dict:
    config = validate_config(value)
    path = routes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return config


def enabled_nodes(config: dict) -> list[dict]:
    enabled = {edge["to"] for edge in config["edges"] if edge["from"] == "router" and edge["enabled"]}
    return [node for node in config["nodes"] if node["id"] in enabled and node.get("status") != "pending"]


def source_path(relative: str) -> Path:
    root = vector_docs_root().resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Route source escapes vector-docs")
    return path


def editable() -> bool:
    if not settings.document_catalog_edit_enabled:
        return False
    root = vector_docs_root()
    target = routes_path()
    return os.access(root if root.exists() else root.parent, os.W_OK) and (
        not target.exists() or os.access(target, os.W_OK)
    )
