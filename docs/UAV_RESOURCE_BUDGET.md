# 30 节点算法：板端资源预算与证据

2026-11-14，D-031；依据 [工程合同](../coordination/handoffs/M-036-engineering-contract.md)。这是资源筛选基线，不是部署验收。板上运行版本、2026-11-13 的旧目标 ELF、已构建未烧录的组帧修复包与未来 E1 候选必须分别比较；不把主机 sizeof 或仿真执行时间当作 ESP32-S3 数值。

## Flash、内部 RAM 与 PSRAM

| 项 | 已核对证据 | 预算或尚缺 |
|---|---|---|
| 外部 Flash | 实板盘点 4 MiB；[4MB 构建记录](../BUILD-20261113-4MB-notxblock/BUILD.md)为 2267bc60，ESP-IDF 5.5.1，目标 4 MiB。 | Flash 不是 SRAM。原 NVS 0x9000/0x6000、PHY 0xF000/0x1000、factory 0x10000/0x3F0000（4,128,768 B），见[分区表](../BUILD-20261113-4MB-notxblock/partitions.csv)。 |
| 候选 app Flash | [LRN1 修复包](../BUILD-20261113-lrn1-cap/BUILD.md) cd389e57 镜像 953,520 B、未烧录；构建记录报 0 warning/error。 | factory 剩余 3,175,248 B，约 76.9%；按至少 15% 分区余量的内部目标，app 最多 3,509,452 B（取整向下），相对该镜像最大净增 2,555,932 B。该算术不表示候选已经编译或板上采用该包。 |
| 静态目标 RAM | 对已归档、非 host 的 [2267bc60 ELF](../BUILD-20261113-4MB-notxblock/mid_edge.elf)，以 IDF 工具链 `xtensa-esp32s3-elf-size -A` 只读：`.dram0.data` 19,304 B、`.dram0.bss` 105,000 B、`.iram0.text` 103,675 B、vectors 1,028 B。 | 这些 section 不等于可用堆；IRAM/DRAM 映射、保留区和 dummy 段不能简单累加或拿芯片标称 SRAM 减法作为空闲内存。需同版本 IDF size/map 说明可用区域及增量。cd389e57 归档未见配套 ELF/map，不借旧 ELF 冒充该版。 |
| 运行期堆 | 历史 [180 s 实板记录](../simulation/outputs/H-019/20261113-20-soak-stable/SOAK.json)为旧 31279b6f 版本、5 板 active/radio，A 为 LoRa RX、B–E 为 TX；heap 约 90,448–90,588 B。 | 是该记录的单次数值，不是整个试验最低水位；无法由此证明当前 30 节点、Wi-Fi + LoRa + OLED + 主机事件同时满载余量。旧文约 103 KB 为更早版本，不与它相加。所需启动后空闲堆、低水位、最大连续块、各能力域、堆碎片均待新板测。 |
| PSRAM | [默认配置](../firmware/mid_baseline/field_agent/idf/sdkconfig.defaults)写 `CONFIG_SPIRAM` 未启用；归档 sdkconfig 中 `SOC_SPIRAM_SUPPORTED` 为芯片能力标志，不证明外挂芯片存在或可用。 | 暂按 **0 B 可用 PSRAM** 决策；当前设备检测、配置和运行时可分配容量均未重新验证。 |

内部目标是最坏运行期保留至少 25% 可用内部堆基线、各任务栈至少留 25%；它们是设计目标，不是当前实测通过。若未来在相同功能/阶段测得内部堆基线 H，候选运行期最低可用内部堆应至少 0.25H；总空闲堆不足以反映内部/DMA 可分配能力。旧记录最低单次 90,448 B 仅用于说明量级，不当作 H 或可分配预算。

## 固定表、队列与目标符号

从 [source_route.h](../firmware/mid_baseline/field_agent/source_route.h)、[neighbors.h](../firmware/mid_baseline/field_agent/neighbors.h)、[field.h](../firmware/mid_baseline/field_agent/field.h) 读取当前源码上限；以下是结构容量，不等于某目标包每项字节大小：

| 类别 | 固定容量 / 行为边界 | 对 30 节点选型的影响 |
|---|---|---|
| ND / 路由 peer | ND 32、SR peer 32；ESP-NOW SDK `ESP_NOW_MAX_TOTAL_PEER_NUM=20` | 29 个潜在邻居可进入软件表并不意味着能全部驻留硬件 peer；广播及加密 peer 配置也会占用或限制 SDK 配额。须统计添加失败、迁移、淘汰和饥饿；不能无限扩表或假设 29 同时可发。 |
| 路由 | 32 路由、路径最多 4 跳（path[5]） | 距离图直径超过 4 跳时即使几何连通也不一定协议可达；额外备份路由要预算存储、失效和老化。 |
| 等待与发现 | pending 16，轮次 4、每轮候选 16；发现期限 1500 ms，出站队列 12、队列期限 250 ms | 250 ms 仅适用固件排队阶段，不能当发现总期限；容量满应拒绝/计数，不靠无限等待或加深队列掩盖时延。 |
| 去重与事件 | seen 128、delivery 64、SR 事件 32；agent 记录 128、源去重 16 | 长期成员更替、boot 重启和溢出应明确淘汰及观测缺口；全局历史不限量在板端不可用。 |
| 其他 | LoRa 配置/帧/事件队列为 1/1/8；OLED 快照队列 1；输入队列 16，UDP 输入队列 8×1025 B | 队列存储及 RTOS 元数据/动态分配需要目标堆证据；不要把静态结构和堆重复计数。输入大队列与控制峰值并发可能挤压剩余堆。 |

SDK [esp_now.h](../.local/espnow/E1-015/sdk/esp-idf-v5.5.1/components/esp_wifi/include/esp_now.h) 给总 peer 上限 20；具体已占槽位和加密容量需按实际配置核实。当前 [LRN1 组帧](../firmware/mid_baseline/field_agent/lrn1_frame.c)最多 8 行；30 节点时必须处理截断与逐邻居年龄，不能假设每帧囊括 29 个邻居。非双向优先在持续至少 8 个非双向邻居时可能令其他行饥饿，不能承诺无条件轮转覆盖。

使用目标工具 `xtensa-esp32s3-elf-nm -S --size-sort` 读取同一个归档 2267bc60 ELF 的静态符号：`router` 0x6a08 = **27,144 B**，`neighbors` 0x940 = **2,368 B**，`agent` 0x6df0 = **28,144 B**，`txq` 0x1080 = **4,224 B**。四者属于目标 ELF 静态对象，合计 61,880 B，已包含于 section，不要再加到 `.bss`。这只是历史包目标 ABI 对象，不能替代最新源码每个成员的 sizeof，亦不等于动态堆、功能运行峰值或可回收额度。新的 128 条 agent 记录与数据包载荷可能显著占内存；任何缩减必须同步定义覆盖、回放和观测能力变化。

## 栈与处理时间

[归档 sdkconfig](../BUILD-20261113-4MB-notxblock/sdkconfig) 主任务配置 16,384 B；当前源码分别创建 UART 6,144 B、LoRa worker 6,144 B、OLED worker 6,144 B、UDP task 4,096 B。它们是各构建/源码的配置量而非高水位；功能是否启用、实际创建成功、各任务水位及全部系统任务尚待对应版本核对。总和不能与静态 section 或已使用堆简单相加。`field_ip_status` 等提供 heap 和栈字段，仍需对照当前 ESP-IDF 的 API 单位和调用任务后使用；不能把单个 caller 水位代表所有任务。必须逐任务给已配置栈、最小剩余和 25% 阈值，覆盖拥塞、重试、LoRa/OLED 与主机事件并发。

当前 `route_tick` 至多扫描 32 个 ND 项并调用 `sr_neighbor`，需核 `sr_neighbor` 的表扫描及 `sr_tick` 的上界；组帧扫描最多 32 项、输出最多 8 行。候选必须写明每收到帧、每次 tick、每次发现的最坏循环次数，避免 30 节点下无界全图计算、同步等待串口/LoRa/NVS 或按消息无界分配。历史 `route_process_max_us` 若存在只覆盖核心 tick/receive，不能代替完整收发墙时；host 耗时不能映射成 S3 的实时耗时。

## 交给 E1 的隔离构建与后续板测

1. 在 E1 独占隔离构建产物中记录源码与配置 hash、编译器版本/flags、分区表、ELF/map、IDF size 报告；对**相同配置**的基线与候选逐类给 `sizeof`、静态 RAM 和 app Flash 净增。若包未含 map/ELF，标记待补，不能用旧版本替代。
2. 明确 29 个潜在邻居遇 SDK 20 peer 时的保留/替换和最坏扫描数；列 pending/round/route/seen/out/event 与 LoRa/主机队列满时的拒绝、过期、事件覆盖。记录候选算法的额外常驻状态及每条控制消息成本。
3. 后续由硬件负责人在同一固件、相同启动条件下测启动后基线和多功能同时运行的内部堆 low-water、最大连续块、逐任务 stack high-water、各队列高水位、最坏 tick/callback/端到端处理时延；重复高密度/突发/换邻居/网关断联、长时碎片/泄漏。区分功能启动成功与资源余量达标。
4. 当前无完整目标候选增量与并发运行期水位，因此不能判定 RAM/堆/栈 25% 目标通过，也不能声称 30 板部署通过。本卡只读历史构建与记录，没有编译、实机或新测试。
