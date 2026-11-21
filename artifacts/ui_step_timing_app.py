"""Local, passive wall-clock tracing for five UI requests. No fault injection."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
from pathlib import Path
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parent
AUDIT=ROOT/'ui-step-timings-20261121.jsonl'
REQUEST=ContextVar('step_request',default=None)
PHASE=ContextVar('step_phase',default='answer')
LOCK=threading.Lock()


def now():return time.perf_counter()


def add_span(name,start,end,**metadata):
    ctx=REQUEST.get()
    if ctx is not None:
        row={'name':name,'start_s':start-ctx['start'],'end_s':end-ctx['start'],'duration_s':end-start,**metadata}
        with LOCK:ctx['spans'].append(row)


def mark(name,**metadata):
    ctx=REQUEST.get()
    if ctx is not None:
        with LOCK:ctx['marks'].append({'name':name,'seconds':now()-ctx['start'],**metadata})


def wrap_function(owner,attribute,name,phase=None,meta=None):
    original=getattr(owner,attribute)
    @wraps(original)
    def traced(*args,**kwargs):
        if REQUEST.get() is None:return original(*args,**kwargs)
        token=PHASE.set(phase) if phase else None
        start=now();details={}
        try:
            result=original(*args,**kwargs)
            if meta:details=meta(args,kwargs,result)
            return result
        except Exception as exc:
            details['exception']=type(exc).__name__
            raise
        finally:
            add_span(name,start,now(),**details)
            if token is not None:PHASE.reset(token)
    setattr(owner,attribute,traced)


from app.services.chat import graph as graph_module, gpa_assist
from app.services.chat import scope, queue as queue_module
from app.services.chat.text import message_text
from app.services.llm.gemini import GeminiClient,classify_error,_status_code
from app.services.rag.embeddings import CachedQueryEmbedder,GeminiEmbedder
from app.services.rag.store import Retriever,VectorStore
from chromadb.api.models.Collection import Collection
from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres import PostgresSaver

wrap_function(Retriever,'retrieve','document_retrieval',meta=lambda a,k,r:{'articles':[h.article for h in r]})
wrap_function(Retriever,'retrieve_knowledge','knowledge_retrieval',meta=lambda a,k,r:{'hits':len(r)})
wrap_function(VectorStore,'search','vector_search_total',meta=lambda a,k,r:{'collection':a[0].collection_name,'hits':len(r)})
wrap_function(Collection,'query','chroma_query',meta=lambda a,k,r:{'collection':a[0].name})
wrap_function(GeminiEmbedder,'embed_query','embedding_api')

original_embed_query=CachedQueryEmbedder.embed_query
@wraps(original_embed_query)
def cached_embed(self,text):
    if REQUEST.get() is None:return original_embed_query(self,text)
    hit=text in self._cache
    start=now()
    try:return original_embed_query(self,text)
    finally:add_span('query_embedding_cache',start,now(),cache_hit=hit)
CachedQueryEmbedder.embed_query=cached_embed

wrap_function(scope,'classify','route_classification',phase='route',meta=lambda a,k,r:{'route':r})
wrap_function(graph_module,'build_gpa_report','gpa_report_total',phase='extract',meta=lambda a,k,r:{'report_chars':len(r)})
wrap_function(gpa_assist,'build_report_from_extraction','python_math',meta=lambda a,k,r:{'report_chars':len(r)})
wrap_function(graph_module,'build_system_prompt','system_prompt_build',meta=lambda a,k,r:{'chars':len(r)})
wrap_function(graph_module,'build_llm_history','llm_history_build')
for method in ('get_tuple','put','put_writes'):
    wrap_function(PostgresSaver,method,'checkpoint_'+method)

original_add_node=StateGraph.add_node
@wraps(original_add_node)
def add_node(self,node,action=None,*args,**kwargs):
    if node=='generate' and action is not None:
        original=action
        @wraps(original)
        def generate(*a,**kw):
            start=now();mark('generate_start')
            try:return original(*a,**kw)
            finally:add_span('generate_total',start,now());mark('generate_end')
        action=generate
    return original_add_node(self,node,action,*args,**kwargs)
StateGraph.add_node=add_node

original_wait=queue_module.TurnQueue.wait
@wraps(original_wait)
def wait(self,ticket):
    start=now();mark('queue_wait_start')
    try:yield from original_wait(self,ticket)
    finally:add_span('queue_wait',start,now());mark('queue_wait_end')
queue_module.TurnQueue.wait=wait
wrap_function(queue_module.TurnQueue,'enter','queue_admission')

original_stream=GeminiClient.stream
@wraps(original_stream)
def stream(self,messages,tools=None):
    if REQUEST.get() is None:
        yield from original_stream(self,messages,tools=tools)
        return
    phase=PHASE.get();start=now();first_text=None;chars=0;usage={'input_tokens':0,'output_tokens':0,'total_tokens':0,'cache_read_tokens':0}
    mark('llm_start',phase=phase)
    try:
        for chunk in original_stream(self,messages,tools=tools):
            text=message_text(chunk)
            if text and first_text is None:
                first_text=now();mark('llm_first_text',phase=phase)
            chars+=len(text)
            delta=getattr(chunk,'usage_metadata',None) or {}
            for key in ('input_tokens','output_tokens','total_tokens'):usage[key]+=delta.get(key,0)
            usage['cache_read_tokens']+=(delta.get('input_token_details') or {}).get('cache_read',0)
            yield chunk
    finally:
        end=now()
        add_span('llm_'+phase,start,end,first_text_s=first_text-REQUEST.get()['start'] if first_text else None,output_chars=chars,usage=usage)
        mark('llm_end',phase=phase)
GeminiClient.stream=stream

original_client=GeminiClient._client
class ObservedModel:
    def __init__(self,inner,index):self.inner,self.index=inner,index
    def bind_tools(self,*a,**k):return ObservedModel(self.inner.bind_tools(*a,**k),self.index)
    def stream(self,*a,**k):
        start=now();details={'key_index':self.index+1,'phase':PHASE.get()}
        try:yield from self.inner.stream(*a,**k)
        except Exception as exc:
            details.update(category=classify_error(exc),status=_status_code(exc),exception=type(exc).__name__)
            raise
        finally:add_span('provider_attempt',start,now(),**details)
    def invoke(self,*a,**k):return self.inner.invoke(*a,**k)
def client(self,index,key):return ObservedModel(original_client(self,index,key),index)
GeminiClient._client=client

from app.main import app as original_app
from app.api.v1 import conversations as conversations_module
wrap_function(conversations_module,'_pre_screen','input_screen',meta=lambda a,k,r:{'answer_cached':r is not None})
wrap_function(conversations_module,'_admit','rate_limit_and_admission')
wrap_function(conversations_module,'_touch','conversation_db_update')
wrap_function(conversations_module,'record_usage','usage_db_insert')


class TimingApp:
    async def __call__(self,scope,receive,send):
        headers=dict(scope.get('headers',[])) if scope['type']=='http' else {}
        label=headers.get(b'x-step-run',b'').decode('ascii',errors='replace')
        if not label or not scope.get('path','').endswith('/messages/stream'):
            return await original_app(scope,receive,send)
        ctx={'id':uuid.uuid4().hex[:12],'label':label,'start':now(),'spans':[],'marks':[]}
        token=REQUEST.set(ctx);pending='';first=True
        mark('request_received')
        async def observed_send(message):
            nonlocal pending,first
            if message['type']=='http.response.start':mark('response_headers',status=message['status'])
            if message['type']=='http.response.body':
                pending+=message.get('body',b'').decode('utf-8',errors='replace')
                while '\n\n' in pending:
                    block,pending=pending.split('\n\n',1);event='';data={}
                    for line in block.splitlines():
                        if line.startswith('event:'):event=line[6:].strip()
                        if line.startswith('data:'):
                            try:data=json.loads(line[5:])
                            except ValueError:pass
                    if event=='start':mark('user_message_event')
                    if event=='queued':mark('queued',position=data.get('position'))
                    if event=='token' and data.get('text') and first:first=False;mark('first_token_sse')
                    if event=='done':mark('done_sse',cached=data.get('assistant_message',{}).get('cached'))
                    if event=='error':mark('error_sse',code=data.get('code'))
            await send(message)
        try:await original_app(scope,receive,observed_send)
        finally:
            mark('request_end')
            with LOCK:
                with AUDIT.open('a',encoding='utf-8') as f:f.write(json.dumps(ctx,ensure_ascii=False)+'\n')
            REQUEST.reset(token)


app=TimingApp()
