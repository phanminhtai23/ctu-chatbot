"""Summarize saved browser timings, existing answer checks and real SDK audit."""
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'ctu-chatbot-be'))
from tests.rag_cases_hard import HARD_CASES
from tests.answer_checks import case_problems, friendly_problems


def dist(values):
    values=sorted(v for v in values if v is not None)
    if not values:return None
    return {'n':len(values),'min':round(values[0],3),'p50':round(statistics.median(values),3),
            'p95_nearest_rank':round(values[math.ceil(len(values)*.95)-1],3),'max':round(values[-1],3)}


def main():
    path=ROOT/'ui-hard-load-results-20261121.json'
    report=json.loads(path.read_text(encoding='utf-8'))
    all_events=[json.loads(l) for l in (ROOT/'ui-hard-load-events-20261121.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    by_id={c.id:c for c in HARD_CASES}
    results=report['results']
    known_labels={r['caseId'] for r in results}|{r['caseId'] for r in report.get('rechecks',[])}|{'verify_k08'}
    events=[e for e in all_events if e.get('case') in known_labels]
    for row in results:
        if row.get('answer'):
            row['answer_check_problems']=case_problems(by_id[row['caseId']],row['answer'])
            row['style_problems']=friendly_problems(row['answer'])
            row['expected_article_cited']=any(s.get('article')==by_id[row['caseId']].article for s in row.get('sources',[]))
        else:row['answer_check_problems']=['No complete answer']
    completed=[r for r in results if r.get('doneS') is not None]
    for row in report.get('rechecks',[]):
        row['answer_check_problems']=case_problems(by_id[row['baseCaseId']],row['answer']) if row.get('answer') else ['No complete answer']
    verify=report.get('verifyK08',{})
    if verify.get('answer'):
        verify['answer_check_problems']=case_problems(by_id['k08'],verify['answer'])
    by_request=defaultdict(list)
    for event in events:by_request[event.get('request_id') or event.get('id')].append(event)
    failovers=[]
    for rid,trace in by_request.items():
        for i,error in enumerate(trace):
            if error['kind']!='provider_error' or not error.get('before_first_chunk') or error.get('category') not in {'rate_limited','invalid_key'}:continue
            next_call=next((e for e in trace[i+1:] if e['kind']=='provider_attempt'),None)
            if next_call and next_call['key_index']!=error['key_index']:
                failovers.append({'request_id':rid,'case':error.get('case'),'status':error.get('status'),
                    'from_key':error['key_index'],'to_key':next_call['key_index'],
                    'gap_s':round(next_call['at']-error['at'],4),
                    'chat_completed':any(e['kind']=='chat_done' for e in trace),
                    'chat_error':next((e.get('code') for e in trace if e['kind']=='error'),None)})
    report['summary']={
        'attempted_chats':len(results),'completed_chats':len(completed),
        'total_ui_submissions_including_rechecks':len(results)+len(report.get('rechecks',[]))+bool(verify),
        'total_completed_including_rechecks':len(completed)+sum(r.get('doneS') is not None for r in report.get('rechecks',[]))+bool(verify.get('doneS')),
        'unlabelled_external_chats_excluded':sum(e['kind']=='chat_start' and e.get('case') not in known_labels for e in all_events),
        'transport_or_llm_errors':dict(Counter(r.get('error') or r.get('readError') for r in results if r.get('error') or r.get('readError'))),
        'cached_answers':sum(r.get('cached') is True for r in results),
        'ui_completed':sum(r.get('uiCompleted') is True for r in results),
        'automatic_answer_checks_passed':sum(not r['answer_check_problems'] for r in results),
        'automatic_answer_checks_flagged':[{'case':r['caseId'],'problems':r['answer_check_problems']} for r in results if r['answer_check_problems']],
        'ttft_s':dist(r.get('ttftS') for r in completed),'done_s':dist(r.get('doneS') for r in completed),
        'phase_metrics':{str(phase):{'chats':sum(r['phase']==phase for r in results),
            'ttft_s':dist(r.get('ttftS') for r in completed if r['phase']==phase),
            'done_s':dist(r.get('doneS') for r in completed if r['phase']==phase),
            'queued_chats':sum(bool(r.get('queued')) for r in results if r['phase']==phase)} for phase in (4,8)},
        'real_provider_attempts':sum(e['kind']=='provider_attempt' for e in events),
        'real_provider_successful_calls':sum(e['kind']=='provider_done' for e in events),
        'real_provider_errors':dict(Counter(str(e.get('status'))+' '+e.get('category','') for e in events if e['kind']=='provider_error')),
        'attempts_by_key':dict(Counter(e['key_index'] for e in events if e['kind']=='provider_attempt')),
        'observed_failovers':failovers,
        'successful_chats_after_real_429':len({f['request_id'] for f in failovers if f['status']==429 and f['chat_completed']}),
        'tokens':{k:sum(e.get('usage',{}).get(k,0) for e in events if e['kind']=='provider_done') for k in ('input_tokens','output_tokens','total_tokens')},
    }
    report['notes']=[
        'All chats were entered using the real UI composer in isolated browser contexts; no API calls submitted directly by the driver.',
        'Unmodified application queue concurrency=4; 8 UI users exercise queue waiting rather than 8 active chat pipelines.',
        'Observation wrapper records SDK status/key indexes only. No errors were injected in this run.',
        'Automatic answer checks are regex-based regression checks, not a complete proof of semantic correctness.',
        'Provider attempts include retries on different keys; token totals include only successfully completed SDK calls.',
        'A supplementary instruction suffix in this initial run was mangled by PowerShell stdin encoding; the original hard questions and numeric inputs are intact. Exact sent questions are retained in the cases artifact.',
        'Unlabelled requests not submitted by the driver are excluded from SDK statistics. They can still share provider quotas with the benchmark.',
        'Rechecks use the original Vietnamese questions without the supplementary suffix. Initial-run statistics are kept separate from retries.',
    ]
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
