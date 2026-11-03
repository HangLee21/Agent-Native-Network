# EoRa-HUB-400TB五板使用入口

2026-11-03。到货前代码已具备：同一C协议核心的主机harness、ESP32-S3目标工程、已绑定串口的有限台架控制，以及闭合采集后的自动分析和有来源指标追加。ESP目标尚未编译，五板未到，未刷写、未测RF，所有真实测量仍为null。先静态台架，再安装小车。

五板使用同一固件、按运行配置轮换源/中继/目的，无固定中心板；电脑负责绑定、配置与采集，不代替无线转发。ESP-NOW只承载单跳，上层实现HELLO、按需源路由、端点ACK有限重试、状态latest/expiry及best-effort CANCEL。[协议与台架说明](PROTOCOL_AND_BENCH_PLAN.md)给L5–L1职责、精确命令、日志/指标口径和实现限制。

## 现在哪层已有证据

| 层次 | 已有证据 | 仍待验证 |
|---|---|---|
| C核心/主机协议 | E1_lifecycle_v4：12场景6200断言、164边界检查及3原反例；E2独立核心20项通过 | 无持久exactly-once/分片/加密；不是RF样本 |
| 离线分析 | E2_analyzer_v2：44项自测及实际C日志封装互验1项通过 | PDR需接收覆盖、goodput需实测窗口，未知量不补算 |
| H采集/指标追加 | H_capture_v5：35项主机测试，17号run的实际C host→H Capture→v2分析互验通过；synthetic未填实测 | 实际串口、USB/天线、板型和无线行为未验证 |
| 最后独立互验 | [E2最终6项H Capture→analysis_bridge→API互验](../../../simulation/results/2026-11-03-M-016-espnow-host/E2-015/20261103-17-final-H-capture-independent/result.json)通过，失败/错误/跳过均0 | synthetic主机证据，无硬件测量 |
| ESP目标/静态五板 | ESP-IDF v5.5.1候选工程与只构建入口已交付 | 目标构建not_performed、未刷写、无线测量not_measured |

上述源码和主机证据已冻结。最后独立互验与C终审进度由[C-017](../../../coordination/tasks/C-017.md)、[E2-015](../../../coordination/tasks/E2-015.md)、[M-016](../../../coordination/tasks/M-016.md)确认；文件或测试存在不等于最终验收。[原字节归档](../../../simulation/results/2026-11-03-M-016-espnow-host/README.md)保存源码/日志/manifest等，件数不是测试数。旧接口、6208旧计数和早期H测试均保留为历史。

## 到货后怎样接续

从仓库根目录运行；每条命令都需要相应实时任务已允许执行，使用全新直属run目录，不覆盖旧结果。H-001/H-002状态以主卡与应用为准，不因阅读本文自动执行。主机复现、ESP只构建及完整参数见[协议说明§7](PROTOCOL_AND_BENCH_PLAN.md)；工具不会安装SDK/驱动或自动刷写。

1. 人工核板型/版次、供电和USB通路，逐板记录物理编号、端口/USB身份与可信MAC。完成目标编译及明确授权的逐板初始化后，建立本机hardware/eora_hub_400tb/bindings.local.json；[空模板](../../../hardware/eora_hub_400tb/bindings.example.json)中的示意值不能代填。该文件Git忽略，没有它只可枚举，不能自动打开未知设备。
2. 先一次枚举，再仅向physically_confirmed、allow_probe且身份一致的绑定做info。核nonce/固件/protocol/chip/MAC/boot/build，ready仍不认证400TB板型。
3. 用[disabled台架模板](../../../hardware/eora_hub_400tb/bench.example.json)另建实际计划，冻结2–5设备、单发送/单目的、run_id、次数/捕获窗并armed。逐板arm→接收/中继start→发送bench→全体stop，之后自动核证据、分析及追加。先低负载单跳，再五板发现、可追溯两跳/中继退出、事务/状态，最后上车。

以下为命令形状，UNIQUE-*及ACTUAL-*须换成获准的新run与真实计划；未在D窗口执行：

```powershell
python -B -m tools.espnow_hardware.hardware_tool --task-id H-001 --once --output simulation/outputs/H-001/UNIQUE-CHECK-ID
python -B -m tools.espnow_hardware.hardware_tool --task-id H-001 --once --probe --bindings hardware/eora_hub_400tb/bindings.local.json --output simulation/outputs/H-001/UNIQUE-PROBE-ID
python -B -m tools.espnow_hardware.hardware_tool --task-id H-001 --bindings hardware/eora_hub_400tb/bindings.local.json --bench hardware/eora_hub_400tb/ACTUAL-bench.json --output simulation/outputs/H-001/EXACT-PLAN-RUN-ID
```

bench输出目录末级须等于计划run_id；帧含112-byte头，总长≤250 byte、echo≥120，命令固件上限512 byte不含换行、H含换行保守限制。捕获≤45秒、内部截止55秒/合同60秒；count/interval乘积须落在捕获窗内。独立active设备stop和异常关闭处理已实现，精确命令及失败状态见协议说明，不以停止未确认当成功。

## 自动计算什么，哪些继续null

bench闭合采集后写不可变capture_context和配置，再调用已核分析器；context同run，log_sha256覆盖输入日志绝对路径与原字节hash。只有硬件来源、接收覆盖/计数、全体stop、无日志溢出/损坏等证据合格，才把有效PDR、协议payload goodput和成功echo子集P95追加到measurement_updates.jsonl，原measurements.json不覆盖。缺日志/生成数/接收计数/stop证据不导入有效实测；缺窗口的goodput、无有效echo的RTT以及无观测的距离/RF重试/airtime继续null。synthetic与硬件证据分开，--log只是外部日志hash/计数，不是测量导入。

日志原事务键为origin_id+origin_boot_id+seq，记录节点键为node_id+boot_id；tx_attempt只匹配本节点提交/回调，不是RF重试。frame_rx不算唯一端点交付。RTT只由同源同boot的generated和echo_correlation关联，t_us为毫秒乘1000，不跨板减时间。goodput扣ANN头但包含payload内echo元数据，不等于语义有效收益；PDR核心接纳分母与全部应用签发/拒绝分开。

## 到货检测与研究路线

[H-002](../../../coordination/tasks/H-002.md)已完成一次预检并review停写：opened_ports=0、waiting_hardware，六项测量null。每小时heartbeat h-eora仍PAUSED，最终验收与阶段提交后才启用，状态以任务卡/应用为准。电脑需开机、桌面应用与项目可访问；调度启用后每次--once≤60秒，仅枚举/已绑定info，不触发bench。五个有效握手仅表示台架准备状态，不代表五板无线通过。

五板功能/实测校准与百节点规模分开，原[网络研究框架](../NETWORK_RESEARCH_FRAMEWORK.md)、[实验总览](../EXPERIMENT_FRAMEWORK.md)及[NEXT_STEPS](../NEXT_STEPS.md)保留历史与后续规模路线，不启动旧仿真或模型预算。
