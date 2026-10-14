# SymCheck 对比评分报告

Baseline mathematical grading + final-verify log consistency; not independent loop re-solving

基线 PASS：13/15；待复核：0。

闭环日志审计 PASS：15/15；对比完整：True。

| ID | 基线 | 闭环日志审计 | 问题 |
| --- | --- | --- | --- |
| calculus-01 | PASS | PASS |  |
| calculus-02 | PASS | PASS |  |
| calculus-03 | PASS | PASS |  |
| calculus-04 | PASS | PASS |  |
| calculus-05 | PASS | PASS |  |
| linear-algebra-01 | PASS | PASS |  |
| linear-algebra-02 | FAIL | PASS |  |
| linear-algebra-03 | PASS | PASS |  |
| linear-algebra-04 | FAIL | PASS |  |
| linear-algebra-05 | PASS | PASS |  |
| ode-01 | PASS | PASS |  |
| ode-02 | PASS | PASS |  |
| ode-03 | PASS | PASS |  |
| ode-04 | PASS | PASS |  |
| ode-05 | PASS | PASS |  |

正确率提升（百分点）：13.333333333333334。缺失日志或待人工复核时不计算提升。

按文件行顺序取最后一个 verify；允许先 FAIL 后 PASS，不从 summary 自行补造判定。加分题单独统计。日志一致性不等于独立数学正确性证明。
