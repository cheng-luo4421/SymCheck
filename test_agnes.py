# -*- coding: utf-8 -*-
"""
hackathon/test_agnes.py
Agnes 模型 API 冒烟测试: 直接调 api.agnes-ai.cn(OpenAI 兼容), 验证 Key/模型可用。
不依赖 AGH 构建, 先跑通模型链路。

用法: python -I test_agnes.py [--ask 你的问题]
"""
import json
import sys
import urllib.request

CONFIG = json.load(open(__file__.rsplit("\\", 1)[0] + "\\config.json", encoding="utf-8"))


def ask_agnes(prompt: str, model: str = None, max_tokens: int = 300) -> str:
    body = {
        "model": model or CONFIG["model"],
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


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 and sys.argv[1] == "--ask" \
        else "用一句话回答: 1+1 等于几? (只回答数字和算式, 不要解释)"
    print(f"模型: {CONFIG['model']}")
    print(f"端点: {CONFIG['base_url']}")
    print(f"提问: {prompt}")
    try:
        reply = ask_agnes(prompt)
        print("回复:", reply)
        print("\n=== 冒烟测试通过: Key 有效, 模型可用 ===")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:600]}")
        sys.exit(1)
    except Exception as e:
        print(f"连接失败: {type(e).__name__}: {e}")
        sys.exit(1)
