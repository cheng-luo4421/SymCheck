# -*- coding: utf-8 -*-
"""
direct_ask.py — 对比实验 · 模型直接作答(队长 · 系统集成线)

用同一题库 SymBench-15, 把每题 statement 直接发给 agnes-3.0-flash(不带工具、
不带闭环提示词), 记录模型原始作答。与闭环(AGH+SymPy/SciPy 交叉验证)对比,
验证"闭环显著提升正确率"这一核心价值主张。

输出: batch_out/direct_answers.json — 逐题 {id, category, statement, model_answer, asked_at}。
不包含 expected(标准答案只留在评测端 problems.py, 绝不发给模型, 也避免对比脚本误用)。

用法: python -I direct_ask.py [--only <id>]
队友侧: 按此 JSON 用其自身评分逻辑逐题打分(与闭环同题库同口径), 产出对比表。
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import problems  # noqa: E402

CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
OUT = HERE / "batch_out" / "direct_answers.json"

_PROMPT = "请直接解答下面的数学题, 只给出答案(含必要算式), 不要解释过程:\n{statement}"


def ask_agnes(prompt: str, max_tokens: int = 600) -> str:
    body = {
        "model": CONFIG["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        CONFIG["base_url"] + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + CONFIG["api_key"],
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    probs = ([p for p in problems.SYMBENCH15 if p["id"] == only] if only
             else problems.SYMBENCH15)
    if only and not probs:
        sys.exit(f"未知题目 id: {only}")

    # 续跑: 已问过的题跳过(改 --only 重问单题需先删文件里的对应行)
    prev = []
    if not only and OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = []
    done_ids = {r["id"] for r in prev}

    rows = list(prev)
    for p in probs:
        if p["id"] in done_ids:
            continue
        prompt = _PROMPT.format(statement=p["statement"])
        try:
            answer = ask_agnes(prompt)
        except urllib.error.HTTPError as e:
            answer = f"[HTTP {e.code}] {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception as e:
            answer = f"[{type(e).__name__}] {e}"
        rows.append({"id": p["id"], "category": p["category"],
                     "statement": p["statement"], "model_answer": answer,
                     "asked_at": time.strftime("%Y-%m-%d %H:%M:%S")})
        print(f"{p['id']:<20}{len(answer):>5} 字")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n== 已作答 {len(rows)}/{len(problems.SYMBENCH15)} ==(batch_out/direct_answers.json)")


if __name__ == "__main__":
    main()
