# 实现状态（代码级审计结果）

状态定义：**【板】**已在真实硬件运行；**【编】**已编译进镜像、未实板验证；**【仿】**仅仿真；
**【未】**未实现；**【死】**代码存在但无调用点。

日期：2026-11-13。审计方式：读源码 + 编译 + 实板 `esptool flash_id` / `info` / `stats`。

## 1 Wi-Fi 控制面（ND）

| 机制 | 状态 | 位置 | 证据 |
|---|---|---|---|
| Hello 2–3 s、ACK 500 ms 限速 | 【板】 | `app_main.c` / `neighbors.c` | 五板 `control_hello_*` 计数单调 |
| 三态 LOST/HEARD/BIDIRECTIONAL、9 s/12 s | 【板】 | `neighbors.h` | `ND_CONFIRM_MS/ND_LOST_MS` |
| 只有双向可作下一跳 | 【板】 | `source_route.c:live()` | 单元测试 + 实板 |
| `ND_PEERS 32` | 【编】 | `neighbors.h` | 编译通过；实板 `route_core_bytes=27144` |
| **ESP-NOW peer 上限 20** | 【未】 | — | IDF 常量；**无对策代码** |
| 移动自适应定时 | 【仿】 | `sim_alg.py` | 固件无速度输入 |

## 2 Wi-Fi 数据面（SR）

| 机制 | 状态 | 位置 |
|---|---|---|
| `SR01` 60 B 头 / payload ≤160 / path[5] / TTL4 | 【板】 | `source_route.h` |
| RREQ 泛洪 / RREP 反回 / RERR | 【板】 | `source_route.c` |
| 200 ms 收敛窗口、候选选最短 | 【板】 | `source_route.c` |
| 路由缓存 10 s + `first_boot` 绑定 | 【板】 | `source_route.c` |
| 交付判据 `rx_local` + 字节一致 | 【板】 | `app_main.c` |
| 表容量 32/32/128/16/12 | 【编】 | `source_route.h` |
| 路由发现令牌桶 4/250 ms | 【编】 | `source_route.c:rreq_take` |
| 待发窗口 250 ms | 【板】 | 长链不足（已知） |
| 扩展环 RREQ | 【仿】 | 未进固件 |

## 3 LoRa 控制面

| 机制 | 状态 | 位置 |
|---|---|---|
| `LRN1` 44+20n+CRC、≤8 行、470 MHz | 【板】 | `lora_ref/runtime.c`、`port.c` |
| 10 s ±250 ms、无 ACK/重传 | 【板】 | `runtime.c` |
| 角色/频率 NVS 自启动 | 【板】 | 实测：复位/重新供电后自动恢复 |
| **8 上行 + 1 下行** | 【未】 | **硬件不支持**（单 LR1121） |
| 调度化上行（TDMA） | 【仿】 | `sim_gw.py`：0.67→0.95 |
| LRN2 / LRC1 | 【未】 | 仅设计（`docs/LRN2_LRC1_DESIGN.md`） |

## 4 移动感知（本轮新增）

| 机制 | 状态 | 位置 | 证据 |
|---|---|---|---|
| Mobility State 抽象 | 【编】 | `mobility.h` | 编译 + 主机测试 |
| 相对位置/相对速度 | 【编】 | `mobility.c:offset_mm` | 测试：100 m/20 m/s 精度 <1% |
| LET 三维求解 | 【编】 | `mobility.c:mob_predict` | 测试：解析值 11.0 s 与实测 10.8–11.2 s |
| 不确定性带 + 置信度 | 【编】 | 同上 | 测试：band 包住估计 |
| 风险三态 + 非对称滞回 | 【编】 | 同上 | 测试：升级立即、降级等 2 s |
| **置信度门限（防振荡）** | 【编】 | `MOB_MIN_CONFIDENCE` | 评估：稳定编队误报 596→0 |
| 链路质量 EWMA/ETX | 【编】 | `mob_delivery` | 测试：干净链路 ETX=1.00 |
| Shadow 记录 | 【编】 | `mob_shadow_line` | JSON 单行，短缓冲拒绝 |
| 评估工具 | 【已运行】 | `tools/mid_baseline/mobility/let_shadow.py` | S1–S6 结果见 `EXPERIMENT_PLAN.md` §4 |
| **接入 ND / 路由** | 【未】 | — | 本轮禁止 |
| GNSS/飞控真实输入 | 【未】 | — | 硬件接口未接入 |
| 节点间移动状态传递（ND02/MT02） | 【未】 | — | 只有 `MT01` 位置（无速度） |

## 5 硬件核查结论

| 项 | 结论 | 依据 |
|---|---|---|
| 芯片 | ESP32-S3（QFN56, rev v0.2），无 PSRAM | `esptool` / `CONFIG_SPIRAM not set` |
| Flash | **实测 4 MB**，但配置 2 MB | `esptool flash_id` vs `sdkconfig.defaults` |
| app 分区 | 1 MiB（余 9%） | 构建输出 |
| 镜像 | 952,640 B（含 mobility.c） | 构建输出 |
| LoRa 射频 | **单 LR1121**，收发互斥、单天线组 | `lora_ref/port.c` |
| ESP-NOW peer | 上限 20 | IDF `esp_now.h` |
| GNSS | **无驱动**；只有 `position_set` 注入与 `MT01` 单跳位置广播 | 代码审计 |

## 6 硬件阻塞项

1. **8 路并行接收不存在** → 需换网关硬件；在此之前按单信道 TDMA 设计。
2. **无 GNSS/飞控接口** → 速度/航向只能注入或回放，不能称实测。
3. **无实测 PDR-距离曲线** → `range_mm=120 m` 是几何假设，LET 不能当真实链路寿命。
4. **实板只有 5 块** → N=10/20/30 只能仿真，或分批拼测。
5. Flash 配置与器件不符 → 需改 `CONFIG_ESPTOOLPY_FLASHSIZE_4MB` + 自定义分区表（会改变烧录流程）。

## 7 本轮实际改动

| 文件 | 改动 |
|---|---|
| `firmware/mid_baseline/field_agent/mobility.h` | 新增：状态结构、LET/风险接口、阈值常量 |
| `firmware/mid_baseline/field_agent/mobility.c` | 新增：相对运动、LET、不确定性、滞回、阴影序列化 |
| `firmware/mid_baseline/field_agent/test_mobility.c` | 新增：26 项主机测试 |
| `firmware/mid_baseline/field_agent/idf/main/CMakeLists.txt` | 加入 `mobility.c/h`（编译检查；未被引用） |
| `tools/mid_baseline/mobility/let_shadow.py` | 新增：合成轨迹生成 + LET 评估 |
| `docs/*.md` | 新增七份规划文档 |

**未改动**：`app_main.c` 的路由逻辑、`source_route.*`、`neighbors.*`、
`lora_ref/*`、任何线上帧格式。**五节点基线的行为与上一版完全一致。**

## 8 回归验证

| 项 | 结果 |
|---|---|
| 主机测试 `test_mobility` | 26/26 通过 |
| 固件编译（全新构建目录） | 0 warning / 0 error，952,640 B |
| 构建 ID | `mid-lora-ref-v1-111f2d676bab352fdf0839e0e55614ea293dfe08568e6fab4ab36275a37a5f23` |
| 镜像 sha256 | `44d45eae6b5363c45797b1480f95e3f89cd4d9f2bad91895b4313a76f34e997d` |
| 链接器符号 | `nm` 查无 `mob_*` → **模块被链接器整体丢弃**，镜像字节与体积不变 |
| 五板运行基线 | 未在本轮重新烧写（mobility 无调用点，行为不变） |
| LoRa 拓扑 | 本轮未重测（硬件能力未变） |

> 说明：`mobility.o` 编译通过但未被任何代码引用，链接器按需丢弃，因此
> **固件体积与行为与上一版完全一致**。这是本轮刻意选择的接入方式：先证明模块可编译、
> 可测试，再在 P2 用开关接入 ND，避免在无验证的情况下改动稳定基线。

## 9 后续修订（同日，用户确认后执行）

| 项 | 状态 | 证据 |
|---|---|---|
| flash 改为 4 MB + 自定义分区表 | **已完成并实板验证** | app 分区 4032 KB（余 77%）；NVS 偏移未变，五板 group/ch/LoRa/autostart 全部自动恢复 |
| 事件输出改为非阻塞 | **已完成并实板验证** | 60 s 无人读串口：4/5 板块 `input_overflow_total` 增量 **0**（修复前 +30…+62） |
| E 板仍周期性溢出 | **未解决** | `uart_tx_drops=0` 排除输出阻塞；`send_callback_timeouts=9` 最高；处理耗时正常 → 待抓帧型分布 |
| 八通道网关 | **待采购** | 规格见 `LORA_GATEWAY_REQUIREMENTS.md` |
| 真实移动输入 | **仍缺失** | 无飞控/GNSS 接口；LET 继续只用合成/回放数据 |

当前板上固件：`mid-lora-ref-v1-2267bc60…`（见 `BUILD-20261113-4MB-notxblock/BUILD.md`）。
