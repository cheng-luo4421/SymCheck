# SymCheck —— 基于 AGH 的双方法交叉验证自治数学求解智能体

2026 江苏省 AI+ 科学与工程创新实践黑客松(高校组 · 本科生组)参赛作品。

## 一、项目简介

**问题:** 大语言模型解数学题常"答而不验"——直接作答无法保证正确性,也缺乏可核查的证据链。

**方案:** SymCheck 以 AgnesHarness(AGH)为智能体运行底座、Agnes 模型为唯一调用模型,构建"读题 → 规划 → SymPy 符号求解 → SciPy 数值独立验证 → 误差阈值判定 → 失败换策略重试(≤3 轮)→ 中文报告"的完整闭环。符号方法与数值方法**两套独立实现交叉验证**,任何一步失败都会触发换策略重试,全程留痕。

**价值主张:** 在自建评测集 SymBench-15(微积分/线性代数/ODE 各 5 题)+ RK4 收敛阶加分题上,闭环后**16/16 全部 PASS**;对比基线(同一模型直接作答、同题同口径,经逐题人工转写 + 哈希绑定 + SymPy 数学核验)为 **13/15(86.67%)**——linear-algebra-02、04 两题答错,而闭环将这两题全部救回。**独立评分脚本给出:正确率 86.67% → 100%,提升 13.33 个百分点**(见 `batch_out/comparison_out.json`,由对比评分脚本独立生成,非自证)。对比实验证明:验证闭环能显著提升数学求解的可靠性。

## 二、核心闭环流程

```
题目 ──► [AGH 智能体] ──► 规划(读题、定求解策略)
   ▲                          │
   │                          ▼
   │                    sympy_solve_tool   (SymPy 符号解)
   │                          │
   │                          ▼
   │                    scipy_verify_tool  (SciPy/NumPy 独立数值验证)
   │                          │  max_error ≤ threshold?
   │              PASS ───────┴─────── FAIL
   │                │                  │
   │                │                  ▼
   │                │           strategy_switch_tool (换策略, ≤3 轮)
   │                │                  │
   │                └────────┬─────────┘
   │                         ▼
   └────────────── rk4_convergence_tool(加分题: RK4 收敛阶第二道验证)
                              │
                              ▼
                    中文最终报告(符号解、verdict、max_error、重试次数)
```

四步闭环全部由 AGH 驱动模型自主完成:任务规划、能力调用(4 个 MCP 数学工具)、反馈处理(FAIL 时换策略重试)、结果验证(双方法交叉验证)。每题全程证据写入 JSONL 日志。

## 三、四个数学工具(MCP stdio 服务器)

| 工具 | 作用 | 关键设计 |
| --- | --- | --- |
| `sympy_solve_tool` | SymPy 符号求解 | 不定/定积分、极限、方程组、求逆/行列式/特征对、ODE 通解与初值问题;安全解析(符号白名单) |
| `scipy_verify_tool` | SciPy 数值独立验证 | quad 高精度定积分(1e-11)、双侧 Richardson 外推极限、np.linalg 矩阵运算、solve_ivp(RK45)轨迹对照;ODE 通解用初值组(含零解)验证,漏常数判 FAIL;绝对误差口径,阈值逐题读取 |
| `strategy_switch_tool` | 失败换策略 | 策略库白名单,驱动 ≤3 轮重试,3 轮耗尽 give_up |
| `rk4_convergence_tool` | RK4 收敛阶验证(加分题) | 独立实现 RK4,四档步长与解析解比对,误差比趋 16(观测阶趋 4)判 PASS;**解析解错误时误差不随步长缩小(误差比趋 1)会被判 FAIL**——与 scipy_verify 构成第二道独立交叉验证 |

工具的工程化细节(全部有自测覆盖):

- **对模型非致命格式错误自动归一化**:矩阵写成裸列表字面量、vars 被序列化成对象、表达式漏右括号,均可自动修复并给出可操作提示;
- **兜底设计**:模型三轮都漏传 ODE 初值且读不懂工具提示时,工具从题面文本正则解析 y(0)=y0 / y'(0)=y1(结果带 `ic_source` 字段可审计);
- **口径防护**:裸表达式+常数结果会被拒(MANUAL),提示用 Integral/Limit 包装,防止模型绕过验证;
- **完整性守卫**:n 阶矩阵特征对必须给出 n 个互异特征值+向量,缺则 FAIL。

## 四、评测集与结果

**SymBench-15**(自建,微积分 5 / 线性代数 5 / ODE 5)+ **RK4 加分题**(dy/dt = −2y + t,验证收敛阶为 4)。

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 闭环批量(绝对误差口径) | **16/16 PASS**(冻结批次 2026-10-12 22:25,16 题全部 0 重试),每题 rc=0 + 中文报告 | `batch_out/summary_freeze_1012.json`(冻结版备份,run_id ↔ 题目映射)+ `runs/` 每题一个 JSONL |
| 对比基线(模型直接作答,同题同口径) | **13/15(86.67%)**;linear-algebra-02 答 (2,1,3)(max_error=1.0)、linear-algebra-04 两个特征值都答 √3(max_error=1.268);两题闭环均 PASS | `batch_out/direct_answers.json`(原文 SHA256 绑定 `reviewed_answers.json` 人工转写) |
| 独立对比评分 | **闭环 15/15 vs 基线 13/15,提升 +13.33 个百分点**,comparison_complete=True,UNVERIFIED=0(2026-10-12 冻结批次数据重生成) | `batch_out/comparison_out.json/.md`(队友评分脚本生成,非自证) |
| RK4 加分题 | 四档步长 h=0.1/0.05/0.025/0.0125 终点误差 5.33e-6/3.07e-7/1.84e-8/1.13e-9,误差比 17.4/16.7/16.3,观测收敛阶 **4.07**;离线参考实现 `rk4_experiment.py`(队员独立实现)与闭环工具结果一致 | `runs/run-20261012-222430-4b42.jsonl`(冻结批次)+ `rk4_out.json` |
| 闭环价值实证 | calc-04 历史批次(10/9)第 1 轮口径错配 FAIL → 模型自主 strategy_switch → 第 2 轮 PASS(闭环换策略演示);冻结批次口径防护修复后模型正确包装 Integral 一遍过(0 重试) | `runs/run-20261009-223426-3f95.jsonl`(换策略)+ `runs/run-20261012-222028-f008.jsonl`(冻结 0 重试) |

**三类测试(正常/边界/失败)** 完整案例见《三类测试报告》,包括:极限双侧外推、初值兜底、通解含零解验证、错误解 sin(2t) 被 FAIL(1.41)、漏常数判 FAIL(14.8)、错误解析解被收敛阶判定 FAIL 等。

## 五、证据体系

自建 logger(`logger.py`)按 7 类事件写 JSONL:`plan / model_msg / tool_call / verify / retry / feedback / final`。每个 run 文件对应一道题的一次会话,**run_id ↔ 题目 ↔ 判定结果**三方映射存 `batch_out/summary.json`;AGH 自带 Trace 与 JSONL 双份证据,演示视频逐段标注 run_id。

## 六、复现步骤

**环境:** Windows 11 · Node.js v24.17.0 · Python 3.12.10 · SymPy 1.14.0 · SciPy 1.18.1 · NumPy 2.5.3 · AGH(AgnesAI-Labs/agnes-harness,Apache-2.0,本地构建)

1. **构建 AGH 本地 CLI**:按 AGH 官方文档构建,得到 `agnes.mjs`(本项目使用其本地模式)。
2. **安装 Python 依赖**:`pip install sympy scipy numpy mcp`(国内可用 npmmirror/清华镜像)。
3. **配置 Agnes Provider**:AGH Web 界面(默认 http://127.0.0.1:4177)添加 Agnes AI Provider——base_url `https://api.agnes-ai.cn/v1`、模型 `agnes-3.0-flash`、填入 API Key(Key 不入库,`config.json` 已 gitignore)。
4. **注册 MCP 服务器**:Web 界面注册 stdio 服务器,命令 `python mcp_tools.py`,trust + enable 至 ready。
5. **自测**:`python -I mcp_tools.py --selftest`(11 项,应全过)。
6. **跑批**:先 `python -I restart_agh.py`(全清冷启动,等 Web+行进程就绪),再 `python -I batch_agh.py --include-bonus`(15 题 + 加分题;`--only <id>` 单题重跑)。每题约 1 分钟,结果落 `batch_out/`。
7. **离线数值评测**(不经过 AGH 的本地口径检查):`python -I batch_eval.py`。
8. **对比基线**(模型直接作答):`python -I direct_ask.py`,输出 `batch_out/direct_answers.json`。
9. **独立对比评分**(基线人工转写核验 + 闭环日志审计):`python analyze.py --direct batch_out/direct_answers.json --summary batch_out/summary.json --runs runs --out comparison_out.json`,输出 `comparison_out.json/.md`(依赖 SymPy;analyze.py/score_batch.py/inspect_baseline.py/reviewed_answers.json 须同目录)。
10. **RK4 离线参考实验**(不依赖 AGH 的标准库实现):`python -I rk4_experiment.py --out rk4_out.json`。
11. **AGH Trace 导出**(官方会话账本,与题目粒度 JSONL 双份证据):`python -I export_agh_trace.py`(需 AGH 守护进程在线),产物 `batch_out/agh_trace/*.jsonl/.html` + `manifest.md`。

## 七、目录结构

```
hackathon/
├── problems.py            # 评测数据(SymBench-15 + RK4 加分题,含标准答案与阈值)
├── mcp_tools.py           # MCP 数学工具服务器(4 工具, v0.4.0)
├── logger.py              # JSONL 证据日志(7 类事件)
├── batch_agh.py           # AGH 端到端批量评测驱动
├── batch_eval.py          # 本地离线评测(不经 AGH)
├── direct_ask.py          # 对比基线(模型直接作答)
├── analyze.py             # 对比评分:基线哈希绑定核验 + 闭环日志审计
├── score_batch.py         # 批量结果评分报告生成
├── inspect_baseline.py    # 基线输入完整性检查
├── reviewed_answers.json  # 基线人工转写的原文 SHA256 绑定
├── rk4_experiment.py      # RK4 离线参考实现(队员, 标准库)
├── rk4_out.json           # RK4 参考实验输出
├── restart_agh.py         # AGH 全清冷启动脚本
├── export_agh_trace.py    # AGH 官方 Trace 导出(工作区粒度账本 → batch_out/agh_trace/)
├── make_submission.py     # 提交包组装(代码+证据+文档, 自动脱敏 config 模板)
├── test_agnes.py          # Agnes API 冒烟测试
├── probe_models.py        # 模型可用性探测
├── config.json            # API Key(不入库)
├── batch_out/             # summary.json / direct_answers.json / comparison_out.json/.md / agh_trace/
└── runs/                  # 每题一个 JSONL 证据文件
```

## 八、成员分工与独立完成声明

(定稿见《成员分工和独立完成声明》,10/13 随材料提交。)

- 队长:**系统集成线**——AGH 集成与 Provider/MCP 配置、mcp_tools.py 四工具、logger 证据体系、批量评测驱动、打包提交;
- 队员:**数学评测线**——题目集 problems.py、RK4 收敛阶实验(rk4_experiment.py,标准库独立实现)、对比评分脚本(analyze.py/score_batch.py/inspect_baseline.py/reviewed_answers.json)、演示视频、文档(队员使用 Codex 辅助)。

## 九、第三方素材来源说明

- **AgnesHarness(AGH)**:赛会指定智能体底座,来源 AgnesAI-Labs/agnes-harness(Apache-2.0),按官方文档本地构建使用;
- **Agnes 模型**:赛会指定唯一调用模型(agnes-3.0-flash),经官方中国网关 OpenAI 兼容 API 调用;
- **SymPy / SciPy / NumPy**:开源数值符号计算库,用于双方法交叉验证的两种独立实现;
- **题目集**:队伍自建,标准答案经人工逐题核验;
- 其余代码均为赛期内队伍原创。
