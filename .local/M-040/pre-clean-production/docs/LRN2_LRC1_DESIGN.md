# LRN2 / LRC1：LoRa 全局遥测与下行控制设计

版本：2026-11-13。**本轮只做设计，不实现**（P5）。

## 0 硬件前提（先纠正，再设计）

| 事实 | 证据 | 后果 |
|---|---|---|
| 板载 **一颗 LR1121**，收发互斥 | `lora_ref/port.c`：`lref_port_rx`/`lref_port_tx` 使用 `set_rx`/`set_tx`；`rfswitch_cfg` 只有一组 rx/tx 引脚 | **8 路并行接收不可能** |
| 当前只有 ALOHA 上行 | `runtime.c` 按固定周期发帧，无时隙 | 30 节点需 ~3 分钟周期（见 §4.1） |
| 帧上限 208 B | 44 + 8×20 + 4 | LRN2 必然需要分片 |

**结论**：8 路上行 + 1 路下行是**目标架构**，不是现有能力。在换硬件之前，
应按**单信道 + TDMA** 设计与验收；换到多接收机后再按 8 信道扩容（§4.2）。

## 1 LRN2 上行遥测

### 1.1 分层结构

```
LRN2 帧 = 版本头(8 B) + TLV 块(可变) + CRC32(4 B)
版本头：ver(1) | type(1) | flags(1) | seq(2) | frag_index(1) | frag_total(1) | payload_len(1)
```

`type`：

| 值 | 名称 | 用途 | 频率 |
|---|---|---|---|
| 1 | `HEARTBEAT` | 存活、boot、AoI 基线 | 高频（10 s 基线） |
| 2 | `SNAPSHOT` | 完整状态，可分片 | 低频（30–120 s 或按需） |
| 3 | `DELTA` | 自上次快照的增量 | 事件触发 |
| 4 | `EVENT` | 单条异常事件（重启/断链/溢出） | 事件触发 |
| 5 | `CMD_ACK` | LRC1 执行反馈 | 收到命令后 |

### 1.2 TLV 字段表

| TLV | 名称 | 长度 | 内容 |
|---|---|---:|---|
| 0x01 | IDENTITY | 14 | mac(6) boot(4) node_class(1) fw_ver(3) |
| 0x02 | HEALTH | 10 | uptime_s(4) heap_free(2) heap_min(2) power_mv(2) |
| 0x03 | MOBILITY | 22 | lat_e7(4) lon_e7(4) alt_mm(2) ve/vn/vu(3×2) acc_m(2) vacc(2) sample_age_ms(2) |
| 0x04 | NEIGHBOR | 12+6n | count(1) 每项：peer_idx(1) state(1) rssi(1) pdr(1) etx(1) let_s(2) age_s(1) |
| 0x05 | ROUTE | 8+6n | count(1) 每项：dst_idx(1) hops(1) let_s(2) fails(1) |
| 0x06 | TRAFFIC | 12 | tx(2) rx(2) relay(2) drop(2) bytes_k(2) |
| 0x07 | QUEUE | 8 | txq(1) pending(1) high_water(1) avg_wait_ms(2) |
| 0x08 | ERROR | 8+ | code(2) count(2) at_ms(4) |

`peer_idx` / `dst_idx`：由网关在拓扑建立后下发 **索引表**，避免每次上报 6 B MAC。
索引表由 LRC1 下发（`SET_ID_MAP`），带版本号；节点未收到索引表时退化为英文 MAC 直报。

### 1.3 分片与重组

- 单帧载荷上限：`200 B`（留出 LoRa 前导与驱动余量）。
- `frag_total ≤ 8`（约 1.6 KB 快照上限），超出则本周期只报 `DELTA`。
- 网关按 `(mac, boot, seq, frag_total)` 重组，**任何一片缺失不覆盖上一份完整快照**；
  完整快照标记 `complete_at`，部分快照只并入增量。
- 重复片（同 `frag_index` + 同 `seq`）直接丢弃并计数。

### 1.4 AoI（信息年龄）

每条记录必须携带 `sample_age_ms`（源侧采样到发送的延迟）。网关侧：

```
report_age = sample_age_ms + (pc_receive_time − tx_time)
```

规则：

- `report_age > 30 s` 的物品标 **stale**，不得用于任何全局决策；
- 全局决策使用的位置/路由信息必须附 `report_age`，超过阈值时**拒绝下发强制改路**；
- 节点收到 LRC1 时若发现命令 `issued_at` 早于自己最近一次状态变化，可回 `REJECTED(stale)`。

## 2 LRC1 下行控制

### 2.1 帧结构

```
LRC1 = 版本头(8 B) + 目标(6 B) + 命令体(可变) + CRC32(4 B)
版本头：ver(1) | type(1) | flags(1) | cmd_seq(2) | payload_len(1) | reserved(2)
目标：target_mac(6)；广播用 ff:ff:ff:ff:ff:ff
```

命令体：

| 字段 | 长度 | 说明 |
|---|---:|---|
| command_id | 2 | 命令种类 |
| config_version | 2 | 单调递增，节点回退旧版本 |
| issued_at | 4 | 网关时钟（ms，相对网关 boot） |
| expire_at | 4 | 过期即丢弃，不得执行 |
| apply_at | 4 | 计划生效时刻，0 = 立即 |
| payload | ≤64 | 参数 |
| auth_tag | 4 | 阶段一：CRC32 后缀；阶段二：AES-CMAC（密钥预置 NVS） |

命令种类：

| ID | 命令 | 影响连通性 |
|---|---|---|
| 0x01 | `REQUEST_FULL_REPORT` | 否 |
| 0x02 | `SET_REPORT_PERIOD` | 否 |
| 0x03 | `SET_TRAFFIC_RATE` | 否 |
| 0x04 | `SET_MAX_HOPS` | **是** |
| 0x05 | `SET_ROUTE_POLICY` | **是** |
| 0x06 | `SET_RELAY_PREFERENCE` | **是** |
| 0x07 | `SET_LINK_RISK_THRESHOLD` | 否（仅本地判定） |
| 0x08 | `SET_ID_MAP` | 否 |
| 0x09 | `CHANNEL_PREPARE` / `CHANNEL_COMMIT` | **是（最高危）** |

### 2.2 执行状态机

```
RECEIVED ─► VALIDATED ─► ACCEPTED ─► APPLIED
    │            │           │
    └─► REJECTED(原因)  └─► REJECTED(过期/版本旧/目标不符/鉴权失败)
                             └─► FAILED(执行异常，含回滚)
```

必须实现：

1. **去重**：`(target_mac, boot, config_version)` 三元组，重复命令不重复执行。
2. **过期**：`now > expire_at` → `REJECTED(expired)`，绝不"补执行"。
3. **重放保护**：`config_version` 小于已执行版本即拒绝；重启后从 NVS 恢复已执行版本。
4. **目标校验**：`target_boot` 不符（节点已重启）→ 拒绝，网关需重新获取 boot。
5. **反馈**：`APPLIED` 后必须发 `CMD_ACK`，网关据此统计 `Command Execution Ratio`。

### 2.3 高危命令：PREPARE / COMMIT

信道切换、最大跳数变更等会切断全网的命令，采用两阶段：

```
网关 ──PREPARE(v, T_switch)──► 节点：加载新配置但不生效，回 PREPARED
网关收到 ≥80% PREPARED ──COMMIT(v)──► 节点在 apply_at 同步切换
网关在 T_switch + margin 内未收到足够的 APPLIED ──► 下发 ROLLBACK(v)
```

节点侧：`PREPARE` 保存在独立槽位，`COMMIT` 才替换运行配置；
若 `T_switch` 过后仍未收到 `COMMIT`，**自动丢弃 PREPARE 并保持原配置**。

## 3 LoRa 服务边界（硬约束）

LoRa **只做**慢速全局协调与管理：

- 允许：拓扑汇总、策略下发、周期调整、按需详细报告、全局告警。
- **禁止**：毫秒级邻居维护、飞控安全控制、实时路由修复、业务数据转发。

任何依赖 LoRa 时延（≥ 秒级）的功能都不得进入安全链路。

## 4 容量规划

### 4.1 当前硬件（单信道，ALOHA）

`m = N−1`，单帧 ToA `τ(208 B) = 328 ms`，目标占空 `ρ`：

| N | 单帧 ToA | ρ=0.05 时周期 | 实测/推算送达 |
|---:|---:|---:|---|
| 10 | 328 ms | 59 s | 单信道 10 s 时 ≈ 0.65（实测 5 节点 0.85） |
| 20 | 328 ms | 125 s | — |
| 30 | 328 ms | **190 s** | 实测 0.057（10 s 周期，单信道） |

### 4.2 当前硬件（单信道，TDMA）——推荐的现实方案

TDMA 消除碰撞，`ρ` 可接近 1：

```
T_superframe ≥ N·(τ + guard) + τ_beacon
N=30, τ=328 ms, guard=20 ms, beacon=82 ms
T ≥ 29×348 + 82 = 10.2 s
```

**结论：单信道 + TDMA 就能在 ~10 s 内完成 30 节点的 LRN1 级快照**，
不需要 8 条物理信道。8 信道的价值在于把 10 s 压到 ~2 s，或承载更大的 LRN2 帧。

### 4.3 规划中的 8 上行 + 1 下行（需换硬件）

`m = ceil((N−1)/8)`，`T ≥ m·τ/ρ`：

| N | m | ρ=0.05 周期 |
|---:|---:|---:|
| 30 | 4 | **26 s** |
| 30 | 4 | ρ=0.5 → 2.6 s |

※ 该表是**设计目标**，在单 LR1121 上不可实现。

## 5 超帧与调度（P5）

```
┌ beacon(下行) ┬ slot0 ┬ slot1 ┬ … ┬ slot(N-1) ┬ CMD 窗口 ┬ 竞争窗口 ┐
   82 ms        348 ms  348 ms      348 ms         可变       剩余 15%
```

- `beacon` 携带：超帧号、时隙表版本、各节点时隙、下行命令队列摘要。
- **漏收 beacon 的节点**在超帧尾部 15% 竞争窗口用 ALOHA 上报（仿真验证：2% 漏收率下整体仍 0.95）。
- 下行命令优先于上行数据：`CMD 窗口` 固定预留，避免命令被上报挤占。
- 时隙表变更必须走 `SET_SLOT_MAP` + `config_version`，且**只在超帧边界生效**。

## 6 未确认事项

1. LR1121 是否支持 >208 B 的 LoRa 载荷（需实测）；表按 200 B 设计。
2. 8 信道硬件的具体形态（多 SX126x / 8 通道集中器）与串口协议**未定**。
3. 下行鉴权密钥的注入方式（NVS 预置 vs 现场配置）未定。
4. 网关时钟与节点时钟无同步机制，`issued_at/expire_at` 只能使用**相对时长**
   （如 `expire_after_ms`），这一点在实现前必须重新定义字段语义。
