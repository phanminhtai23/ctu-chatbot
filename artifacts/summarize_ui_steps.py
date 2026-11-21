import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'ctu-chatbot-be'))
from tests.rag_cases_hard import HARD_CASES
from tests.answer_checks import case_problems

p=ROOT/'ui-step-results-20261121.json'
report=json.loads(p.read_text(encoding='utf-8'))
traces=[json.loads(l) for l in (ROOT/'ui-step-timings-20261121.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
lookup={r['label']:r for r in traces}
case=next(c for c in HARD_CASES if c.id=='k03')
for ui in report['results']:
    trace=lookup[ui['label']]
    spans=trace['spans'];marks=trace['marks']
    def group(name):return [s for s in spans if s['name']==name]
    def span(name):return group(name)[0]
    def mark(name):return next(m['seconds'] for m in marks if m['name']==name)
    def duration(name):return sum(s['duration_s'] for s in group(name))
    answer_calls=group('llm_answer')
    astart=min(s['start_s'] for s in answer_calls)
    first=min(s['first_text_s'] for s in answer_calls if s.get('first_text_s') is not None)
    classify=span('route_classification')
    stages={
        'http_auth_validation_admission':mark('queue_wait_start'),
        'queue_wait':duration('queue_wait'),
        'checkpoint_graph_setup':mark('generate_start')-mark('queue_wait_end'),
        'rag_and_knowledge':classify['start_s']-mark('generate_start'),
        'route_classification':classify['duration_s'],
        'llm_extract':duration('llm_extract'),
        'python_math':duration('python_math'),
        'prompt_build_and_misc':astart-classify['end_s']-duration('llm_extract')-duration('python_math'),
        'answer_wait_for_first_text':first-astart,
        'answer_stream_and_finalize':mark('generate_end')-first,
        'final_checkpoint_and_db':mark('done_sse')-mark('generate_end'),
        'browser_network_and_render':ui['uiDoneS']-mark('done_sse'),
    }
    ui['stage_seconds']={k:round(v,6) for k,v in stages.items()}
    ui['server_done_s']=mark('done_sse')
    ui['rag_details']={
        'embedding_api_s':round(duration('embedding_api'),6),
        'embedding_cache':[{'hit':s['cache_hit'],'duration_s':round(s['duration_s'],6)} for s in group('query_embedding_cache')],
        'chroma_query_s':round(duration('chroma_query'),6),
        'chroma_queries':len(group('chroma_query')),
        'retrieved_articles':[s['articles'] for s in group('document_retrieval')],
        'knowledge_retrieval_s':round(duration('knowledge_retrieval'),6),
    }
    ui['db_details']={name:round(duration(name),6) for name in ['checkpoint_get_tuple','checkpoint_put','checkpoint_put_writes','conversation_db_update','usage_db_insert']}
    ui['llm_calls']=[s for s in spans if s['name'] in {'llm_route','llm_extract','llm_answer'}]
    ui['provider_attempts']=group('provider_attempt')
    ui['answer_check_problems']=case_problems(case,ui.get('answer',''))
    ui['stage_sum_s']=round(sum(stages.values()),6)
    ui['raw_trace']=trace
names=list(report['results'][0]['stage_seconds'])
report['mean_stage_seconds']={name:round(statistics.mean(r['stage_seconds'][name] for r in report['results']),6) for name in names}
report['totals']={
    'mean_ui_done_s':round(statistics.mean(r['uiDoneS'] for r in report['results']),4),
    'mean_ui_first_text_s':round(statistics.mean(r['uiFirstS'] for r in report['results']),4),
    'all_actual_vector_search':all(r['rag_details']['chroma_queries']>0 for r in report['results']),
    'all_uncached_answers':all(r.get('cached') is False for r in report['results']),
    'all_answer_checks_passed':all(not r['answer_check_problems'] for r in report['results']),
    'provider_attempts':sum(len(r['provider_attempts']) for r in report['results']),
    'provider_errors':sum(bool(s.get('exception')) for r in report['results'] for s in r['provider_attempts']),
    'keys_used':sorted({s['key_index'] for r in report['results'] for s in r['provider_attempts']}),
}
report['notes']=[
    'Same hard question submitted five times sequentially in five new conversations through the real UI.',
    'Browser measurements start at the native Send click. Existing empty conversations were created before the click.',
    'UI first text and final render are measured with MutationObserver; stream done and token arrival are measured on a response clone.',
    'Stage durations partition the end-to-end UI completion interval. Browser network/render is the remaining wall time outside the backend interval.',
    'RAG details are nested within rag_and_knowledge and must not be added a second time.',
    'Raw checkpoint operations can overlap graph generation; final_checkpoint_and_db measures only the post-generation critical path.',
    'Query-vector cache stays enabled. Only the first request needs a query embedding RPC; every run still queries ChromaDB.',
    'No document OCR, indexing or document embedding was run; only the first question embedding was created.',
    'This is a small sequential local profile, not production latency or a load test.',
]
p.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'runs':[{'label':r['label'],'stages':r['stage_seconds'],'rag':r['rag_details'],'uiFirstS':r['uiFirstS'],'uiDoneS':r['uiDoneS'],'answerProblems':r['answer_check_problems']} for r in report['results']],'means':report['mean_stage_seconds'],'totals':report['totals']},ensure_ascii=False,indent=2))
