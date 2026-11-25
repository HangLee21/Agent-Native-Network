# 实验计划

目标：每个结论都要能**复现、可消融、可回退**。固定种子、固定拓扑、固定业务负载。

## 1 维度

| 维度 | 取值 |
|---|---|
| 节点规模 N | 5、10、20、30 |
| 拓扑 | 紧凑、稀疏、长链、动态编队 |
| 移动场景 | 静态、S1 稳定编队、S2 交汇、S3 分裂、S4 汇合、S5 移动中继、S6 突然退出、S7 速度/航向突变 |
| 业务 | 随机目的 2–3 s；集中目的（少数 sink）；突发 |
| 策略（对照） | ①基线（固定 Hello + 最短路径）②自适应 ND ③LET 感知选路 ④LET + 主备 ⑤LET + 预热/局部修复 ⑥LoRa 全局协调 |
| 消融 | 每策略单独开关，逐项关闭 |
| 种子 | 每配置 ≥5 个（1、2、3、4、5） |
| 时长 | 静态 60 s；动态 ≥120 s（覆盖分裂-汇合全过程） |

## 2 指标（必须同时报告，不能只报 PDR）

**交付与时效**：PDR、E2E Delay P50/P95/P99、Average Hop Count、Task Completion Ratio。
**控制开销**：RREQ/s、每成功发现所需 RREQ 数、Control Overhead（控制字节/业务字节）。
**路由动态**：Route Discovery Latency、Route Recovery Time、Route Churn（每分钟变化次数）。
**移动预测**：Link Prediction Error（秒）、Precision、Recall、Warning Lead Time、`confidence` 校准曲线。
**资源**：Queue Drop Rate、`input_overflow_total`、`send_callback_timeouts`、Heap Watermark（free/min）。
**LoRa**：Report Delivery Ratio、AoI（P50/P95）、Command Execution Ratio。
**稳健性**：节点失联后 60 s 内恢复比例。

## 3 复现规则

1. 所有仿真输出到 `simulation/outputs/<任务>/<日期>-<序号>/`，含 `RUN_MANIFEST.json`。
2. 固定 `--seed`，记录种子列表；同一配置重复跑 5 次取均值与极差。
3. 仿真器：`simulation/dense_adhoc/sim_{dynamic,real,gw,alg,hops}.py`（协议级，无 Wi-Fi 碰撞模型 → 结果为**乐观上界**，必须标注）。
4. 实板实验记录 `native.jsonl` + 逐板 `raw.bin` + `RESULT.json`，交付只认 `rx_local`。
5. **合成轨迹与实测数据必须分别标注**，不得混用。

## 4 阶段实验编排

### P1（本轮）LET Shadow —— 已完成，合成数据

工具：`tools/mid_baseline/mobility/let_shadow.py`（`simulate` + `eval`）。
模型：位置误差 8 m、速度误差 0.8 m/s、`R=120 m`、2σ 置信带、置信度门限 300。
**几何真值，非 RF 实测。**

| 场景 | 断链次数 | Recall | Precision | 平均预警提前量 | 平均绝对误差 | 误报行 |
|---|---:|---:|---:|---:|---:|---:|
| S1 稳定编队 | 0 | — | — | — | — | **0** |
| S2 交汇（5 种子） | 1 | **1.00** | **0.99** | **4.7 s** | **0.2 s** | 1 |
| S3 分裂（5 种子） | 1 | **1.00** | **1.00** | **13.3 s** | **0.5 s** | 0 |
| S6 速度突变 | 1 | 1.00 | 0.991 | 22.5 s | 0.7 s | 2 |

**关键发现**：未加置信度门限时，S1（同速同向）会因相对速度≈0 而把位置误差放大成巨大不确定带，
**每 100 ms 产生一次 AT_RISK 误报（596 次）**。门限后降为 0。这验证了"必须有不确定性而不是
只算 LET"的设计要求。

### P2 自适应 ND

对照：固定 2–3 s vs `T_lost=clamp(0.3R/v_rel, 2 s, 12 s)`。
验收：同负载下 PDR 不降、RREQ/s 不升 >10%、失效检测时延下降 ≥40%。

### P3 LET 感知选路

对照：最短路径 vs `Cost = w1·ETX + w2·LET + w3·Queue`。
验收：P95 时延下降 ≥15% 或 Route Recovery Time 下降 ≥25%，且控制开销增幅 ≤20%。

### P4 预热与局部修复

验收：切换中断时间下降 ≥30%，预热产生的额外 RREQ ≤ 总量的 10%。

### P5 LRN2/LRC1

验收（单信道 TDMA 前提）：30 节点快照周期 ≤ 15 s、AoI P95 ≤ 30 s、命令执行率 ≥95%。

## 5 已知会污染结论的因素

1. 仿真**无 Wi-Fi 碰撞/CSMA 模型** → PDR 偏乐观；
2. `range_mm` 是几何假设，不是实测通信距离；
3. 合成轨迹无遮挡、无多径、无天线姿态；
4. 实板只有 5 块，N=10/20/30 只能靠仿真或分批实测；
5. LoRa 单信道实测 30 节点不可行，只能用 TDMA 或换硬件验证。
