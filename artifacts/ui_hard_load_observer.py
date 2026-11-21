"""Observe real UI load only. No fault injection, no changes to key selection."""
from contextvars import ContextVar
import json
from pathlib import Path
import threading
import time
import uuid

from app.services.llm.gemini import GeminiClient, classify_error, _status_code, retry_delay_seconds

AUDIT = Path(__file__).with_name("ui-hard-load-events-20261121.jsonl")
LOCK = threading.Lock()
REQUEST = ContextVar("hard_load_request", default=None)
original_client = GeminiClient._client


def audit(kind, **values):
    with LOCK:
        with AUDIT.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"kind":kind,"at":time.time(),**values}, ensure_ascii=False)+"\n")


class ObservedModel:
    def __init__(self, inner, index):
        self.inner, self.index = inner, index

    def bind_tools(self, *args, **kwargs):
        return ObservedModel(self.inner.bind_tools(*args, **kwargs), self.index)

    def stream(self, *args, **kwargs):
        context = REQUEST.get() or {}
        call = {"request_id":context.get("id"),"case":context.get("case"),
                "key_index":self.index+1,"call_id":uuid.uuid4().hex[:10]}
        start = time.perf_counter()
        first = True
        usage = {"input_tokens":0,"output_tokens":0,"total_tokens":0}
        audit("provider_attempt", **call)
        try:
            for chunk in self.inner.stream(*args, **kwargs):
                if first:
                    audit("provider_first_chunk", **call, seconds=round(time.perf_counter()-start,4))
                    first = False
                for name in usage:
                    usage[name] += (getattr(chunk,"usage_metadata",None) or {}).get(name,0)
                yield chunk
            audit("provider_done", **call, seconds=round(time.perf_counter()-start,4),usage=usage)
        except Exception as exc:
            # Only classifications/status are stored; never raw SDK errors or credentials.
            audit("provider_error", **call, category=classify_error(exc), status=_status_code(exc),
                  retry_after=retry_delay_seconds(exc,60), before_first_chunk=first,
                  seconds=round(time.perf_counter()-start,4))
            raise

    def invoke(self, *args, **kwargs):
        return self.inner.invoke(*args, **kwargs)


def observed_client(self, index, key):
    return ObservedModel(original_client(self,index,key),index)


GeminiClient._client = observed_client
from app.main import app as original_app


class ObserverApp:
    async def __call__(self, scope, receive, send):
        if scope["type"]!="http" or not scope.get("path","").endswith("/messages/stream"):
            return await original_app(scope,receive,send)
        headers=dict(scope.get("headers",[]))
        context={"id":uuid.uuid4().hex[:12],"case":headers.get(b"x-ui-benchmark-case",b"unlabelled").decode("ascii",errors="replace")[:80]}
        token=REQUEST.set(context)
        start=time.perf_counter()
        pending=""
        first=True
        audit("chat_start",request_id=context["id"],case=context["case"])

        async def observed_send(message):
            nonlocal pending,first
            elapsed=round(time.perf_counter()-start,4)
            if message["type"]=="http.response.start":
                audit("http_status",**context,status=message["status"],seconds=elapsed)
            elif message["type"]=="http.response.body":
                pending+=message.get("body",b"").decode("utf-8",errors="replace")
                while "\n\n" in pending:
                    block,pending=pending.split("\n\n",1)
                    event,data="",{}
                    for line in block.splitlines():
                        if line.startswith("event:"): event=line[6:].strip()
                        if line.startswith("data:"):
                            try: data=json.loads(line[5:])
                            except ValueError: pass
                    if event=="token" and data.get("text") and first:
                        first=False
                        audit("first_token",**context,seconds=elapsed)
                    if event=="done":
                        msg=data.get("assistant_message",{})
                        audit("chat_done",**context,seconds=elapsed,cached=msg.get("cached"),server_duration=msg.get("duration_seconds"))
                    if event in {"queued","error"}:
                        audit(event,**context,seconds=elapsed,position=data.get("position"),code=data.get("code"),retry_after=data.get("retry_after"))
            await send(message)
        try:
            await original_app(scope,receive,observed_send)
        finally:
            audit("chat_end",**context,seconds=round(time.perf_counter()-start,4))
            REQUEST.reset(token)


app=ObserverApp()
