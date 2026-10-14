"""Compare reviewed baseline against final verify events, joined by problem ID."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from collections import Counter
import sympy as s
from problems import SYMBENCH15, RK4_BONUS, x, t
from inspect_baseline import inspect
from score_batch import TRANSCRIPTIONS

BASE = {p['id']: p for p in SYMBENCH15}
ALL = {**BASE, RK4_BONUS['id']: RK4_BONUS}

def baseline_scores(path):
    records = inspect(path)
    hashes = json.loads(Path(__file__).with_name('reviewed_answers.json').read_text(encoding='utf-8'))
    transcriptions = dict(zip(BASE, TRANSCRIPTIONS))
    namespace = {'x':x,'t':t,'C1':s.Symbol('C1'),'C2':s.Symbol('C2')}
    result = {}
    for key,p in BASE.items():
        answer = records[key]['model_answer']
        row = {'grade':'MANUAL','max_error':None,'threshold':p['threshold'],
               'raw_answer':answer,'reason':'Raw answer changed; reviewed transcription required'}
        if hashlib.sha256(answer.encode('utf-8')).hexdigest() == hashes[key]:
            a = s.sympify(transcriptions[key],locals=namespace)
            b = s.sympify(p['expected'],locals=namespace)
            if key == 'linear-algebra-04':
                error = max(abs(float(av[0]-bv[0])) for av,bv in zip(a,b))
                residual_ok = all(s.simplify(p['expr']*v-lam*v)==s.zeros(2,1) for lam,v in a)
                ok = residual_ok and error<=p['threshold']
            elif isinstance(a,tuple):
                error = max(abs(float(av-bv)) for av,bv in zip(a,b))
                ok = len(a)==len(b) and error<=p['threshold']
            else:
                delta = s.simplify(a-b)
                zero = delta==s.zeros(*delta.shape) if isinstance(delta,s.MatrixBase) else delta==0
                error = 0.0 if zero else None
                ok = zero
            row.update(grade='PASS' if ok else 'FAIL',max_error=error,
                       reason='Hash-bound reviewed transcription checked against local expected',
                       transcription=transcriptions[key])
        result[key] = row
    return result

def event_type(event):
    return event.get('event',event.get('type',event.get('event_type')))

def verify_data(event):
    containers = [event] + [event[k] for k in ('data','payload','details') if isinstance(event.get(k),dict)]
    values = {}
    for container in containers:
        for key in ('verdict','value','max_error','threshold','error_type','check','op'):
            if key in container:
                if key in values and values[key] != container[key]:
                    raise ValueError('Conflicting verify fields: '+key)
                values[key] = container[key]
    return values

def audit(row, runs):
    result = {'summary_grade':row.get('grade'),'grade':'UNVERIFIED','issues':[],
              'last_verify':None,'event_types':{},'math_verified':False}
    run_id = row.get('run_id')
    if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',run_id):
        result['issues'].append('Invalid run_id'); return result
    path = Path(runs)/(run_id+'.jsonl')
    result['run_id'] = run_id
    if not path.is_file():
        result['issues'].append('Missing log'); return result
    counts = Counter(); last = None
    for number,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
        if not line.strip(): continue
        try:
            event = json.loads(line)
            if not isinstance(event,dict): raise ValueError('Event is not object')
            if event.get('run_id',run_id)!=run_id: raise ValueError('run_id mismatch')
            kind = event_type(event)
            counts[str(kind)] += 1
            if kind=='verify': last = (number,event)
        except (ValueError,TypeError) as error:
            result['issues'].append(f'Line {number}: {error}')
    result['event_types'] = dict(counts)
    if last is None:
        result['issues'].append('No verify event'); return result
    try:
        fields = verify_data(last[1])
    except ValueError as error:
        result['issues'].append(str(error)); return result
    result['last_verify'] = {'line':last[0],**fields}
    verdict = fields.get('verdict')
    if verdict not in ('PASS','FAIL','MANUAL'):
        result['issues'].append('Missing or invalid final verify verdict')
    if verdict != row.get('grade'):
        result['issues'].append('Summary differs from LAST verify verdict')
    if row.get('category')!=ALL[row['id']]['category']:
        result['issues'].append('Category mismatch')
    if verdict=='PASS' and row.get('rc')!=0:
        result['issues'].append('PASS with nonzero/missing rc')
    if fields.get('error_type') not in (None,'absolute'):
        result['issues'].append('Not absolute error')
    # Some verification checks concern convergence order, not an error norm.
    # Only validate a numeric comparator when explicitly supplied; never infer
    # that value is an error or require its threshold to equal problem threshold.
    if 'value' in fields and 'threshold' in fields and fields.get('op') in ('<=','<','>=','>'):
        try:
            v,threshold = float(fields['value']),float(fields['threshold'])
            if not math.isfinite(v) or not math.isfinite(threshold): raise ValueError('Nonfinite comparator')
            predicates={'<=':v<=threshold,'<':v<threshold,'>=':v>=threshold,'>':v>threshold}
            if (verdict=='PASS') != predicates[fields['op']] and verdict!='MANUAL':
                result['issues'].append('Verdict contradicts numeric comparator')
        except (ValueError,TypeError): result['issues'].append('Invalid numeric comparator')
    if not result['issues']:
        result['grade']=verdict
    return result

def analyze(direct, summary_path, runs):
    baseline = baseline_scores(direct)
    summary = json.loads(Path(summary_path).read_text(encoding='utf-8-sig'))
    rows = summary['rows']; by_id = {}
    for row in rows:
        key=row['id']
        if key in by_id or key not in ALL: raise ValueError('Duplicate or unknown summary ID: '+str(key))
        by_id[key]=row
    results=[]
    for key,p in BASE.items():
        loop = audit(by_id[key],runs) if key in by_id else {'grade':'UNVERIFIED','issues':['Missing summary row'],'math_verified':False}
        results.append({'id':key,'category':p['category'],'threshold':p['threshold'],
                        'error_type':'absolute','baseline':baseline[key],'loop':loop})
    bonus = audit(by_id['rk4-bonus'],runs) if 'rk4-bonus' in by_id else None
    base_pass=sum(r['baseline']['grade']=='PASS' for r in results)
    loop_pass=sum(r['loop']['grade']=='PASS' for r in results)
    complete=all(r['baseline']['grade'] in ('PASS','FAIL') and r['loop']['grade'] in ('PASS','FAIL') for r in results)
    return {'scope':'Baseline mathematical grading + final-verify log consistency; not independent loop re-solving',
            'total':15,'baseline_passed':base_pass,'baseline_accuracy':base_pass/15,
            'baseline_manual':sum(r['baseline']['grade']=='MANUAL' for r in results),
            'loop_audited_passed':loop_pass,'loop_audited_accuracy':loop_pass/15 if complete else None,
            'comparison_complete':complete,
            'improvement_percentage_points':(loop_pass-base_pass)/15*100 if complete else None,
            'rows':results,'bonus':bonus}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--direct',default='batch_out/direct_answers.json')
    parser.add_argument('--summary',default='batch_out/summary.json')
    parser.add_argument('--runs',default='runs')
    parser.add_argument('--out',default='comparison_out.json')
    args=parser.parse_args()
    result=analyze(args.direct,args.summary,args.runs)
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# SymCheck 对比评分报告','',result['scope'],'',
           f"基线 PASS：{result['baseline_passed']}/15；待复核：{result['baseline_manual']}。",'',
           f"闭环日志审计 PASS：{result['loop_audited_passed']}/15；对比完整：{result['comparison_complete']}。",'',
           '| ID | 基线 | 闭环日志审计 | 问题 |','| --- | --- | --- | --- |']
    for r in result['rows']:
        lines.append(f"| {r['id']} | {r['baseline']['grade']} | {r['loop']['grade']} | {'; '.join(r['loop']['issues'])} |")
        print(r['id'],r['baseline']['grade'],r['loop']['grade'])
    lines+=['',f"正确率提升（百分点）：{result['improvement_percentage_points']}。缺失日志或待人工复核时不计算提升。",'',
            '按文件行顺序取最后一个 verify；允许先 FAIL 后 PASS，不从 summary 自行补造判定。加分题单独统计。日志一致性不等于独立数学正确性证明。']
    out.with_suffix('.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f"Baseline {result['baseline_passed']}/15; comparison_complete={result['comparison_complete']}")

if __name__=='__main__': main()
