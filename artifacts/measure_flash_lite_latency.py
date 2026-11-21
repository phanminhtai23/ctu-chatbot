"""Small live latency probe. Run from the backend directory with its venv.

Uses one configured key, existing vectors and isolated in-memory checkpoints.
Never indexes documents. Stores timings, not credentials or conversation history.
"""
import json
import logging
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ctu-chatbot-be"))

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import settings
from app.services.chat.graph import build_chat_graph
from app.services.chat.service import stream_turn
from app.services.chat.text import message_text
from app.services.ingest import storage
from app.services.llm.gemini import GeminiClient, LLMUnavailable
from app.services.rag.embeddings import CachedQueryEmbedder, GeminiEmbedder
from app.services.rag.knowledge import KnowledgeStore
from app.services.rag.store import Retriever, VectorStore, default_chroma_path
from tests.live_gemini import _load_daily_count, _save_daily_count, MAX_CALLS_PER_DAY


class ProbeStopped(BaseException):
    pass


for name in ("app.llm", "app.rag", "google", "httpx", "httpcore", "chromadb"):
    logging.getLogger(name).setLevel(logging.CRITICAL)

stamp = datetime.now(ZoneInfo("Asia/Saigon"))
out = Path(__file__).with_name("flash-lite-latency-" + stamp.strftime("%Y%m%d-%H%M%S") + ".json")
report = {
    "started_at": stamp.isoformat(),
    "requested_model": "gemini-3.5-flash-lite",
    "configured_model": settings.llm_model,
    "scope": "local direct SDK and real chat graph; no HTTP, queue, production network or Postgres",
    "key_policy": "first configured key only; no key rotation",
    "max_llm_calls": 12,
    "runs": [],
}


def save():
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_error(exc):
    msg = str(exc)
    for key in [*settings.gemini_api_keys, settings.embedding_model_api_key]:
        if key:
            msg = msg.replace(key, "[REDACTED]")
    return {"type": type(exc).__name__, "message": msg[:500]}


class TimedLLM:
    supports_tools = True

    def __init__(self):
        self.inner = GeminiClient(settings.gemini_api_keys[:1], report["requested_model"], 60, 60)
        self.calls = []

    def stream(self, messages, tools=None):
        daily = _load_daily_count()
        if len(self.calls) >= report["max_llm_calls"] or daily >= MAX_CALLS_PER_DAY:
            raise ProbeStopped("Probe call budget reached")
        _save_daily_count(daily + 1)
        entry = {"tools_bound": bool(tools), "input_chars": sum(len(message_text(m)) for m in messages)}
        self.calls.append(entry)
        start = time.perf_counter()
        chars = 0
        try:
            for chunk in self.inner.stream(messages, tools=tools):
                text = message_text(chunk)
                if text and "ttft_s" not in entry:
                    entry["ttft_s"] = round(time.perf_counter() - start, 3)
                chars += len(text)
                if getattr(chunk, "usage_metadata", None):
                    # Stream chunks carry usage deltas; the final chunk may be zero.
                    usage = entry.setdefault("usage", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
                    for key in usage:
                        usage[key] += chunk.usage_metadata.get(key, 0)
                metadata = getattr(chunk, "response_metadata", {})
                for key in ("model_name", "model_version", "finish_reason"):
                    if key in metadata:
                        entry[key] = metadata[key]
                yield chunk
        except LLMUnavailable as exc:
            entry["error"] = safe_error(exc)
            raise ProbeStopped("Provider quota unavailable; stopping probe") from None
        except Exception as exc:
            entry["error"] = safe_error(exc)
            raise
        finally:
            entry["total_s"] = round(time.perf_counter() - start, 3)
            entry["output_chars"] = chars


class StageLog(logging.Handler):
    current = None

    def emit(self, record):
        if self.current is not None and record.msg.startswith("Thời gian lượt chat"):
            self.current["stage_log"] = record.getMessage()


def pause():
    # Outside measured intervals; does not inflate individual request latency.
    time.sleep(7)


def measure(label, factory, llm):
    run = {"label": label}
    report["runs"].append(run)
    stages.current = run
    offset = len(llm.calls)
    started = time.perf_counter()
    chars = 0
    try:
        for text in factory():
            if text:
                if "ttft_s" not in run:
                    run["ttft_s"] = round(time.perf_counter() - started, 3)
                chars += len(text)
        run["ok"] = chars > 0
    except BaseException as exc:
        run["error"] = safe_error(exc)
        run["ok"] = False
        raise
    finally:
        run["total_s"] = round(time.perf_counter() - started, 3)
        run["output_chars"] = chars
        run["llm_calls"] = llm.calls[offset:]
        stages.current = None
        save()
        print(json.dumps(run, ensure_ascii=False), flush=True)


stages = StageLog()
logging.getLogger("app.chat").addHandler(stages)
logging.getLogger("app.chat").setLevel(logging.INFO)
llm = TimedLLM()

try:
    if not settings.gemini_api_keys:
        raise ProbeStopped("No configured Gemini key")
    for i in range(3):
        if i:
            pause()
        measure(
            "direct_control_" + str(i + 1),
            lambda: (message_text(c) for c in llm.stream([HumanMessage(content="Chỉ trả lời đúng một từ: OK")])),
            llm,
        )

    # Read existing collections. Do not run ensure_index or embed_documents.
    path = default_chroma_path()
    import chromadb

    existing = chromadb.PersistentClient(path=str(path))
    names = {c.name if hasattr(c, "name") else str(c) for c in existing.list_collections()}
    active = storage.read_active()
    collection = active["collection"] if active else "qd3266"
    if collection not in names:
        raise ProbeStopped("Existing document collection not found; indexing intentionally skipped")
    embed_keys = list(dict.fromkeys(k for k in [settings.embedding_model_api_key, *settings.gemini_api_keys[:1]] if k))
    embedder = CachedQueryEmbedder(GeminiEmbedder(embed_keys, settings.embedding_model, settings.embedding_dim))
    store = VectorStore(embedder, path=path, collection=collection)
    if not store.count():
        raise ProbeStopped("Existing document collection is empty")
    kb = KnowledgeStore(embedder, path=path) if "knowledge-qa" in names else None
    report["rag_collection"] = collection
    report["rag_articles"] = store.count()
    graph = build_chat_graph(llm, InMemorySaver(), Retriever(store, knowledge=kb))
    cases = [
        ("graph_explicit_article", "Theo Điều 14, số tín chỉ đăng ký trong một học kỳ được quy định thế nào? Trả lời ngắn gọn."),
        ("graph_general_regulation", "Mình muốn bảo lưu kết quả học tập, cần đáp ứng điều kiện gì? Trả lời ngắn gọn."),
        ("graph_gpa", "ĐTBCTL của mình là 3,0 sau 80 tín chỉ trong chương trình 120 tín chỉ. Chỉ học các tín chỉ còn lại thì có đạt 3,6 không? Trả lời ngắn gọn."),
    ]
    for label, question in cases:
        pause()

        def tokens(question=question):
            for event in stream_turn(graph, uuid.uuid4(), question):
                if event["type"] == "token":
                    yield event["text"]

        measure(label, tokens, llm)
except BaseException as exc:
    report["stopped"] = safe_error(exc)
    print(json.dumps({"stopped": report["stopped"]}, ensure_ascii=False), flush=True)
finally:
    for prefix in ("direct_control", "graph"):
        runs = [r for r in report["runs"] if r["label"].startswith(prefix) and r.get("ok")]
        report[prefix + "_summary"] = {
            "successful_samples": len(runs),
            "median_ttft_s": round(statistics.median(r["ttft_s"] for r in runs), 3) if runs else None,
            "median_total_s": round(statistics.median(r["total_s"] for r in runs), 3) if runs else None,
        }
    report["llm_calls_total"] = len(llm.calls)
    report["finished_at"] = datetime.now(ZoneInfo("Asia/Saigon")).isoformat()
    save()
    print(json.dumps({"report": str(out), "summaries": {k: v for k, v in report.items() if k.endswith("summary")}, "llm_calls": len(llm.calls)}, ensure_ascii=False), flush=True)
