# 稳定版构建（2026-11-13）：从根上消除"几十秒就锁死"

## 结论

之前"几十秒锁死"不是自愈次数不够，而是**把背压当成了故障**，并且**每帧打印放大了主任务负担**。
本轮改的是机制，不是时间窗。

## 关键标识

- `build_id`：`mid-lora-ref-v1-31279b6f51075d10ac483d0b25c8a180044fbb538a5f6e3ad1085f74afeb2b49`
- 镜像：`images/mid_edge.bin`，**952,352 B**，SHA256 `02e7cc01a1406584d33f44a93f533d469356c7881ebcaee7a89202e72826aaec`
- 编译：ESP-IDF v5.5.1，**0 warning / 0 error**
- 回滚：`BUILD-20261112-fieldagent-algv2/images/mid_edge.bin`（`…45ed1aac…`）

## 根因

主任务要处理三件事：路由/ND 逻辑、串口命令、以及**每个收到的帧都打印一条完整 JSON**。
`inputs` 队列只有 16 深，而 `input` 结构体约 1.1 KB（含 1025 B 的行缓冲）。
一旦主任务被串口写或路由计算拖住，ESP-NOW 回调里的 `xQueueSend(...,0)` 就会失败 →
`callback_drops` 增加 → 旧代码把**背压当成故障**：`locked=1; stop_all()`，整块板下线。

同时 UART 读任务在队列满时会阻塞 50 ms，反过来又造成 UART 侧溢出。

## 三处结构性改动

| # | 改动 | 位置 | 为什么这是根因修复 |
|---|---|---|---|
| 1 | 输入队列溢出**只计数、丢帧，不再停射频** | `app_main.c` 主循环 | 溢出是背压，不是射频故障。真正丢掉的发送回调由已有的 1 s 超时路径处理，不需要整机下线 |
| 2 | ND 帧（hello/ACK）**不再逐帧打印 JSON**，但保留 RSSI 采样 | `rf_observation()` | 邻居状态已在 `stats`/`neighbors`/LRN1 里可见；逐帧打印是纯开销 |
| 3 | UART 读任务**永不阻塞**在满队列上（50 ms → 0） | 串口读循环 | 阻塞会反向造成 UART 溢出与更大积压 |

时间窗自愈（每 2 分钟 3 次）作为**兜底**保留，只对"发送回调真的没来"生效。

## 实板验证（5 块板，约 5 分钟）

| 板 | 模式 | radio | locked | 溢出 | 自愈 | hello_rx | LoRa | heap |
|---|---|---|---|---|---:|---:|---|---:|
| A | active | on | **false** | **0** | **0** | 406 | rx，已收 **119 帧** | 90.6 KB |
| B | active | on | false | 0 | 0 | 419 | tx 34 | 90.5 KB |
| C | active | on | false | 0 | 0 | 417 | tx 32 | 90.6 KB |
| D | active | on | false | 0 | 0 | 414 | tx 30 | 90.4 KB |
| E | active | on | false | 0 | 0 | 417 | tx 28 | 90.6 KB |

改动前：同样强度的运行下，B、E、A 各在几十秒内 `locked=true`，`input_overflow_total` 4–5 次，
其中 E 的 `radio_heal_attempts` 用尽到 3 后永久锁死、必须物理复位。

改动后：**三分钟压力运行零溢出、零自愈、零锁死**。

证据：`simulation/outputs/H-019/20261113-20-soak-stable/SOAK.json`

## 仍未解决

1. **8766 控制台被先前的失败记录锁住**（`cleanup_unconfirmed` + migration marker）。
   恢复需要原始失败记录里四板的 stop 证明（当时 D/E 为 false）与 A 的新鲜停止证明。
   现有实现不支持"事后重新验证全部参与板"的恢复路径。8767 已用独立状态目录启用。
2. **控制台受控发送与自主模式互斥**：`start` 返回 `deployment_present_clear_first`，
   必须先 `route_clear`/`deployment_clear`，会清掉现场配置。
3. 长链首包丢失（`SR_QUEUE_MS=250 ms` 小于远距离发现时延）未改。
4. Wi-Fi 仍无 CSMA/碰撞模型，仿真中的 PDR 仍是乐观上界。
