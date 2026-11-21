"""Local-only UI test instrumentation around the unmodified application.

Arm a single request by writing ui-chat-probe-arm.json next to this module:
{"mode":"429-once"}, {"mode":"invalid-once"}, or {"mode":"429-all"}.
Only the next chat stream consumes the file. Faults occur before a model chunk.
No credentials, authorization headers or user messages are written to the audit.
"""
from contextvars import ContextVar
import json
from pathlib import Path
import threading
import time
import uuid

from app.services.llm.gemini import GeminiClient, classify_error

ROOT = Path(__file__).resolve().parent
ARM = ROOT / "ui-chat-probe-arm.json"
AUDIT = ROOT / "ui-chat-probe-events.jsonl"
LOCK = threading.Lock()
REQUEST = ContextVar("ui_chat_probe_request", default=None)
original_client = GeminiClient._client


def audit(kind, **values):
    record = {"kind": kind, "at": time.time(), **values}
    with LOCK:
        with AUDIT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class InjectedError(Exception):
    def __init__(self, status):
        self.status_code = status
        super().__init__(
            "LOCAL_TEST: simulated 429 RESOURCE_EXHAUSTED; retryDelay: 60s"
            if status == 429 else "LOCAL_TEST: simulated 400 API_KEY_INVALID"
        )


class ObservedModel:
    def __init__(self, inner, index):
        self.inner, self.index = inner, index

    def bind_tools(self, *args, **kwargs):
        return ObservedModel(self.inner.bind_tools(*args, **kwargs), self.index)

    def _start(self):
        context = REQUEST.get()
        attempt = {"request_id": context["id"] if context else None, "key_index": self.index + 1}
        if context:
            context["attempts"] += 1
            mode = context["mode"]
            if mode == "429-all" or mode in {"429-once", "invalid-once"} and context["attempts"] == 1:
                status = 400 if mode == "invalid-once" else 429
                audit("injected_key_error", **attempt, status=status)
                raise InjectedError(status)
        audit("provider_attempt", **attempt)
        return attempt

    def stream(self, *args, **kwargs):
        start = time.perf_counter()
        attempt = None
        try:
            attempt = self._start()
            yield from self.inner.stream(*args, **kwargs)
            audit("provider_done", **attempt, seconds=round(time.perf_counter() - start, 4))
        except Exception as exc:
            if attempt:
                audit("provider_error", **attempt, category=classify_error(exc), exception=type(exc).__name__)
            raise

    def invoke(self, *args, **kwargs):
        attempt = self._start()
        start = time.perf_counter()
        result = self.inner.invoke(*args, **kwargs)
        audit("provider_done", **attempt, seconds=round(time.perf_counter() - start, 4))
        return result


def observed_client(self, index, key):
    return ObservedModel(original_client(self, index, key), index)


GeminiClient._client = observed_client

from app.main import app as original_app


class ProbeApp:
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").endswith("/messages/stream"):
            return await original_app(scope, receive, send)
        mode = "observe"
        with LOCK:
            if ARM.exists():
                mode = json.loads(ARM.read_text(encoding="utf-8"))["mode"]
                ARM.unlink()
        context = {"id": uuid.uuid4().hex[:12], "mode": mode, "attempts": 0}
        token = REQUEST.set(context)
        started = time.perf_counter()
        pending = ""
        first = False
        audit("chat_start", request_id=context["id"], mode=mode)

        async def observed_send(message):
            nonlocal pending, first
            elapsed = round(time.perf_counter() - started, 4)
            if message["type"] == "http.response.start":
                audit("http_status", request_id=context["id"], status=message["status"], seconds=elapsed)
            elif message["type"] == "http.response.body":
                pending += message.get("body", b"").decode("utf-8", errors="replace")
                while "\n\n" in pending:
                    block, pending = pending.split("\n\n", 1)
                    event, data = "", {}
                    for line in block.splitlines():
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            try:
                                data = json.loads(line[5:].strip())
                            except ValueError:
                                pass
                    if event == "token" and data.get("text") and not first:
                        first = True
                        audit("first_token", request_id=context["id"], seconds=elapsed)
                    if event == "done":
                        audit("chat_done", request_id=context["id"], seconds=elapsed,
                              cached=data.get("assistant_message", {}).get("cached"),
                              server_duration=data.get("assistant_message", {}).get("duration_seconds"))
                    if event in {"error", "queued"}:
                        audit(event, request_id=context["id"], seconds=elapsed,
                              code=data.get("code"), position=data.get("position"))
            await send(message)

        try:
            await original_app(scope, receive, observed_send)
        finally:
            audit("chat_end", request_id=context["id"], attempts=context["attempts"],
                  seconds=round(time.perf_counter() - started, 4))
            REQUEST.reset(token)


app = ProbeApp()
