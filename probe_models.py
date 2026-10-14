# -*- coding: utf-8 -*-
"""
hackathon/probe_models.py
遍历 config.json 的 model_options, 逐个发最小请求, 探测本 Key 有权访问哪些模型。
用法: python -I probe_models.py
"""
import json
import sys
import urllib.request
import urllib.error

CFG = json.load(open(__file__.rsplit("\\", 1)[0] + "\\config.json", encoding="utf-8"))


def try_model(model: str) -> str:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "只回一个数字: 1"}],
        "max_tokens": 16,
    }
    req = urllib.request.Request(
        CFG["base_url"] + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + CFG["api_key"],
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        reply = data["choices"][0]["message"]["content"][:60].replace("\n", " ")
        return f"OK -> {reply}"
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace"))["error"]["message"]
        except Exception:
            msg = f"HTTP {e.code}"
        return f"{msg} ({e.code})"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for m in CFG["model_options"]:
        print(f"{m}: {try_model(m)}")
