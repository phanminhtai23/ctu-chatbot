"""Bounded live concurrency probe using the app's streaming Gemini client.

Run from ctu-chatbot-be with its venv. Reuses one configured key and one fixed
RAG-style prompt at every level. No retries, key rotation, embeddings or indexing.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import statistics
import sys
import threading
import time
import warnings
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ctu-chatbot-be"))

from langchain_core.messages import HumanMessage, SystemMessage
from app.core.config import settings
from app.services.chat.graph import build_system_prompt
from app.services.chat.text import message_text
from app.services.llm.gemini import GeminiClient, LLMUnavailable, classify_error
from app.services.rag.chunker import split_into_articles
from app.services.rag.store import default_source_path
from tests.live_gemini import _load_daily_count, _save_daily_count, MAX_CALLS_PER_DAY


def timestamp():
    return datetime.now(ZoneInfo("Asia/Saigon")).isoformat()


def safe_error(exc):
    message = str(exc)
    for key in [*settings.gemini_api_keys, settings.embedding_model_api_key]:
        if key:
            message = message.replace(key, "[REDACTED]")
    error = {"type": type(exc).__name__, "message": message[:400]}
    error["kind"] = "rate_limited" if isinstance(exc, LLMUnavailable) else classify_error(exc)
    if hasattr(exc, "retry_after"):
        error["retry_after"] = exc.retry_after
    return error


def summary(rows, wall):
    successful = [r for r in rows if r.get("ok")]
    result = {
        "attempted": len(rows), "successful": len(successful),
        "failed": len(rows) - len(successful), "batch_wall_s": round(wall, 3),
        "completed_per_second": round(len(successful) / wall, 3),
    }
    for metric in ("ttft_s", "total_s"):
        values = sorted(r[metric] for r in successful)
        if values:
            result[metric] = {
                "min": values[0], "median": round(statistics.median(values), 3),
                "max": values[-1], "mean": round(statistics.mean(values), 3),
            }
    # With 4 or 8 samples the maximum is clearer than a purported stable p95.
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore", message=".*fixed sampling defaults.*")
    if not settings.gemini_api_keys:
        raise SystemExit("No configured Gemini key")

    articles = {c.article: c for c in split_into_articles(default_source_path().read_text(encoding="utf-8"))}
    selected = [articles[n] for n in (14, 13, 15, 16, 17)]
    question = (
        "Tóm tắt quy định đăng ký số tín chỉ trong học kỳ chính theo Điều 14. "
        "Trả lời bằng tiếng Việt khoảng 80 từ, chỉ dựa vào tài liệu được cung cấp."
    )
    system = build_system_prompt(selected)
    messages = [SystemMessage(content=system), HumanMessage(content=question)]
    client = GeminiClient(settings.gemini_api_keys[:1], args.model, 60, 60)
    client._client(0, settings.gemini_api_keys[0])  # exclude lazy client creation; no inference call
    report = {
        "started_at": timestamp(), "model": args.model, "configured_model": settings.llm_model,
        "key_policy": "first configured key, shared client, no key rotation or retries",
        "scope": "local direct streaming LLM calls with the app system prompt and fixed document context",
        "excluded": ["HTTP endpoint", "app admission queue", "routing/extraction/tools", "query embeddings", "Postgres"],
        "measurement_notes": [
            "Three serial baseline calls, then one burst of four and one burst of eight.",
            "Identical prompt and one shared configured API key at all levels.",
            "Provider prompt caching and cold/warm connections may affect successive batches.",
            "This small sample measures burst latency, not sustained capacity or production HTTP throughput.",
        ],
        "prompt": {"articles": [c.article for c in selected], "question": question,
                   "input_chars": len(system) + len(question),
                   "sha256": hashlib.sha256((system + question).encode("utf-8")).hexdigest()},
        "max_attempts": 15, "batches": [],
    }
    output = Path(__file__).with_name("flash-lite-parallel-" + datetime.now(ZoneInfo("Asia/Saigon")).strftime("%Y%m%d-%H%M%S") + ".json")

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def request(index, barrier, wave_start):
        if barrier:
            barrier.wait(timeout=20)
        started = time.perf_counter()
        row = {"request": index, "start_offset_s": round(started - wave_start, 4)}
        chars = 0
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        try:
            for chunk in client.stream(messages):
                text = message_text(chunk)
                if text and "ttft_s" not in row:
                    row["ttft_s"] = round(time.perf_counter() - started, 3)
                chars += len(text)
                delta = getattr(chunk, "usage_metadata", None) or {}
                for name in usage:
                    usage[name] += delta.get(name, 0)
                metadata = getattr(chunk, "response_metadata", {}) or {}
                if "model_name" in metadata:
                    row["returned_model"] = metadata["model_name"]
            row["ok"] = chars > 0
            if not chars:
                row["error"] = {"kind": "empty_response"}
        except Exception as exc:
            row["ok"] = False
            row["error"] = safe_error(exc)
        finally:
            row["total_s"] = round(time.perf_counter() - started, 3)
            row["output_chars"] = chars
            if usage["total_tokens"]:
                row["usage"] = usage
        return row

    print(json.dumps({"event": "start", "model": args.model, "input_chars": report["prompt"]["input_chars"], "levels": [1, 4, 8]}, ensure_ascii=False), flush=True)
    for concurrency, count in ((1, 3), (4, 4), (8, 8)):
        daily = _load_daily_count()
        if daily + count > MAX_CALLS_PER_DAY:
            report["stopped"] = "Local daily test budget reached"
            break
        # Reserve in the coordinator; the old daily counter is not thread-safe.
        _save_daily_count(daily + count)
        batch = {"concurrency": concurrency, "started_at": timestamp(), "requests": []}
        report["batches"].append(batch)
        save()
        wall_start = time.perf_counter()
        if concurrency == 1:
            for index in range(count):
                row = request(index + 1, None, wall_start)
                batch["requests"].append(row)
                print(json.dumps({"event": "request", "concurrency": concurrency, **row}, ensure_ascii=False), flush=True)
                save()
                if not row["ok"]:
                    break
        else:
            barrier = threading.Barrier(concurrency)
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(request, i + 1, barrier, wall_start) for i in range(count)]
                for future in as_completed(futures):
                    row = future.result()
                    batch["requests"].append(row)
                    print(json.dumps({"event": "request", "concurrency": concurrency, **row}, ensure_ascii=False), flush=True)
                    save()
        batch["requests"].sort(key=lambda r: r["request"])
        batch["summary"] = summary(batch["requests"], time.perf_counter() - wall_start)
        batch["finished_at"] = timestamp()
        save()
        print(json.dumps({"event": "batch_done", "concurrency": concurrency, **batch["summary"]}, ensure_ascii=False), flush=True)
        if batch["summary"]["failed"]:
            report["stopped"] = "A request failed; no higher concurrency submitted"
            break

    report["finished_at"] = timestamp()
    report["actual_attempts"] = sum(len(b["requests"]) for b in report["batches"])
    save()
    print(json.dumps({"event": "finished", "report": str(output), "actual_attempts": report["actual_attempts"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
