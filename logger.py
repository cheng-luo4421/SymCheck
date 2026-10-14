# -*- coding: utf-8 -*-
"""
hackathon/logger.py
2026 江苏省 AI+ 黑客松 —— AGH 执行记录模块

用途:
    把 agent 运行的每一步（任务规划、工具调用、模型交互、执行反馈、
    结果验证、异常重试、最终报告）自动记录为 JSONL 证据文件,
    供评委人工核查"任务规划→工具调用→执行反馈→结果验证→异常处理"闭环。

用法示例:
    from logger import (init_run, log_plan, log_model_msg, log_feedback,
                        log_verify, log_retry, log_final, final_report, tool_logged)

    init_run("数学验证第一轮")
    log_plan("求解 y''+2y'+y=0, 计划: SymPy 符号解 + SciPy 数值解交叉验证")

    @tool_logged          # 工具函数加这个装饰器, 自动记录入参/结果/耗时/异常
    def sympy_solve(ode: str) -> str:
        ...

    log_verify("最大相对误差", value=0.0003, threshold=0.01, op="lt")
    final_report({"总题数": 10, "通过": 9, "平均误差": 0.001})

输出:
    runs/run-20261012-102301-a1b2.jsonl      每次运行的 JSONL 证据(机器+人工可读)
    runs/run-20261012-102301-a1b2.REPORT.md  最终汇总报告(可直接附在提交材料里)

注意:
    - 所有记录必须由程序真实产生, 禁止手工编辑 JSONL(赛事会核验)
    - 每次完整运行调用一次 init_run, 失败/中断的运行也保留, 失败记录也是真实迭代的证据
"""

import functools
import json
import os
import threading
import time
import traceback
import uuid

_RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
_LOCK = threading.Lock()

_run_id = None        # 当前运行 ID, 由 init_run() 赋值
_echo = False         # 是否同步打印到控制台(开发时看)
_max_len = 2000       # 单个字符串字段最大长度, 超出截断, 防止日志文件爆炸
_stats = {}           # 事件统计, final_report 用
_started_at = ""      # 本次运行开始时间


class LogError(RuntimeError):
    """未调用 init_run() 就记日志时抛出。"""


# ---------------------------------------------------------------- 基础函数

def init_run(name: str, echo: bool = True) -> str:
    """开始一次新的运行, 返回 run_id。每次完整执行调用一次。"""
    global _run_id, _echo, _stats, _started_at
    os.makedirs(_RUNS_DIR, exist_ok=True)
    _run_id = "run-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    _echo = echo
    _stats = {}
    _started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    log("run_start", name=name, note="本文件由程序自动生成, 为 AGH 执行证据")
    return _run_id


def get_run_id() -> str:
    """获取当前运行 ID。"""
    if _run_id is None:
        raise LogError("请先调用 init_run()")
    return _run_id


def evidence_file() -> str:
    """当前运行的 JSONL 证据文件完整路径。"""
    if _run_id is None:
        raise LogError("请先调用 init_run()")
    return os.path.join(_RUNS_DIR, _run_id + ".jsonl")


def _truncate(obj):
    """递归截断过长的字符串, 数字等原样保留。"""
    if isinstance(obj, str) and len(obj) > _max_len:
        return obj[:_max_len] + f"...[截断, 原长度{len(obj)}]"
    if isinstance(obj, dict):
        return {k: _truncate(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_truncate(v) for v in obj]
    return obj


def log(event: str, **fields) -> dict:
    """记录一条通用事件, 自动附带毫秒级时间戳和 run_id。"""
    if _run_id is None:
        raise LogError("请先调用 init_run() 再记日志")
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}",
        "run_id": _run_id,
        "event": event,
    }
    entry.update({k: _truncate(v) for k, v in fields.items()})
    _stats[event] = _stats.get(event, 0) + 1
    if event == "verify" and "verdict" in fields:
        key = f"verify:{fields['verdict']}"
        _stats[key] = _stats.get(key, 0) + 1
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with _LOCK:
        with open(evidence_file(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    if _echo:
        print(f"[{event}] {line[:160]}")
    return entry


# ---------------------------------------------------------------- 事件辅助函数

def log_plan(content: str, **extra) -> dict:
    """任务规划: agent 的解题/执行计划与理由。"""
    return log("plan", content=content, **extra)


def log_model_msg(role: str, content: str, **extra) -> dict:
    """模型交互: 发给 Agnes 模型的 prompt 或收到的响应(Agnes 模型参与核心任务的证据)。"""
    return log("model_msg", role=role, content=content, **extra)


def log_feedback(source: str, content: str, **extra) -> dict:
    """执行反馈: 代码 stdout/stderr、中间结果等。"""
    return log("feedback", source=source, content=content, **extra)


def log_verify(check: str, value, threshold=None, op="lt", verdict=None, **extra) -> dict:
    """结果验证: 不传 verdict 时自动按 op 比较 value 与 threshold 判定 PASS/FAIL。

    op 取值: "lt" / "le" / "gt" / "ge" / "eq"
    """
    if verdict is None:
        verdict = _compare(value, threshold, op)
    return log("verify", check=check, value=value, threshold=threshold,
               op=op, verdict=verdict, **extra)


def _compare(value, threshold, op):
    if threshold is None:
        return "MANUAL"
    try:
        ok = {"lt": value < threshold, "le": value <= threshold,
              "gt": value > threshold, "ge": value >= threshold,
              "eq": value == threshold}[op]
        return "PASS" if ok else "FAIL"
    except Exception:
        return "MANUAL"


def log_retry(attempt: int, reason: str, new_strategy: str, **extra) -> dict:
    """异常处理: 第几次重试、失败原因、换用的新策略。"""
    return log("retry", attempt=attempt, reason=reason,
               new_strategy=new_strategy, **extra)


def log_final(content: str, **extra) -> dict:
    """最终结果/结论。"""
    return log("final", content=content, **extra)


# ---------------------------------------------------------------- 工具装饰器

def tool_logged(fn):
    """装饰器: 自动记录工具调用的入参、返回值、耗时;
    异常时记录错误与 traceback 后重新抛出, 让上层 agent 循环捕获并走重试逻辑。

    用法: 给每个暴露给 agent 的工具函数(调 SymPy、跑仿真、查数据等)加上 @tool_logged
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.time()
        payload = {"tool": fn.__name__, "args": kwargs or args}
        try:
            result = fn(*args, **kwargs)
            payload.update(result=result, status="ok",
                           duration_ms=round((time.time() - t0) * 1000, 1))
            log("tool_call", **payload)
            return result
        except Exception as e:
            payload.update(error=repr(e), traceback=traceback.format_exc(),
                           status="error",
                           duration_ms=round((time.time() - t0) * 1000, 1))
            log("tool_call", **payload)
            raise

    return wrapper


# ---------------------------------------------------------------- 最终报告

def final_report(summary: dict) -> str:
    """写入最终汇总: JSONL 里的 final 事件 + 人类可读的 REPORT.md, 返回报告路径。

    summary 例如: {"题目数": 10, "通过": 9, "最大相对误差": 0.001, "重试次数": 2}
    """
    if _run_id is None:
        raise LogError("请先调用 init_run()")
    log("final", summary=summary)
    md = [
        f"# 黑客松运行报告 {_run_id}",
        "",
        f"- 开始时间: {_started_at}",
        f"- 结束时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 证据文件: runs/{_run_id}.jsonl",
        "",
        "## 事件统计",
        "",
        "| 事件 | 次数 |",
        "|---|---|",
    ]
    for k, v in _stats.items():
        md.append(f"| {k} | {v} |")
    md += ["", "## 最终结果", ""]
    for k, v in summary.items():
        md.append(f"- **{k}**: {v}")
    md += ["", f"本报告由 logger.py 根据 {_run_id}.jsonl 自动生成, 请勿手工修改。"]

    path = os.path.join(_RUNS_DIR, _run_id + ".REPORT.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return path
