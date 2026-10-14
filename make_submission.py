"""Assemble the SymCheck submission ZIP (code + evidence + optional docs/video).

Dry-run by default: just reports what would be packed and the total size.
--extra lets 10/14 packaging add the docs, declaration and demo video.
"""
import argparse
import json
import shutil
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent

# 参赛包必须包含的代码与证据(config.json 含 Key,绝不入包)
CODE = [
    'problems.py', 'mcp_tools.py', 'logger.py', 'batch_agh.py', 'batch_eval.py',
    'direct_ask.py', 'analyze.py', 'score_batch.py', 'inspect_baseline.py',
    'reviewed_answers.json', 'rk4_experiment.py', 'rk4_out.json',
    'restart_agh.py', 'test_agnes.py', 'export_agh_trace.py', 'probe_models.py',
    'make_submission.py', 'README.md',
]
EVIDENCE_DIRS = ['batch_out', 'runs']


def mask_config():
    """config.json -> config.example.json, redact the API Key."""
    cfg = json.loads((ROOT / 'config.json').read_text(encoding='utf-8-sig'))
    for key in ('api_key', 'apikey', 'key', 'token'):
        if key in cfg:
            cfg[key] = '<你的-API-Key>'
    return json.dumps(cfg, ensure_ascii=False, indent=2)


def build(dry_run, extra, dest):
    staged = []
    for name in CODE:
        path = ROOT / name
        if not path.is_file():
            print(f'[WARN] missing: {name}')
            continue
        staged.append(path)
    for d in EVIDENCE_DIRS:
        for p in sorted((ROOT / d).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                staged.append(p)
    for item in extra:
        p = Path(item)
        if not p.is_file():
            print(f'[WARN] missing extra: {item}')
            continue
        staged.append(p)

    total = sum(p.stat().st_size for p in staged)
    n = len(staged)
    print(f'{n} files, {total/1024/1024:.2f} MB staged')
    biggest = sorted(staged, key=lambda p: -p.stat().st_size)[:5]
    for p in biggest:
        print(f'  {p.stat().st_size/1024/1024:7.2f} MB  {p.relative_to(ROOT) if str(p).startswith(str(ROOT)) else p}')
    if total > 200 * 1024 * 1024:
        print('[FAIL] >200MB, trim extras')
        return 1
    if dry_run:
        print('[DRY-RUN] not writing zip')
        return 0

    dest = Path(dest)
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
        for p in staged:
            arcname = str(p.relative_to(ROOT)) if str(p).startswith(str(ROOT)) else p.name
            zf.write(p, arcname)
        zf.writestr('config.example.json', mask_config())
    print(f'[OK] {dest}  ({dest.stat().st_size/1024/1024:.2f} MB)')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extra', nargs='*', default=[],
                        help='extra files to add (docs / declaration / demo video)')
    parser.add_argument('--dest', default=str(ROOT.parent / f'SymCheck-提交包-{date.today():%Y%m%d}.zip'))
    parser.add_argument('--write', action='store_true', help='actually write the zip (default dry-run)')
    args = parser.parse_args()
    return build(dry_run=not args.write, extra=args.extra, dest=args.dest)


if __name__ == '__main__':
    raise SystemExit(main())
