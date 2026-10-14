# -*- coding: utf-8 -*-
"""
hackathon/mcp_tools.py
SymCheck 数学工具 MCP 服务器 v0.4.0 (10-10 午, 新增第 4 工具 rk4_convergence)

通过 stdio 与 AGH 连接。AGH 中的 Agnes 模型可调用 4 个工具:
  sympy_solve       符号求解 (SymPy)
  scipy_verify      数值独立验证 (SciPy/NumPy), 与符号解交叉比对
  strategy_switch   失败换策略 (策略库白名单, 驱动 ≤3 轮重试)
  rk4_convergence   RK4 收敛阶验证 (独立实现, 加分题第二道交叉验证)

每个工具挂 @tool_logged, 调用证据写入 runs/ JSONL (logger.py 7 类事件体系)。
覆盖: 微积分(不定/定积分/极限)、线性代数(方程组/求逆/行列式/特征对)、
ODE(通解/初值问题) + RK4 收敛阶。未覆盖的组合返回 MANUAL。

单独调试:
  python -I mcp_tools.py --selftest   # 不走 MCP, 直接跑一遍四个工具自测
"""
import re
import sys
import time

import numpy as np
import sympy as sp
from scipy import integrate
from sympy.core.function import UndefinedFunction

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")
from logger import init_run, tool_logged, log_verify  # noqa: E402

# ---------------------------------------------------------------- 初始化
init_run("mcp-math-tools", echo=False)   # 服务器启动即开一次运行, run_id 贯穿本次会话

mcp = MCPServer("symcheck-math-tools")

# 安全解析: sympify 只允许以下符号/函数, 防题目文本注入执行代码
_SAFE_FUNCS = {
    "exp": sp.exp, "log": sp.log, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "sqrt": sp.sqrt, "pi": sp.pi, "E": sp.E, "Abs": sp.Abs,
    "Integral": sp.Integral, "Derivative": sp.Derivative, "Limit": sp.Limit,
    "Eq": sp.Eq, "Matrix": sp.Matrix,
}


def _parse(expr: str, vars: list[str], kind: str):
    """用安全 locals 把模型给的表达式解析成 SymPy 对象。"""
    if isinstance(vars, dict):            # 模型偶尔把列表序列化成 {"value": [...], "Count": n}
        vars = vars.get("value") or []
    locals_ = dict(_SAFE_FUNCS)
    locals_["x"], locals_["t"] = sp.Symbol("x"), sp.Symbol("t")   # 自变量兜底
    for c in ("C1", "C2", "C3", "C4"):                            # dsolve 通解常数, 回读用
        locals_[c] = sp.Symbol(c)
    if kind != "ode":
        for v in vars:
            locals_[v] = sp.Symbol(v)   # ODE 的变量/函数名全部交给 sympify 自动推断
    try:
        return sp.sympify(expr, locals=locals_)
    except Exception as exc:
        # 模型手抄表达式常漏右括号(如特征向量列表), 尝试补齐后重试:
        # 漏的括号可能在串尾, 也可能在结尾的 ']' 之前
        for k in range(1, 5):
            for cand in (expr + ")" * k, expr[:-1] + ")" * k + expr[-1:]):
                try:
                    return sp.sympify(cand, locals=locals_)
                except Exception:
                    continue
        raise exc


def _ode_func(e):
    """从方程里取被解的函数(如 y(t) 的 y), 与 vars 传什么无关。
    atoms(Function) 会带上 sin/cos 等内置函数, 需过滤出 func 是 UndefinedFunction 的。"""
    fns = sorted({a.func for a in e.atoms(sp.Function)
                  if isinstance(a.func, UndefinedFunction)},
                 key=lambda f: f.__name__)
    return fns[0] if fns else None


def _now(t0: float) -> float:
    return round((time.time() - t0) * 1000, 1)


def _errors(got, ref, error_type):
    """逐点误差: relative 或 absolute, 除零处用 1e-12 兜底。"""
    got, ref = np.asarray(got, dtype=float), np.asarray(ref, dtype=float)
    if error_type == "relative":
        return np.abs(got - ref) / np.maximum(np.abs(ref), 1e-12)
    return np.abs(got - ref)

# ---------------------------------------------------------------- 运行切片
# MCP 行进程跨任务复用, 默认所有工具事件写进同一个 run 文件。
# 批量评测要求每题独立证据: 题目文本变化 → 新开 run 文件(同题重试仍共用)。
_ACTIVE_PROBLEM = {"key": None}


def _rotate_run(problem: str):
    key = problem.strip()[:64]
    if _ACTIVE_PROBLEM["key"] != key:
        _ACTIVE_PROBLEM["key"] = key
        init_run("mcp-math-tools", echo=False)


def _ic_from_statement(problem: str) -> dict | None:
    """从题面文本解析初值(如 'y(0)=1, y'(0)=0'), 模型漏传 ic 时的兜底。

    只解析 y(x0)=y0; 仅当同 x0 处还有 y'(x0)=y1 时才含 y1, 避免跨点误配。
    """
    m = re.search(r"y\s*\(\s*([-+\d.eE]+)\s*\)\s*=\s*([-+\d.eE]+)", problem)
    if not m:
        return None
    ic = {"x0": float(m.group(1)), "y0": float(m.group(2))}
    m2 = re.search(r"y\s*['′]\s*\(\s*([-+\d.eE]+)\s*\)\s*=\s*([-+\d.eE]+)", problem)
    if m2 and float(m2.group(1)) == ic["x0"]:
        ic["y1"] = float(m2.group(2))
    return ic


# ---------------------------------------------------------------- 工具 1: sympy_solve

@tool_logged
def sympy_solve(problem: str, kind: str, expr: str, vars: list[str],
                strategy: str | None = None, ics: dict | None = None) -> dict:
    """符号求解。expr 是模型读题后整理的 SymPy 表达式(带 Integral/Derivative/Eq 等包装)。"""
    _rotate_run(problem)
    t0 = time.time()
    try:
        e = _parse(expr, vars, kind)
    except Exception as exc:
        return {"status": "bad_input", "symbolic_result": None, "steps": [],
                "error": f"表达式解析失败: {exc}", "duration_ms": _now(t0)}

    steps = []
    try:
        if kind == "calculus":
            steps.append(f"解析为: {e}")
            if isinstance(e, (sp.Integral, sp.Derivative, sp.Limit)):
                result = e.doit()
            else:                                     # 裸表达式按不定积分处理
                x = sp.Symbol(vars[0])
                result = sp.integrate(e, x)
                steps.append(f"按不定积分 ∫({e}) d{vars[0]} 计算")
        elif kind == "linear_algebra":
            op = (strategy or "").lower()
            if isinstance(e, (list, tuple)) and e and all(isinstance(q, sp.Eq) for q in e):
                steps.append(f"解析为方程组: {e}")             # 方程组: [Eq(...), Eq(...)]
                result = sp.linsolve(list(e), [sp.Symbol(v) for v in vars])
                if len(result) == 1:
                    result = next(iter(result))               # 唯一解: 有限解集 → 元组
            elif isinstance(e, (list, tuple)):
                e = sp.Matrix(e)                              # 裸列表字面量 → 矩阵
            else:
                if not isinstance(e, sp.MatrixBase):
                    return {"status": "bad_input", "symbolic_result": None, "steps": steps,
                            "error": "linear_algebra 题目需传方程组列表或 Matrix(...) 表达式",
                            "duration_ms": _now(t0)}
                steps.append(f"解析为矩阵: {e}")
                if "eigen" in op:
                    result = [(lam, vs[0].normalized())
                              for lam, _m, vs in e.eigenvects()]   # [(λ, 单位向量), ...]
                elif "det" in op:
                    result = e.det()
                else:                                     # 默认求逆
                    result = e.inv()
        elif kind == "ode":
            steps.append(f"解析为方程: {e}")
            f = _ode_func(e)
            if f is None:
                return {"status": "bad_input", "symbolic_result": None, "steps": steps,
                        "error": "方程中没有未知函数(如 y(t))", "duration_ms": _now(t0)}
            indeps = sorted(e.free_symbols, key=str)          # 方程里的自变量
            if not indeps:
                return {"status": "bad_input", "symbolic_result": None, "steps": steps,
                        "error": "方程中没有自变量", "duration_ms": _now(t0)}
            ics_sym = None
            if ics:                                           # {"x0","y0"[, "y1"]} → SymPy 初值字典
                x_sym = indeps[0]
                ics_sym = {f(x_sym).subs(x_sym, ics["x0"]): ics["y0"]}
                if "y1" in ics:
                    ics_sym[sp.Derivative(f(x_sym), x_sym).subs(x_sym, ics["x0"])] = ics["y1"]
            result = sp.dsolve(e, f(indeps[0]), ics=ics_sym)
        else:
            return {"status": "bad_input", "symbolic_result": None, "steps": steps,
                    "error": f"未知 kind: {kind}", "duration_ms": _now(t0)}
        return {"status": "solved", "symbolic_result": str(result), "steps": steps,
                "error": None, "sympy_version": sp.__version__, "duration_ms": _now(t0)}
    except Exception as exc:
        return {"status": "failed", "symbolic_result": None, "steps": steps,
                "error": f"{type(exc).__name__}: {exc}", "duration_ms": _now(t0)}

# ---------------------------------------------------------------- 工具 2: scipy_verify

@tool_logged
def scipy_verify(problem: str, kind: str, expr: str, symbolic_result: str,
                 vars: list[str], threshold: float = 1e-6,
                 error_type: str = "absolute", n_points: int = 8,
                 bounds: list[float] | None = None,
                 ic: dict | None = None) -> dict:
    """数值独立验证: 用 SciPy 独立计算参考解, 与符号解比对, max_error<=threshold 判 PASS。
    error_type 默认 'absolute'(题库统一口径: 绝对误差), 可选 'relative'。"""
    _rotate_run(problem)
    t0 = time.time()

    def finish(**kw) -> dict:
        kw.update({"status": kw.get("status", "done"), "verify_method": "scipy",
                   "threshold": threshold, "error_type": error_type, "duration_ms": _now(t0)})
        return kw

    def judged(got, ref, label, et=None):
        et = et or error_type
        errs = _errors(got, ref, et)
        max_err = float(np.max(errs))
        verdict = "PASS" if max_err <= threshold else "FAIL"
        log_verify(f"{label} 最大{'绝对' if et == 'absolute' else '相对'}误差",
                   value=max_err, threshold=threshold, op="le", verdict=verdict)
        return {"numeric_reference": np.asarray(ref, dtype=float).tolist(),
                "errors": np.asarray(errs, dtype=float).tolist(),
                "max_error": max_err, "verdict": verdict}

    try:
        e = _parse(expr, vars, kind)
        s = _parse(symbolic_result, vars, kind)
    except Exception as exc:
        return finish(status="bad_input", verdict="MANUAL", error=f"解析失败: {exc}")

    try:
        # ================= 微积分
        if kind == "calculus":
            # 防护: 常数符号结果必须配"定积分(带积分限)/极限"形式的 expr, 否则口径错配
            # (裸表达式/丢积分限的 Integral + 常数结果 = 极限/定积分被模型漏包装时的典型错误)
            definite = (isinstance(e, sp.Integral)
                        and isinstance(e.args[1], (tuple, sp.Tuple))
                        and len(e.args[1]) == 3)
            if s.is_number and not definite and not isinstance(e, sp.Limit):
                return finish(verdict="MANUAL", error=(
                    "expr 与常数 symbolic_result 口径不匹配: 若是定积分请把 expr 写成 "
                    "Integral(f, (x, a, b))(必须带积分限); "
                    "若是极限请把 expr 写成 Limit(f, x, x0) 后重试"))

            # 极限: 双侧数值逼近 + Richardson 外推(与符号求极限完全独立的方法)
            if isinstance(e, sp.Limit):
                x, x0 = e.args[1], e.args[2]
                fn = sp.lambdify(x, e.args[0], "numpy")
                target = float(sp.N(s))
                ests = []
                for h in (1e-3, 1e-4):      # 更小的 h 会被浮点消去误差淹没(≈1e-6 噪声)
                    for sgn in (+1, -1):
                        try:
                            v2 = fn(float(x0) + sgn * h)
                            v1 = fn(float(x0) + sgn * h / 2)
                            ests.append(2 * v1 - v2)       # Richardson: L ≈ 2·f(h/2) − f(h)
                        except Exception:
                            pass                           # 单侧无定义(如 log)时跳过该侧
                ests = np.asarray(ests, dtype=float)
                ests = ests[np.isfinite(ests)]
                if len(ests) == 0:
                    return finish(verdict="MANUAL", error="极限数值逼近失败(函数在邻域无定义)")
                return finish(**judged(np.full(len(ests), target), ests,
                                       f"极限 {e} 符号 vs 数值外推"))

            # 定积分: Integral(f, (x, a, b)) —— args[1] 是长度 3 的 Tuple
            if (isinstance(e, sp.Integral) and isinstance(e.args[1], (tuple, sp.Tuple))
                    and len(e.args[1]) == 3):
                if not bounds:
                    return finish(verdict="MANUAL", error="定积分验证需 bounds=[a,b]")
                a, b = float(bounds[0]), float(bounds[1])
                x = e.args[1][0]
                f = sp.lambdify(x, e.args[0], "numpy")
                ref = integrate.quad(f, a, b, epsabs=1e-11, epsrel=1e-11)[0]
                got = float(sp.N(s))
                return finish(**judged([got], [ref], f"定积分 ∫_{a}^{b} 符号 vs 数值"))

            # 不定积分: 裸表达式或 Integral(f, x) → 符号反导数增量 vs 数值积分
            # 注: 不定积分的 args[1] 是 Tuple(x), 自变量取 [0]
            x = e.args[1][0] if isinstance(e, sp.Integral) else (
                sp.Symbol(vars[0]) if vars else sorted(e.free_symbols, key=str)[0])
            f_expr = e.args[0] if isinstance(e, sp.Integral) else e
            sym_expr = s.rhs if isinstance(s, sp.Eq) else s
            f = sp.lambdify(x, f_expr, "numpy")
            F = sp.lambdify(x, sym_expr, "numpy")
            xs = np.linspace(0.1, 2.0, n_points)
            got = F(xs) - F(xs[0])                                   # 符号反导数的增量
            ref = np.array([integrate.quad(f, xs[0], xi, epsabs=1e-11, epsrel=1e-11)[0]
                            for xi in xs])
            return finish(**judged(got, ref, f"∫({f_expr})d{x} 符号 vs 数值积分"))

        # ================= 线性代数
        if kind == "linear_algebra":
            # 方程组: [Eq(...), ...] → 系数矩阵, numpy 独立求解对照
            if isinstance(e, (list, tuple)) and e and all(isinstance(q, sp.Eq) for q in e):
                syms = [sp.Symbol(v) for v in vars]
                A_rows, b_rows = [], []
                for eq in e:
                    A_rows.append([float(eq.lhs.coeff(sym)) for sym in syms])
                    b_rows.append(float(sp.N(eq.rhs)))
                ref = np.linalg.solve(np.array(A_rows), np.array(b_rows))
                if isinstance(s, sp.MatrixBase):
                    got = np.asarray(s.tolist(), dtype=float).ravel()
                elif isinstance(s, (tuple, list)):
                    got = np.array([float(sp.N(v)) for v in s])
                else:
                    return finish(verdict="MANUAL", error=f"无法解析解向量: {s}")
                return finish(**judged(got, ref, "方程组 符号 vs 数值求解"))

            if isinstance(e, (list, tuple)):
                # 模型把矩阵写成裸列表字面量(漏 Matrix 包装), 转回矩阵
                try:
                    e = sp.Matrix(e)
                except Exception:
                    return finish(verdict="MANUAL", error=(
                        "线性代数验证需 Matrix 或 Eq 列表: 矩阵请写成 "
                        "Matrix([[...],[...]]), 方程组请写成 [Eq(...), Eq(...)]"))

            if not isinstance(e, sp.MatrixBase):
                return finish(verdict="MANUAL", error="线性代数验证需 Matrix 或方程组")

            # 特征对: 对每个 (λ, v) 检查 ‖A·v − λ·v‖∞ 残差(与符号法独立的数值判定)
            if isinstance(s, (list, tuple)) and s and isinstance(s[0], (tuple, list)):
                M = np.array(e.tolist(), dtype=float)
                n = M.shape[0]
                lams = [round(float(sp.N(lam)), 8) for lam, _v in s]
                if len(lams) != n or len(set(lams)) != n:
                    # 判定标准要求"n 阶矩阵给出 n 个互异特征值及非零向量", 缺一不可
                    return finish(verdict="FAIL", error=(
                        f"特征对不完整: {n} 阶矩阵应给出 {n} 个互异特征值及对应特征向量, "
                        f"实际 {len(lams)} 个({lams})"))
                errs = []
                for lam, vv in s:
                    lamf = float(sp.N(lam))
                    v = np.asarray([float(sp.N(c)) for c in vv], dtype=float).ravel()
                    errs.append(np.max(np.abs(M @ v - lamf * v)) / max(np.abs(v).max(), 1e-12))
                errs = np.asarray(errs, dtype=float)
                return finish(**judged(errs, np.zeros_like(errs),
                                       "特征对 A·v≈λ·v 残差", et="absolute"))

            # 逆矩阵 / 行列式
            M = np.array(e.tolist(), dtype=float)
            if isinstance(s, sp.MatrixBase):
                got = np.array(s.tolist(), dtype=float)
                ref = np.linalg.inv(M) if got.shape == M.shape else np.linalg.det(M)
            else:                                                    # 标量结果按行列式对照
                got = np.array([float(sp.N(s))])
                ref = np.array([np.linalg.det(M)])
            return finish(**judged(got, ref, "线性代数 符号 vs 数值"))

        # ================= ODE
        if kind == "ode":
            x = sorted(e.free_symbols, key=str)[0]        # 方程实际的自变量
            f = _ode_func(e)
            sym_expr = s.rhs if isinstance(s, sp.Eq) else s
            f_expr = sp.expand(e.lhs - e.rhs)
            d1, d2 = sp.diff(f(x), x), sp.diff(f(x), x, 2)
            order = 2 if f_expr.has(d2) else 1
            target = d2 if order == 2 else d1
            g_list = sp.solve(f_expr, target)             # 解出最高阶导数
            if not g_list:
                return finish(verdict="MANUAL", error="无法把方程解为 y''=g(x,y,y') 形式")
            if order == 2:
                g_fn = sp.lambdify((x, f(x), d1), g_list[0], "numpy")
                def rhs(t, yv):
                    return [yv[1], float(g_fn(t, yv[0], yv[1]))]
            else:
                g_fn = sp.lambdify((x, f(x)), g_list[0], "numpy")
                def rhs(t, yv):
                    return [float(g_fn(t, yv[0]))]
            # 通解无初值: 按判定标准用初值组验证解族——一阶 y(0)=0/1/-1(零解不可漏),
            # 二阶 (y(0),y'(0))=(1,0)/(0,1)/(1,-1)。能抓出漏写任意常数的不完整答案。
            C = sorted(sym_expr.free_symbols - {x}, key=str)   # 通解常数, 由各组初值确定
            text_ic = None
            if not ic and not C:
                text_ic = _ic_from_statement(problem)  # 模型漏传 ic 时从题面兜底解析初值
            if ic:
                groups = [ic]
            elif text_ic:
                groups = [text_ic]
            elif order == 1:
                groups = [{"x0": 0.0, "y0": v} for v in (0.0, 1.0, -1.0)]
            else:
                groups = [{"x0": 0.0, "y0": a, "y1": b}
                          for a, b in ((1.0, 0.0), (0.0, 1.0), (1.0, -1.0))]
            err_list = []
            for g in groups:
                x0 = float(g["x0"])
                y0v = float(g.get("y0", 1.0))
                eqs = [sp.Eq(sym_expr.subs(x, x0), y0v)]
                if order == 2:
                    eqs.append(sp.Eq(sp.diff(sym_expr, x).subs(x, x0),
                                     float(g.get("y1", 1.0))))
                consts = sp.solve(eqs, C, dict=True) if C else [{}]
                if not consts:
                    return finish(verdict="MANUAL", error=f"初值组 {g} 无法确定通解常数")
                y_sym = sp.lambdify(x, sym_expr.subs(consts[0]), "numpy")
                xs = np.linspace(x0, x0 + 2.0, n_points)
                sol = integrate.solve_ivp(rhs, [xs[0], xs[-1]],
                                          [y0v] + ([float(g.get("y1", 1.0))]
                                                   if order == 2 else []),
                                          t_eval=xs, rtol=1e-10, atol=1e-12)
                if not sol.success:
                    return finish(verdict="MANUAL", error=f"数值求解未收敛({g}): {sol.message}")
                err_list.append(_errors(y_sym(xs), sol.y[0], error_type))
            errs = np.concatenate(err_list)
            max_err = float(np.max(errs))
            verdict = "PASS" if max_err <= threshold else "FAIL"
            label = ("ODE 数值解(RK45) vs 符号解(指定初值)" if ic
                     else "ODE 数值解(RK45) vs 符号解(题面解析初值)" if text_ic
                     else "ODE 数值解(RK45) vs 符号解(通解初值组)")
            log_verify(f"{label} 最大{'绝对' if error_type == 'absolute' else '相对'}误差",
                       value=max_err, threshold=threshold, op="le", verdict=verdict)
            hint = None
            if not ic and not text_ic and not C and verdict == "FAIL":
                hint = ("符号解不含任意常数且未提供 ic: 若是初值问题, 请把初值放到 "
                        "ic 参数(如 {'x0':0,'y0':1,'y1':0})后重试; 若题目要求通解, 此答案不完整")
            return finish(verdict=verdict, max_error=max_err,
                          errors=errs.tolist(), numeric_reference=None, error=hint,
                          ic_source="call" if ic else "statement" if text_ic else "multi")

        return finish(verdict="MANUAL", error=f"kind={kind} 的数值验证未实现(v0.2 范围)")
    except Exception as exc:
        return finish(status="failed", verdict="MANUAL",
                      error=f"{type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- 工具 3: strategy_switch

_STRATEGIES = {
    "calculus":      ["direct_integration", "integration_hints", "numerical_fit"],
    "linear_algebra": ["direct_solve", "simplify_nullspace", "numeric_guided"],
    "ode":           ["dsolve_direct", "laplace_transform", "power_series"],
}

_HINTS = {
    ("calculus", "integration_hints"): "尝试换元/分部积分, 把被积函数改写为更易积的形式再调 sympy_solve",
    ("calculus", "numerical_fit"): "先调 scipy_verify 拿数值参考, 再反推符号形式",
    ("linear_algebra", "simplify_nullspace"): "先化简矩阵(提取公因子/分块)再求逆",
    ("linear_algebra", "numeric_guided"): "用数值结果验证/引导符号化简方向",
    ("ode", "laplace_transform"): "对线性常系数方程改用 Laplace 变换求解",
    ("ode", "power_series"): "改用幂级数法展开近似解",
}

@tool_logged
def strategy_switch(kind: str, failed_tool: str, reason: str, attempt: int) -> dict:
    """失败换策略: 从策略库白名单取下一策略, 驱动 agent 重试(≤3 轮)。"""
    t0 = time.time()
    lib = _STRATEGIES.get(kind)
    if not lib:
        return {"new_strategy": None, "hints": f"未知 kind: {kind}", "strategies_left": 0,
                "give_up": True, "duration_ms": _now(t0)}
    idx = attempt - 1                                 # 第 attempt 次尝试用第 attempt 条
    if idx >= len(lib):
        return {"new_strategy": None, "hints": "策略库已耗尽(3 轮用尽)",
                "strategies_left": 0, "give_up": True, "duration_ms": _now(t0)}
    strategy = lib[idx]
    return {"new_strategy": strategy,
            "hints": _HINTS.get((kind, strategy), "按新策略重试"),
            "strategies_left": len(lib) - idx - 1,
            "give_up": False, "duration_ms": _now(t0)}

# ---------------------------------------------------------------- 工具 4: rk4_convergence

def _rk4_step_loop(rhs, t0, y0, h, t_end):
    """RK4 标准公式(独立实现, 刻意不与队友 rk4_experiment.py 共享代码, 保持双方法互验)。"""
    y, t = float(y0), float(t0)
    while t < t_end - h / 2:                       # 步长不被区间整除时最后一步按剩余长度走
        hh = min(h, t_end - t)
        k1 = rhs(t, y)
        k2 = rhs(t + hh / 2, y + hh * k1 / 2)
        k3 = rhs(t + hh / 2, y + hh * k2 / 2)
        k4 = rhs(t + hh, y + hh * k3)
        y = y + hh * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        t = t + hh
    return y


@tool_logged
def rk4_convergence(problem: str, kind: str, expr: str, symbolic_result: str,
                    vars: list[str], ics: dict | None = None,
                    t_end: float = 1.0, hs: list[float] | None = None) -> dict:
    """RK4 收敛阶验证: 独立实现 RK4 数值解, 与符号解在 t_end 处比对, 检查相邻步长
    误差比是否趋 2^4=16(观测阶趋 4)。符号解错误时误差不随步长缩小(误差比趋 1)→ FAIL,
    因此与 scipy_verify(solve_ivp) 构成第二种独立交叉验证。仅支持一阶 ODE。"""
    _rotate_run(problem)
    t0 = time.time()

    def finish(**kw) -> dict:
        kw.update({"status": kw.get("status", "done"), "method": "rk4",
                   "t_end": t_end, "duration_ms": _now(t0)})
        return kw

    if kind != "ode":
        return finish(status="bad_input", verdict="MANUAL",
                      error=f"rk4_convergence 仅支持 kind='ode', 收到 {kind}")
    try:
        e = _parse(expr, vars, kind)
        s = _parse(symbolic_result, vars, kind)
    except Exception as exc:
        return finish(status="bad_input", verdict="MANUAL", error=f"解析失败: {exc}")
    try:
        f = _ode_func(e)
        if f is None:
            raise ValueError("方程中没有未知函数(如 y(t))")
        indeps = sorted(e.free_symbols, key=str)
        if not indeps:
            raise ValueError("方程中没有自变量")
        x_sym, y_sym = indeps[0], f(indeps[0])
        eq_zero = e.lhs - e.rhs
        if any(d.derivative_count > 1 for d in eq_zero.atoms(sp.Derivative)):
            raise ValueError("仅支持一阶 ODE, 高阶请先化为一阶方程组")
        sol = sp.solve(eq_zero, sp.Derivative(y_sym, x_sym))
        if not sol:
            raise ValueError(f"无法把方程化为 y'=f(t,y) 的显式形式")
        rhs_expr = sol[0]
        unknown = rhs_expr.free_symbols - {x_sym}
        if unknown:
            raise ValueError(f"右端含未知量 {sorted(unknown, key=str)}, 无法数值化")
        if any(isinstance(a.func, UndefinedFunction) for a in s.atoms(sp.Function)
               if a.func not in (sp.exp, sp.log, sp.sin, sp.cos, sp.tan, sp.sqrt, sp.Abs)):
            raise ValueError("解析解含未定函数, 无法数值化")
        consts = sorted(a for a in s.free_symbols if str(a) in ("C1", "C2", "C3", "C4"))
        if consts:
            raise ValueError(f"解析解含未定常数 {consts}, 请先用初值确定解")
        if ics is None:
            ics = _ic_from_statement(problem)
        if ics is None:
            raise ValueError("缺少初值: 传 ics={'x0':0,'y0':1} 或确保题面含 y(0)=y0")
        rhs_np = sp.lambdify((x_sym, y_sym), rhs_expr, "numpy")
        analytic = sp.lambdify(x_sym, s, "numpy")
        x0, y0 = float(ics["x0"]), float(ics["y0"])
        y_exact = float(analytic(t_end))
        if not np.isfinite(y_exact):
            raise ValueError(f"解析解在 t_end={t_end} 处非有限值: {y_exact}")
        hs = list(hs) if hs else [0.1, 0.05, 0.025, 0.0125]
        hs = sorted({float(h) for h in hs}, reverse=True)
        if len(hs) < 2:
            raise ValueError("至少需要两档步长才能算收敛阶")
        results, steps = [], []
        for h in hs:
            y_h = _rk4_step_loop(rhs_np, x0, y0, h, t_end)
            e_h = abs(y_h - y_exact)
            results.append({"h": h, "y_h": y_h, "e_h": e_h})
            steps.append(f"h={h}: y({t_end})={y_h:.12g}, e(h)={e_h:.3e}")
        ratios = [results[i]["e_h"] / results[i + 1]["e_h"]
                  for i in range(len(results) - 1)]
        observed_order = float(np.mean(np.log2(ratios)))
        min_err = results[-1]["e_h"]
        verdict = ("PASS" if all(12 <= r <= 20 for r in ratios)
                   and min_err <= 1e-6 else "FAIL")
        log_verify("RK4 收敛阶交叉验证", value=observed_order, threshold=None,
                   verdict=verdict, ratios=ratios, min_error=min_err)
        return finish(status="solved", verdict=verdict, results=results, steps=steps,
                      ratios=ratios, observed_order=observed_order,
                      min_error=min_err, threshold=1e-6, error=None)
    except Exception as exc:
        return finish(status="failed", verdict="MANUAL",
                      error=f"{type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- MCP 注册
# 只读注解: AGH 把 readOnlyHint!=true 的 MCP 工具视为破坏性 → 要求人工审批,
# 非交互(批量评测)环境会直接拒绝。三个数学工具均为纯计算, 声明只读/幂等。
_RO_ANNOTATIONS = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                  idempotentHint=True, openWorldHint=False)

@mcp.tool(annotations=_RO_ANNOTATIONS)
def sympy_solve_tool(problem: str, kind: str, expr: str, vars: list[str],
                     strategy: str | None = None, ics: dict | None = None) -> dict:
    """符号求解(SymPy)。kind: calculus|linear_algebra|ode。
    calculus: expr 如 'Integral(x*exp(x), x)'(不定积分)、'Integral(sin(x), (x, 0, pi))'(定积分)、
      'Limit(sin(x)/x, x, 0)'(极限)。
    linear_algebra: 方程组传 '[Eq(2*u+v, 5), Eq(u-v, 1)]'(strategy 不填, vars 给未知量);
      矩阵题传 'Matrix([[1,2],[3,4]])', strategy='eigen' 求特征值特征向量 / 'det' 求行列式 / 不填求逆。
    ode: expr 如 'Eq(Derivative(y(t), t), t*y(t))', vars 给自变量; 初值问题加
      ics={'x0':0,'y0':1}(一阶) 或 {'x0':0,'y0':1,'y1':0}(二阶, y1 为一阶导初值)。"""
    return sympy_solve(problem, kind, expr, vars, strategy, ics)


@mcp.tool(annotations=_RO_ANNOTATIONS)
def scipy_verify_tool(problem: str, kind: str, expr: str, symbolic_result: str,
                      vars: list[str], threshold: float = 1e-6,
                      error_type: str = "absolute", n_points: int = 8,
                      bounds: list[float] | None = None, ic: dict | None = None) -> dict:
    """数值独立验证(SciPy): 用与符号求解完全不同的数值方法算参考解, 与符号解比对,
    max_error<=threshold 判 PASS。error_type 默认 'absolute'(题库统一口径: 绝对误差)。
    微积分: 不定积分/定积分(需 bounds=[a,b])/极限(需 Limit 包装, 自动 Richardson 外推);
    裸表达式+常数结果会被拒(MANUAL, 提示用 Integral/Limit 包装)。
    线性代数: 方程组/求逆/行列式/特征对(残差)。
    ODE: 与 solve_ivp(RK45) 对照; 无初值的通解用初值组验证(一阶 y(0)=0/1/-1,
    二阶 (1,0)/(0,1)/(1,-1)), 漏写任意常数会被判 FAIL。
    初值问题(题目给了初值)必须把初值放到 ic 参数; 若确实漏传且符号解不含常数,
    工具会从题面文本自动解析 y(0)=y0 / y'(0)=y1 兜底(结果含 ic_source 字段)。"""
    return scipy_verify(problem, kind, expr, symbolic_result, vars, threshold,
                        error_type, n_points, bounds, ic)


@mcp.tool(annotations=_RO_ANNOTATIONS)
def strategy_switch_tool(kind: str, failed_tool: str, reason: str, attempt: int) -> dict:
    """失败换策略: 从白名单策略库取下一策略。attempt 从 1 开始, 3 轮用尽返回 give_up=true。"""
    return strategy_switch(kind, failed_tool, reason, attempt)


@mcp.tool(annotations=_RO_ANNOTATIONS)
def rk4_convergence_tool(problem: str, kind: str, expr: str, symbolic_result: str,
                         vars: list[str], ics: dict | None = None,
                         t_end: float = 1.0, hs: list[float] | None = None) -> dict:
    """RK4 收敛阶验证(独立实现, 与 scipy_verify 构成第二种交叉验证)。仅支持一阶 ODE。
    expr 传原方程(如 'Eq(Derivative(y(t), t), -2*y(t) + t)'),
    symbolic_result 传 sympy_solve 得到的解析解(如 '(5*exp(-2*t) + 2*t - 1)/4'),
    vars 给自变量, ics 传 {'x0':0,'y0':1}(漏传会从题面文本解析 y(0)=y0 兜底),
    t_end 为比对终点(默认 1)。
    用四档步长 h=0.1/0.05/0.025/0.0125 的 RK4 数值解与解析解在 t_end 处比对,
    收敛阶为 4 时相邻步长误差比应趋 16。判 PASS: 三个误差比全在 [12,20] 且
    最细步长误差 <= 1e-6; 解析解错误时误差不随步长缩小(误差比趋 1)会被判 FAIL。"""
    return rk4_convergence(problem, kind, expr, symbolic_result, vars, ics, t_end, hs)


# ---------------------------------------------------------------- 自测(不走 MCP)

def _selftest():
    try:
        sys.stdout.reconfigure(encoding="utf-8")     # Windows 控制台避免 GBK 编码报错
    except Exception:
        pass
    print("== 自测 1: 不定积分 ∫ x·e^x dx ==")
    r1 = sympy_solve("计算不定积分 ∫ x·e^x dx", "calculus", "x*exp(x)", ["x"])
    print("  符号解:", r1["symbolic_result"], "|", r1["status"])
    v1 = scipy_verify("计算不定积分 ∫ x·e^x dx", "calculus", "x*exp(x)",
                      r1["symbolic_result"], ["x"])
    print("  数值验证:", v1["verdict"], "max_error =", v1.get("max_error"))

    print("== 自测 2: ODE y''+2y'+y=0, y(0)=1, y'(0)=0 ==")
    ode = "Eq(Derivative(y(x), x, 2) + 2*Derivative(y(x), x) + y(x), 0)"
    r2 = sympy_solve("求解 y''+2y'+y=0", "ode", ode, ["y"])
    print("  符号解:", r2["symbolic_result"], "|", r2["status"])
    v2 = scipy_verify("求解 y''+2y'+y=0", "ode", ode, r2["symbolic_result"], ["y"],
                      ic={"x0": 0, "y0": 1, "y1": 0})
    print("  数值验证:", v2["verdict"], "max_error =", v2.get("max_error"), "|", v2.get("error"))

    print("== 自测 3: 定积分 ∫_0^1 x² dx ==")
    r3 = sympy_solve("计算定积分", "calculus", "Integral(x**2, (x, 0, 1))", ["x"])
    print("  符号解:", r3["symbolic_result"], "|", r3["status"])
    v3 = scipy_verify("计算定积分", "calculus", "Integral(x**2, (x, 0, 1))",
                      r3["symbolic_result"], ["x"], bounds=[0, 1])
    print("  数值验证:", v3["verdict"], "max_error =", v3.get("max_error"))

    print("== 自测 4: 换策略 ==")
    s = strategy_switch("calculus", "sympy_solve", "Integral could not be solved", 1)
    print("  第 1 次:", s["new_strategy"], "| 剩余:", s["strategies_left"], "| give_up:", s["give_up"])
    s2 = strategy_switch("calculus", "sympy_solve", "still failed", 4)
    print("  第 4 次(超限):", "give_up =", s2["give_up"])

    print("== 自测 5: 口径错配防护(裸表达式 + 常数结果) ==")
    v5 = scipy_verify("计算极限", "calculus", "(exp(x)-1-x)/x**2", "1/2", ["x"])
    print("  裸表达式+常数:", v5["verdict"], "|", v5.get("error"))

    print("== 自测 6: ODE 通解初值组(漏写常数 C1 应 FAIL) ==")
    ode1 = "Eq(Derivative(y(t), t), t*y(t))"
    v6a = scipy_verify("求通解 y'=t·y", "ode", ode1, "C1*exp(t**2/2)", ["t"])
    print("  完整通解:", v6a["verdict"], "max_error =", v6a.get("max_error"))
    v6b = scipy_verify("求通解 y'=t·y", "ode", ode1, "exp(t**2/2)", ["t"])
    print("  漏常数:", v6b["verdict"], "max_error =", v6b.get("max_error"))

    print("== 自测 7: 定积分丢积分限(Integral(f, x) + 常数)应 MANUAL ==")
    v7 = scipy_verify("计算定积分 ∫₀¹ x·exp(x) dx", "calculus",
                      "Integral(x*exp(x), x)", "1", ["x"], bounds=[0, 1])
    print("  丢积分限:", v7["verdict"], "|", v7.get("error"))

    print("== 自测 8: 特征向量字符串漏右括号应自动修复并 PASS ==")
    v8 = scipy_verify("求 A=[[2,1],[1,2]] 的特征值特征向量", "linear_algebra",
                      "Matrix([[2, 1], [1, 2]])",
                      "[(1, Matrix([[-sqrt(2)/2],[sqrt(2)/2]])), (3, Matrix([[sqrt(2)/2],[sqrt(2)/2]])]",
                      [])
    print("  括号修复:", v8["verdict"], "max_error =", v8.get("max_error"), "|", v8.get("error"))

    print("== 自测 9: 模型漏传 ic 时从题面解析初值兜底 ==")
    ode5 = "Eq(Derivative(y(t), t, 2) + 4*y(t), 0)"
    v9a = scipy_verify("解初值问题 y''(t)+4y(t)=0, y(0)=1, y'(0)=0", "ode",
                       ode5, "cos(2*t)", ["t"])
    print("  漏传 ic(题面兜底):", v9a["verdict"], "max_error =", v9a.get("max_error"),
          "| ic_source =", v9a.get("ic_source"))
    v9b = scipy_verify("解初值问题 y''(t)+4y(t)=0, y(0)=1, y'(0)=0", "ode",
                       ode5, "sin(2*t)", ["t"])
    print("  错误解 sin(2t):", v9b["verdict"], "max_error =", v9b.get("max_error"))

    print("== 自测 10: 模型把矩阵写成裸列表字面量 + vars 对象包装(复刻真实事故) ==")
    v10 = scipy_verify("求矩阵 A=[[2,1],[1,2]] 的全部特征值及对应特征向量", "linear_algebra",
                       "[[2,1],[1,2]]",
                       "[(1, [-0.7071067811865475, 0.7071067811865475]), "
                       "(3, [0.7071067811865475, 0.7071067811865475])]",
                       {"value": ["lambda"], "Count": 1})
    print("  裸列表+vars对象:", v10["verdict"], "max_error =", v10.get("max_error"),
          "|", v10.get("error"))

    print("== 自测 11: RK4 收敛阶(加分题, 正确/错误解析解对照) ==")
    ode_rk4 = "Eq(Derivative(y(t), t), -2*y(t) + t)"
    prob_rk4 = ("用 RK4 方法数值求解初值问题 dy/dt = -2y + t, y(0) = 1, "
                "取步长 h = 0.1、0.05、0.025、0.0125, 计算 t=1 处的数值解, "
                "并与解析解对比, 验证收敛阶为 4")
    v11a = rk4_convergence(prob_rk4, "ode", ode_rk4,
                           "(5*exp(-2*t) + 2*t - 1)/4", ["t"],
                           ics={"x0": 0, "y0": 1})
    print("  正确解析解:", v11a["verdict"], "观测阶 =", round(v11a.get("observed_order", 0), 2),
          "min_error =", f"{v11a.get('min_error', 0):.3e}")
    v11b = rk4_convergence(prob_rk4, "ode", ode_rk4, "exp(-2*t)", ["t"],
                           ics={"x0": 0, "y0": 1})
    print("  错误解析解:", v11b["verdict"], "观测阶 =", round(v11b.get("observed_order", 0), 2))
    v11c = rk4_convergence("求解 y''+4y=0, y(0)=1, y'(0)=0", "ode",
                           "Eq(Derivative(y(t), t, 2) + 4*y(t), 0)",
                           "cos(2*t)", ["t"], ics={"x0": 0, "y0": 1})
    print("  二阶 ODE(应 MANUAL):", v11c["verdict"], "|", v11c.get("error"))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        mcp.run()                       # stdio 模式, 供 AGH 连接
