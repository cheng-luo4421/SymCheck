# AGH Trace 导出清单(生成于 2026-10-12 22:26)

每个 JSONL 是 AGH 官方会话账本(协议事件, 每行一条), HTML 是可读时间线。
默认脱敏(路径/密钥/PII), 未用 --raw。与题目粒度 JSONL(runs/) 互为双份证据。

- **main**(主工作区:10/9 端到端主批(15 题 + 首个闭环任务)): 19 轮 / 58 次工具调用 / 1392 事件 / 2026-10-09 15:13 → 2026-10-12 14:26
  - 事件分布: {'session/start': 1, 'x/agnes/code-mode/kernel': 4, 'x/agnes/privacy/consent': 4, 'inbox': 38, 'user/message': 20, 'turn/start': 19, 'x/host/session-title': 3, 'budget.state': 77, 'x/core/op-mark': 77, 'x/core/context-breakdown': 77, 'step/start': 77, 'request/header': 77, 'effect/intent': 135, 'request/sent': 77, 'assistant/output': 69, 'assistant/message': 77, 'cost/ledger': 78, 'effect/settled': 135, 'step/end': 77, 'verifier/signal': 135, 'turn/end': 19, 'tool/call': 58, 'tool/result': 58}
  - 日期分布: {'2026-10-09': 1388, '2026-10-11': 2, '2026-10-12': 2}
  - 文件: batch_out/agh_trace/main.jsonl / main.html

- **agh_ws**(10/9 最早批次(冷启动测试)): 18 轮 / 36 次工具调用 / 983 事件 / 2026-10-09 15:33 → 2026-10-12 14:26
  - 事件分布: {'session/start': 1, 'x/agnes/code-mode/kernel': 3, 'x/agnes/privacy/consent': 3, 'inbox': 36, 'user/message': 19, 'turn/start': 18, 'x/host/session-title': 3, 'budget.state': 54, 'x/core/op-mark': 54, 'x/core/context-breakdown': 54, 'step/start': 54, 'request/header': 54, 'effect/intent': 90, 'request/sent': 54, 'assistant/message': 54, 'tool/call': 36, 'cost/ledger': 55, 'effect/settled': 90, 'tool/result': 36, 'verifier/signal': 90, 'step/end': 54, 'assistant/output': 53, 'turn/end': 18}
  - 日期分布: {'2026-10-09': 979, '2026-10-11': 2, '2026-10-12': 2}
  - 文件: batch_out/agh_trace/agh_ws.jsonl / agh_ws.html

- **agh_ws2**(10/9 深夜中间批次(冷启动测试)): 1 轮 / 5 次工具调用 / 118 事件 / 2026-10-09 15:45 → 2026-10-12 14:26
  - 事件分布: {'session/start': 1, 'x/agnes/code-mode/kernel': 3, 'x/agnes/privacy/consent': 3, 'inbox': 2, 'user/message': 2, 'turn/start': 1, 'x/host/session-title': 3, 'budget.state': 6, 'x/core/op-mark': 6, 'x/core/context-breakdown': 6, 'step/start': 6, 'request/header': 6, 'effect/intent': 11, 'request/sent': 6, 'assistant/message': 6, 'tool/call': 5, 'cost/ledger': 7, 'effect/settled': 11, 'tool/result': 5, 'verifier/signal': 11, 'step/end': 6, 'assistant/output': 4, 'turn/end': 1}
  - 日期分布: {'2026-10-09': 114, '2026-10-11': 2, '2026-10-12': 2}
  - 文件: batch_out/agh_trace/agh_ws2.jsonl / agh_ws2.html

- **agh_ws3**(10/9 深夜加固批 + 10/10 RK4 加分题端到端(run-20261010-130721)): 3 轮 / 5 次工具调用 / 160 事件 / 2026-10-09 15:49 → 2026-10-12 14:26
  - 事件分布: {'session/start': 1, 'x/agnes/code-mode/kernel': 5, 'x/agnes/privacy/consent': 5, 'inbox': 6, 'user/message': 5, 'turn/start': 3, 'x/host/session-title': 3, 'budget.state': 8, 'x/core/op-mark': 8, 'x/core/context-breakdown': 8, 'step/start': 8, 'request/header': 8, 'effect/intent': 13, 'request/sent': 8, 'assistant/output': 7, 'assistant/message': 8, 'tool/call': 5, 'cost/ledger': 9, 'effect/settled': 13, 'tool/result': 5, 'verifier/signal': 13, 'step/end': 8, 'turn/end': 3}
  - 日期分布: {'2026-10-09': 62, '2026-10-10': 94, '2026-10-11': 2, '2026-10-12': 2}
  - 文件: batch_out/agh_trace/agh_ws3.jsonl / agh_ws3.html

- **agh_ws_freeze**(批次说明待补充(见 manifest.md, 可按运行日期对照《成绩单》)): 16 轮 / 34 次工具调用 / 878 事件 / 2026-10-12 14:19 → 2026-10-12 14:25
  - 事件分布: {'session/start': 1, 'x/agnes/code-mode/kernel': 1, 'x/agnes/privacy/consent': 1, 'inbox': 32, 'user/message': 17, 'turn/start': 16, 'x/host/session-title': 3, 'budget.state': 50, 'x/core/op-mark': 50, 'x/core/context-breakdown': 50, 'step/start': 50, 'request/header': 50, 'effect/intent': 84, 'request/sent': 50, 'assistant/message': 50, 'tool/call': 34, 'cost/ledger': 51, 'effect/settled': 84, 'tool/result': 34, 'verifier/signal': 84, 'step/end': 50, 'assistant/output': 20, 'turn/end': 16}
  - 日期分布: {'2026-10-12': 878}
  - 文件: batch_out/agh_trace/agh_ws_freeze.jsonl / agh_ws_freeze.html

