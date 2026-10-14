"""Reproduce this batch's reviewed transcription and mathematical checks.

This is a fixed-batch evaluation, not a general model-text parser. Reviewed
transcriptions are bound to raw-answer hashes; changed text requires review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sympy as s
from inspect_baseline import inspect
from problems import SYMBENCH15, x, t, y

TRANSCRIPTIONS = [
    'sin(x)**2/2', '(x-1)*exp(x)', 'x**3*log(x)/3-x**3/9', '1', '1/2',
    '(2,1)', '(2,1,3)', 'Matrix([[1,-1],[-1,2]])',
    '[(sqrt(3),Matrix([-1/sqrt(6),1/sqrt(6)])),(sqrt(3),Matrix([1/sqrt(6),1/sqrt(6)]))]',
    '1', 'C1*exp(t**2/2)', 'C1*exp(-2*t)+t/2-1/4',
    'C1*exp(t)+C2*exp(2*t)', 'C1*cos(t)+C2*sin(t)+t', 'cos(2*t)',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('direct')
    parser.add_argument('summary')
    parser.add_argument('--out', default=str(Path(__file__).parent))
    args = parser.parse_args()
    raw = inspect(args.direct)
    manifest = json.loads(Path(__file__).with_name('reviewed_answers.json').read_text(encoding='utf-8'))
    namespace = {'x': x, 't': t, 'C1': s.Symbol('C1'), 'C2': s.Symbol('C2')}
    scores = []
    for problem, transcription in zip(SYMBENCH15, TRANSCRIPTIONS):
        key = problem['id']
        answer = raw[key]['model_answer']
        digest = hashlib.sha256(answer.encode('utf-8')).hexdigest()
        if manifest[key] != digest:
            raise ValueError(f'Raw answer changed; review required: {key}')
        candidate = s.sympify(transcription, locals=namespace)
        expected = s.sympify(problem['expected'], locals=namespace)
        if key == 'linear-algebra-04':
            passed = all(s.simplify(problem['expr']*vec-lam*vec) == s.zeros(2, 1)
                         for lam, vec in candidate)
            evidence = [str(s.simplify(problem['expr']*vec-lam*vec)) for lam, vec in candidate]
        elif isinstance(candidate, tuple):
            passed = all(s.simplify(a-b) == 0 for a, b in zip(candidate, expected))
            substitutions = dict(zip([s.Symbol(v, real=True) for v in problem['vars']], candidate))
            evidence = [str((eq.lhs-eq.rhs).subs(substitutions)) for eq in problem['expr']]
        else:
            difference = s.simplify(candidate-expected)
            passed = difference == s.zeros(2) if isinstance(difference, s.MatrixBase) else difference == 0
            evidence = str(difference)
        if key == 'linear-algebra-04':
            max_error = max(abs(float(a[0]-b[0])) for a,b in zip(candidate, expected))
        elif isinstance(candidate, tuple):
            max_error = max(abs(float(a-b)) for a,b in zip(candidate, expected))
        else:
            max_error = 0.0 if passed else None
        passed = passed and max_error is not None and max_error <= problem['threshold']
        scores.append({'id': key, 'category': problem['category'], 'raw_answer': answer,
                       'reviewed_transcription': transcription, 'source_sha256': digest,
                       'baseline_grade': 'PASS' if passed else 'FAIL', 'evidence': evidence,
                       'threshold': problem['threshold'], 'error_type': 'absolute', 'max_error': max_error})
    summary = json.loads(Path(args.summary).read_text(encoding='utf-8-sig'))
    rows = summary['rows']
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate summary IDs')
    by_id = {r['id']: r for r in rows}
    if set(by_id) != {p['id'] for p in SYMBENCH15} | {'rk4-bonus'}:
        raise ValueError('Summary IDs differ from expected 16 problems')
    for p in SYMBENCH15:
        if by_id[p['id']]['category'] != p['category']:
            raise ValueError('Summary category mismatch')
    count = sum(r['grade'] == 'PASS' for r in rows)
    if summary.get('passed') != count:
        raise ValueError('Summary total inconsistent')
    baseline = sum(r['baseline_grade'] == 'PASS' for r in scores)
    loop = sum(by_id[p['id']]['grade'] == 'PASS' for p in SYMBENCH15)
    result = {'baseline_reviewed_passed': baseline, 'baseline_total': 15,
              'baseline_accuracy': baseline/15, 'loop_summary_reported_passed': loop,
              'loop_total': 15, 'loop_summary_reported_accuracy': loop/15,
              'reported_difference_percentage_points': (loop-baseline)/15*100,
              'loop_independently_verified': False,
              'bonus_reported_grade': by_id['rk4-bonus']['grade'], 'rows': scores}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out/'batch_scoring.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# SymCheck 批量结果评分报告', '',
             '日期：2026 年 10 月 10 日。输入为队长提供的 direct_answers.json 与 summary.json。', '',
             '## 结果', '',
             f'直接作答经逐题阅读、固定转写及数学检查：{baseline}/15，正确率 {baseline/15:.2%}。', '',
             f'闭环摘要报告：{loop}/15，正确率 {loop/15:.2%}；与基线相差 {(loop-baseline)/15*100:.2f} 个百分点。', '',
             '闭环成绩尚未独立数学核验：摘要没有最终答案、采样误差、阈值或工具日志。has_report=true 只能证明摘要声称报告存在，不能证明报告已收到或内容正确。加分题单独记录为摘要 PASS，不计入 15 题正确率。', '',
             '## 逐题成绩', '',
             '| ID | 直接作答复核 | 闭环摘要 |', '| --- | --- | --- |']
    lines += [f"| {r['id']} | {r['baseline_grade']} | {by_id[r['id']]['grade']} |" for r in scores]
    lines += ['', '## 两道错误的证据', '',
              'linear-algebra-02：模型给出 (2,1,3)，标准解为 (1,2,3)。代回三式左边减右边的残差为 (0,3,-1)，超过 1e-8 阈值。', '',
              'linear-algebra-04：模型把两个特征值均写为 √3，正确特征值为 1 与 3。其两个向量的方向分别对应 1 和 3，所以配上 √3 后 A·v−λv 均非零。向量长度不为 1 可通过允许的非零倍数约定处理，但错误特征值不能因此判对。', '',
              '## 方法与复现', '',
              '原始回答由本次评测人员逐条阅读后转写为固定的 SymPy 表达式；这属于一次性人工辅助转写，不是通用自动文本评分器。程序只解析内部固定表达式，原始模型文本不交给 sympify。reviewed_answers.json 绑定每条原文的 SHA256；原文改变时拒绝复用评分。', '',
              '本批通过题的固定转写与标准答案精确等价，误差为零；通解常数统一命名，积分常数省略。标准答案此前已独立符号核验。本结果不代表直接作答执行过 SciPy 验证。', '',
              '运行：python score_batch.py direct_answers.json summary.json。依赖 SymPy，相关脚本和 reviewed_answers.json 放在同一目录。完整证据保存在 batch_scoring.json。', '',
              '## 可发给队长', '',
              '> 文件已收到，15 题 ID、分类和题面与题库一致。直接作答复核结果为 13/15（86.67%），错误为 linear-algebra-02、linear-algebra-04。闭环摘要报告 15/15（100%），表面提升 13.33 个百分点，但尚未收到闭环答案和验证日志，因此不能称为独立确认的提升。请补发对应 15 题的最终答案及 runs/ 验证证据；RK4 加分题单独统计。', '']
    (out/'SymCheck-批量结果评分报告.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Baseline reviewed: {baseline}/15; loop summary reported: {loop}/15; loop independently verified: False')


if __name__ == '__main__':
    main()
