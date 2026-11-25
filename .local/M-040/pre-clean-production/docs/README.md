# 文档索引

`docs/` 下每一份文件的用途、状态与维护时机。**先看 `PROJECT_STATUS.md`**。

| 文件 | 用途 | 状态 | 何时更新 |
|---|---|---|---|
| [`PROJECT_STATUS.md`](PROJECT_STATUS.md) | **单一事实来源**：目标 G1–G6、逐项完成度、已知未解决问题、关键设计结论 | 当前 | 每次交付后 |
| [`SCALABILITY_MOBILITY_PLAN.md`](SCALABILITY_MOBILITY_PLAN.md) | 总体计划：两个维度、四层架构、P0–P5 路线、主要瓶颈 | 当前 | 阶段变更时 |
| [`ARCHITECTURE_DELTA.md`](ARCHITECTURE_DELTA.md) | 现状审计、与 `ALGORITHM.md` 的 8 处差异、模块依赖、数据流、时序约束 | 当前 | 改动协议或模块时 |
| [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) | 逐机制【板】【编】【仿】【未】状态与硬件阻塞项 | 当前 | 每次上板后 |
| [`MOBILITY_MODEL.md`](MOBILITY_MODEL.md) | 移动状态定义、相对运动、LET 数学、几何下界、不确定性、场景 | 当前 | 移动模型变更时 |
| [`LRN2_LRC1_DESIGN.md`](LRN2_LRC1_DESIGN.md) | LoRa 上行遥测 / 下行控制 / 分片 / AoI / 超帧 / 容量推导 | 设计，未实现 | 协议定稿时 |
| [`SCALABILITY_PARAMETER_PLAN.md`](SCALABILITY_PARAMETER_PLAN.md) | 全部容量/时间/跳数参数：来源、推导、当前值、目标值、定参实验 | 当前 | 定参时 |
| [`EXPERIMENT_PLAN.md`](EXPERIMENT_PLAN.md) | 实验矩阵、指标、种子、复现规则、P1 已完成结果 | 当前 | 实验设计变更时 |
| [`LORA_GATEWAY_REQUIREMENTS.md`](LORA_GATEWAY_REQUIREMENTS.md) | 八通道网关采购规格与到货接入计划 | 待采购 | 下单/到货时 |

## 相关但不在 docs/ 的文档

| 位置 | 内容 |
|---|---|
| `firmware/mid_baseline/field_agent/ALGORITHM.md` | 三平面算法总纲（协议逻辑入口） |
| `firmware/mid_baseline/field_agent/{DENSE_ADHOC,DENSE_DESIGN,PROACTIVE_ROUTING}.md` | 密集组网与主动路由的设计与实测记录 |
| `BUILD-*/BUILD.md` | 每个固件版本的改动、验证与回滚目标 |
| `CHANGELOG.md` | 固件版本沿革（build_id 顺序） |
| `simulation/results/` | 被采纳的实验结论（含来源 sha256） |
| `simulation/outputs/DENSE-SIM/*/ANALYSIS.md` | 仿真分析与负面结论 |
| `coordination/CURRENT.md` | M 维护的任务级滚动摘要 |

## 约定

1. 规划文档放 `docs/`，**不覆盖**已有有效内容，只增补或新建。
2. 结论必须带证据路径；仿真与实测必须分别标注。
3. 未验证的内容写明「未验证」，不得写成已通过。
4. 协议格式变更必须同时更新 `ARCHITECTURE_DELTA.md` 的改造范围表。
