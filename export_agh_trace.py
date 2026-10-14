"""Export AGH session ledgers (official AGH Trace) for every SymCheck workspace.

Requires the AGH daemon to be up (run restart_agh.py first if it is not).
Output: batch_out/agh_trace/<workspace>.jsonl + <workspace>.html + manifest.md

The AGH ledger is workspace-granular (one session per workspace directory);
our own JSONL logger is problem-granular. manifest.md documents the mapping.
"""
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
AGNES = Path(r'C:/Users/TEMP/Desktop/agnes-harness/agnes-harness-main/packages/cli/dist/local/agnes.mjs')
OUT = ROOT / 'batch_out' / 'agh_trace'

# 已知工作区的批次说明(与《SymCheck-成绩单》/README 的 run_id 证据互补);
# 未知的 .agh_ws* 目录(如冻结夜新工作区)自动纳入并标注"待补充说明"
KNOWN = {
    '.': '主工作区:10/9 端到端主批(15 题 + 首个闭环任务)',
    '.agh_ws3': '10/9 深夜加固批 + 10/10 RK4 加分题端到端(run-20261010-130721)',
    '.agh_ws2': '10/9 深夜中间批次(冷启动测试)',
    '.agh_ws': '10/9 最早批次(冷启动测试)',
}


def discover_workspaces():
    ws = ['.']
    for d in sorted(ROOT.glob('.agh_ws*')):
        if d.is_dir():
            ws.append(d.name)
    return ws


def run_agnes(args, cwd):
    return subprocess.run(['node', str(AGNES), *args], cwd=str(cwd),
                          capture_output=True, text=True, encoding='utf-8', timeout=180)


def list_sessions(ws_dir):
    r = run_agnes(['sessions', 'list', '--cwd', str(ws_dir)], ROOT)
    ids = [line.split('\t')[0] for line in r.stdout.splitlines() if line.strip()]
    return ids


def summarize(path):
    types, dates, turns, tools = Counter(), Counter(), 0, 0
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        types[e.get('type', '?')] += 1
        dates[e.get('ts', '')[:10]] += 1
        if e.get('type') == 'turn/start':
            turns += 1
        if e.get('type') == 'tool/call':
            tools += 1
    first = last = ''
    lines = path.read_text(encoding='utf-8').splitlines()
    if lines:
        first = json.loads(lines[0]).get('ts', '')[:16].replace('T', ' ')
        last = json.loads(lines[-1]).get('ts', '')[:16].replace('T', ' ')
    return first, last, turns, tools, dict(dates), dict(types)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = [f'# AGH Trace 导出清单(生成于 {datetime.now():%Y-%m-%d %H:%M})', '',
                '每个 JSONL 是 AGH 官方会话账本(协议事件, 每行一条), HTML 是可读时间线。',
                '默认脱敏(路径/密钥/PII), 未用 --raw。与题目粒度 JSONL(runs/) 互为双份证据。', '']
    for rel in discover_workspaces():
        note = KNOWN.get(rel, '批次说明待补充(见 manifest.md, 可按运行日期对照《成绩单》)')
        ws = (ROOT / rel).resolve() if rel != '.' else ROOT
        name = 'main' if rel == '.' else rel.lstrip('.')
        try:
            ids = list_sessions(ws)
        except Exception as e:
            manifest.append(f'- {name}: 无会话(可能未跑过批, {e.__class__.__name__})')
            continue
        if not ids:
            manifest.append(f'- {name}: 无会话记录')
            continue
        for sid in ids:
            safe = sid.replace(':', '-')[-20:]
            dest = OUT / f'{name}.jsonl'
            r = run_agnes(['export', sid, '--cwd', str(ws), '--out', str(dest)], ROOT)
            if r.returncode != 0:
                manifest.append(f'- {name}: 导出失败 {r.stderr.strip()[:120]}')
                continue
            r2 = run_agnes(['export', sid, '--cwd', str(ws), '--html', '--out', str(OUT / f'{name}.html')], ROOT)
            first, last, turns, tools, dates, types = summarize(dest)
            manifest.append(f'- **{name}**({note}): {turns} 轮 / {tools} 次工具调用 / {sum(types.values())} 事件 / {first} → {last}')
            manifest.append(f'  - 事件分布: {types}')
            manifest.append(f'  - 日期分布: {dates}')
            manifest.append(f'  - 文件: batch_out/agh_trace/{name}.jsonl / {name}.html')
            manifest.append('')
    (OUT / 'manifest.md').write_text('\n'.join(manifest) + '\n', encoding='utf-8')
    print((OUT / 'manifest.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    main()
