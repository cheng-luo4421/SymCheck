# -*- coding: utf-8 -*-
"""
batch_agh.py — AGH 端到端批量评测驱动(队长 · 系统集成线)

对 SymBench-15 逐题启动 AGH 会话: 模型读题 → 调 sympy_solve_tool → scipy_verify_tool →
(失败换策略 ≤3 轮) → 中文报告。
每题输出存 batch_out/{id}.txt, 证据在 runs/ 里每题一个 JSONL(按题目切片),
run_id ↔ 题目 映射存 batch_out/summary.json。

用法: python -I batch_agh.py [--start N] [--only <id>] [--include-bonus]
      --start N        从第 N 题续跑(0-based)
      --only id        只重跑指定一题, 结果合并进现有 summary.json
      --include-bonus  15 题之外追加 RK4 加分题(冻结夜全量用)
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import problems  # noqa: E402

NODE = r"D:\KS\node.exe"
AGH = r"C:\Users\TEMP\Desktop\agnes-harness\agnes-harness-main\packages\cli\dist\local\agnes.mjs"
RUNS = HERE / "runs"
OUT_DIR = HERE / "batch_out"
TIMEOUT_S = 300
# AGH 会话 key 由工作区目录哈希派生。已出现三次"工具调用已落库但 turn/end 永不送达"
# (守护进程被强杀/行进程被 kill 后, 该工作区的会话游标在 sessions.db 里坏掉, 重启也无法修复)。
# 中招就给一个新目录名 = 全新会话, 旧会话留在库里不影响新会话。
# 注意: 杀 MCP 行 python 热重载工具代码 = 当前工作区会话必死, 重载后必须换目录+冷启动。
# 冻结夜可 SYMCHECK_WS=.agh_ws4 python -I batch_agh.py 换新工作区(免改代码)
WS_DIR = HERE / os.environ.get("SYMCHECK_WS", ".agh_ws3")

_TEMPLATE = (
    "你是 SymCheck 数学求解智能体。题目: {statement}\n"
    "严格按闭环流程执行:\n"
    "1) 调用 sympy_solve_tool 求符号解(按工具说明构造 kind 与 expr;{hint})\n"
    "2) 调用 scipy_verify_tool 对符号解做数值独立验证(threshold 用 {threshold}, "
    "error_type 用 'absolute');\n"
    "3) 若 verdict 为 FAIL 或工具报错, 调用 strategy_switch_tool 换策略重试, 最多 3 轮;\n"
    "4) 若工具返回 MANUAL, 在报告中如实说明无法自动验证;\n"
    "5) 最后用中文输出最终报告: 符号解、verdict、max_error、重试次数。"
)

_HINTS = {
    "calculus": "不定积分/定积分/极限必须分别用 Integral/Limit 包装 expr, 裸表达式会被拒; "
                "极限题 sympy_solve 与 scipy_verify 的 expr 都要用 Limit(f, x, x0) 包装; "
                "定积分题两个工具的 expr 都要写成带积分限的 Integral(f, (x, a, b)), "
                "并同时给 bounds=[a,b]",
    "linear_algebra": "矩阵题按工具说明选 strategy('eigen' 特征值 / 'det' 行列式 / 缺省求逆), "
                      "方程组用 Eq 列表形式",
    "ode": "有初值条件(IVP)时 sympy_solve 与 scipy_verify 都要把初值放 ics 参数"
           "(如 {'x0':0,'y0':1} 或 {'x0':0,'y0':1,'y1':0}), 漏传会被按通解初值组验证而 FAIL",
}

# rk4-bonus 附加提示: 除闭环外还要验证 RK4 收敛阶(第 4 工具)
_BONUS_HINT = ("本题还要验证 RK4 收敛阶: 在 scipy_verify 通过后调用 rk4_convergence_tool, "
               "kind='ode', expr 传原方程, symbolic_result 传解析解, vars=['t'], "
               "ics={'x0':0,'y0':1}, t_end=1; 把它的 verdict、observed_order、"
               "min_error 一并写进最终报告")


def newest_run_after(t0: float, statement: str | None = None) -> Path | None:
    """返回 t0 之后新建的 run 文件(题目切片: 每题第一次工具调用会开新文件)。
    statement 给定时只认工具调用参数里带该题面的文件——防止跑批期间本地
    selftest/batch_eval 恰好写入(其题面可能与某题相同)导致误记成绩
    (曾把 selftest 第 9 题的 sin(2t) FAIL 误判到 linear-algebra-03 头上)。"""
    cands = [p for p in RUNS.glob("run-*.jsonl") if p.stat().st_mtime >= t0]
    if statement is not None:
        hits = []
        for p in cands:
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
                if any(json.loads(ln).get("args", [None])[0] == statement
                       for ln in lines):
                    hits.append(p)
            except (json.JSONDecodeError, OSError):
                continue
        cands = hits or cands
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def grade_run(run_file: Path | None) -> tuple[str, str, int]:
    """最终判定 = 最后一个 verify 事件(FAIL→换策略→PASS 是闭环的正常路径);
    重试次数 = FAIL verify 事件数。无证据 → '-'。"""
    if run_file is None:
        return "-", "", 0
    verdicts = []
    for line in run_file.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event") == "verify":
            verdicts.append(ev.get("verdict"))
    run_id = run_file.stem
    if not verdicts:
        return "-", run_id, 0
    return verdicts[-1], run_id, sum(1 for v in verdicts if v == "FAIL")


def run_one(p) -> dict:
    hint = _HINTS[p["category"]]
    if p["id"] == "rk4-bonus":
        hint += "。" + _BONUS_HINT
    prompt = _TEMPLATE.format(statement=p["statement"],
                              hint=hint,
                              threshold=p["threshold"])
    out_txt = OUT_DIR / f"{p['id']}.txt"
    t0 = time.time()
    try:
        # --cwd 指向 .agh_ws 专用工作区(见 WS_DIR 注释): 会话 key 由工作区哈希派生,
        # 中招坏游标时换目录即换全新会话, 不用动 DB。
        r = subprocess.run([NODE, AGH, "-p", prompt, "--cwd", str(WS_DIR)],
                           capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=TIMEOUT_S)
        stdout = r.stdout
        out_txt.write_text(r.stdout + r.stderr, encoding="utf-8")
        rc = r.returncode
    except subprocess.TimeoutExpired:
        stdout = ""
        out_txt.write_text("TIMEOUT >300s", encoding="utf-8")
        rc = "timeout"
    grade, run_id, retries = grade_run(newest_run_after(t0, p["statement"]))
    return {"id": p["id"], "category": p["category"], "rc": rc,
            "grade": grade, "run_id": run_id, "retries": retries,
            "has_report": "最终报告" in stdout or "闭环求解报告" in stdout}


def _load_prev_rows() -> list[dict]:
    sf = OUT_DIR / "summary.json"
    try:
        return json.loads(sf.read_text(encoding="utf-8")).get("rows", [])
    except (json.JSONDecodeError, OSError, AttributeError):
        return []


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(exist_ok=True)
    WS_DIR.mkdir(exist_ok=True)
    all_probs = problems.SYMBENCH15 + [problems.RK4_BONUS]
    probs = all_probs if "--include-bonus" in sys.argv else problems.SYMBENCH15
    start = 0
    if "--start" in sys.argv:
        start = int(sys.argv[sys.argv.index("--start") + 1])
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    if only:
        probs = [p for p in all_probs if p["id"] == only]
        if not probs:
            sys.exit(f"未知题目 id: {only}")
    else:
        probs = probs[start:]
    rows = []
    print(f"{'id':<20}{'grade':<7}{'rc':<9}{'retries':<8}run_id")
    for p in probs:
        row = run_one(p)
        rows.append(row)
        print(f"{row['id']:<20}{row['grade']:<7}{str(row['rc']):<9}"
              f"{str(row['retries']):<8}{row['run_id']}")
    if only:                                            # 合并: 只替换重跑的那一行
        by_id = {r["id"]: r for r in _load_prev_rows()}
        by_id.update({r["id"]: r for r in rows})
        final_rows = [by_id[p["id"]] for p in all_probs if p["id"] in by_id]
    else:
        final_rows = rows
    summary = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "rows": final_rows,
               "passed": sum(1 for r in final_rows if r["grade"] == "PASS")}
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n== 通过 {summary['passed']}/{len(final_rows)} ==(summary.json 已存)")


if __name__ == "__main__":
    main()
