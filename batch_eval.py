# -*- coding: utf-8 -*-
"""
batch_eval.py — SymBench-15 跑批驱动(队长 · 系统集成线)

两个用途:
  阶段1(工具级): 不经过模型, 直接把每题喂给 sympy_solve + scipy_verify,
                 检查 mcp_tools 对 15 题的覆盖情况。用法: python -I batch_eval.py
  阶段2(端到端): 驱动 AGH 让模型读题→调工具→报告, 逐题记录证据(后续接入)。

输出: 每题一行 solve 状态 / verify 结论 / 误差; 最后汇总统计。
"""
import sys

import sympy as sp

sys.path.insert(0, r"C:\Users\TEMP\Desktop\hackathon")
import problems  # noqa: E402
from mcp_tools import sympy_solve, scipy_verify  # noqa: E402


def _ics_to_strdict(p) -> dict | None:
    """把 problems.py 的 SymPy 初值字典转成工具约定的 {"x0","y0","y1"}。"""
    if "ics" not in p:
        return None
    ic = {}
    for k, v in p["ics"].items():
        if isinstance(k, sp.Subs):                      # y'(x0)=v → Subs(Derivative(y(t),t),(t,),(x0,))
            ic["x0"] = float(k.args[2][0])
            ic["y1"] = float(v)
        elif k.func.__name__ == "y" and k.args:         # y(x0)=v
            ic["x0"] = float(k.args[0])
            ic["y0"] = float(v)
    return ic or None


def _bounds_of(expr_obj) -> list[float] | None:
    e = sp.sympify(expr_obj)
    lim = e.args[1] if isinstance(e, sp.Integral) else None
    if isinstance(lim, (tuple, sp.Tuple)) and len(lim) == 3:   # 定积分: (x, a, b)
        return [float(lim[1]), float(lim[2])]
    return None


def run_one(p) -> dict:
    kind, st = p["category"], p["statement"]
    expr_str = str(p["expr"])
    strategy = None
    if kind == "linear_algebra":
        if "特征" in st:
            strategy = "eigen"
        elif "行列式" in st:
            strategy = "det"
    bounds = _bounds_of(p["expr"]) if kind == "calculus" else None
    ic = _ics_to_strdict(p) if kind == "ode" else None
    r1 = sympy_solve(st, kind, expr_str, p["vars"], strategy, ic)
    if r1["status"] != "solved":
        return {"id": p["id"], "solve": r1["status"], "solve_err": r1["error"],
                "verify": "-", "max_error": None, "verify_err": None}
    v = scipy_verify(st, kind, expr_str, r1["symbolic_result"], p["vars"],
                     threshold=p["threshold"], error_type="absolute",
                     bounds=bounds, ic=ic)
    return {"id": p["id"], "solve": r1["status"], "solve_err": None,
            "verify": v.get("verdict"), "max_error": v.get("max_error"),
            "verify_err": v.get("error")}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{'id':<20}{'solve':<9}{'verify':<8}{'max_error':<14}备注")
    n_ok = 0
    for p in problems.SYMBENCH15:
        r = run_one(p)
        me = "" if r["max_error"] is None else f"{r['max_error']:.2e}"
        note = r["solve_err"] or r["verify_err"] or ""
        if r["solve"] == "solved" and r["verify"] == "PASS":
            n_ok += 1
        print(f"{r['id']:<20}{r['solve']:<9}{str(r['verify']):<8}{me:<14}{note}")
    print(f"\n== 端到端通过: {n_ok}/15 ==")


if __name__ == "__main__":
    main()
