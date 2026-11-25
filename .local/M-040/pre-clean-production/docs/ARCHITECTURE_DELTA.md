# 架构差异与改造边界

版本：2026-11-13。基于**代码级审计**，不是文档推断。

## 1 现状（审计确认，非文档转述）

| 层 | 实现 | 关键文件 | 状态 |
|---|---|---|---|
| ND | `ND01` hello(2–3 s)/ACK(500 ms 限速)、三态、9 s 确认 / 12 s 失效、`ND_PEERS 32` | `neighbors.c/h`、`app_main.c` | 【板】 |
| SR | `SR01` 60 B 头、payload ≤160、`path[5]`、TTL 4、RREQ 泛洪、RREP 反回、RERR、200 ms 窗口、10 s 缓存、`SR_SEEN 128 / SR_ROUTES 32 / SR_PENDING 16 / SR_OUT 12`、令牌桶 4/250 ms | `source_route.c/h` | 逻辑【板】；扩容【编】 |
| LoRa | `LRN1` 44 B 头 + n×20 B + CRC32、≤8 行、470 MHz/SF7/BW125/CR4-5、10 s±250 ms、无 ACK/重传、ALOHA | `lora_ref/runtime.c`、`lora_ref/port.c` | 【板】 |
| 定位 | `mt_position`（lat/lon e7、accuracy_mm、source、fix）、`MT01` 单跳广播、`position_set` 注入、`MT_ROWS 8` | `telemetry.c/h` | 【板】（仅位置，无速度/航向/高度） |
| 业务发生器 | 板内随机目的、2–3 s、≤160 B | `field.c/h` | 【板】 |
| 自启动 | 四路 NVS：`mid_route` / `mid_deploy` / `lr_ref` / `field_agent` | `app_main.c` | 【板】 |
| 移动/LET | 本轮新增 `mobility.c/h` | `mobility.c/h`、`test_mobility.c` | 【编】可编译、主机测试通过，**未接线路由** |

## 2 `ALGORITHM.md` 与实际代码/硬件的差异（必须并列，不擅自取舍）

| # | 文档说法 | 实际 | 处理 |
|---|---|---|---|
| 1 | §4.5 按「8 路上行 + 1 路下行」推导容量 | 板载**单颗 LR1121**，`port.c` 中 `set_rx`/`set_tx` 互斥、rfswitch 仅一组 → **8 路并行接收不可能** | 文档标注为「规划目标，非现有硬件能力」；改硬件前按单信道计算 |
| 2 | §1.3 自启动「已实测」 | 实测为 **RTS/EN 复位**后恢复；**拔电冷启动未验证** | 状态降为「复位已验证 / 冷启动未验证」 |
| 3 | §9 提及 `field_ip`（IP 入口） | 代码审计：`field_ip_load()`、`field_ip_tick()` **零调用点**，配置永远不加载 → 死代码 | 标为【未】，不得作为可用通路 |
| 4 | §6 跳数上限 4 对紧凑编队「不是瓶颈」 | 一致；但长链瓶颈记录为「发现时延 vs 250 ms 窗口」 | 一致，保留 |
| 5 | 表容量 32/128/16 | 代码一致（`neighbors.h`、`source_route.h`） | 一致 |
| 6 | 移动自适应 ND 定时【仿】 | 代码中确无实现，仅仿真 | 一致 |
| 7 | 「4 MB 器件余量 9%」 | 器件确为 **4 MB**（`esptool flash_id` 实测），但 `sdkconfig.defaults` 为 **2 MB** → 分区表按 2 MB 生成，app 仅 1 MiB | 新增改造项：改 flash size + 分区表 |
| 8 | 邻居容量 32 | ESP-NOW **注册 peer 上限 20**（IDF 常量），超过时 `esp_now_add_peer` 失败 | 表容量 ≠ 射频可寻址数；需在 P2 设计 peer 轮换 |

## 3 目标架构（四层）与模块依赖

```
mobility.c ──► (P2) nd_mobility ──► neighbors.c ──► source_route.c ──► app_main.c
   ▲                │                    ▲                 ▲                 │
   │                ▼                    │                 │                 ▼
telemetry.c      lrn2.c (P5) ────────► lora_ref/runtime.c ◄── lrc1.c (P5) ──┘
                                             ▲
                                             ▼
                                     lora_ref/port.c (单 LR1121)
```

依赖规则（本轮已按此实现）：

- `mobility.*` **不依赖** `neighbors/source_route/app_main`，只依赖 `mid.h`（`mid_id`）。
  因此可被主机测试、被仿真直接调用。
- `source_route` 不得反向依赖 `mobility`：路由若要使用 LET，必须在 `source_route` 之外
  计算后以参数传入（保持可回退）。
- LoRa 侧不依赖 Wi-Fi 侧任何模块，避免两平面耦合。

## 4 数据流

### 4.1 本地快速回路（毫秒–秒）

```
射频 RX ─► ND 更新 ─► 邻居三态 ─► 路由表有效性 ─► 逐跳转发
   │                    │
   └─ RSSI/帧质量 ──────┴─► (P1) mob_delivery ─► ETX/EWMA ─(shadow)→ 日志
位置输入(position_set/GNSS) ─► (P1) mob_self ─► 相对运动 ─► LET ─► risk(滞回)
                                                          └─(P1 只记录)
```

### 4.2 全局慢速回路（秒–分钟）

```
各节点 ─► LRN2 上报(带 sample_ms/seq/boot) ─► 网关 ─► 拓扑 + AoI 评估
                                                        │
                              LRC1（带 expire_at/version）▼
                                                  节点执行并回报 APPLIED/REJECTED
```

规则：网关输出**只能作为建议**，且必须携带年龄；节点若本地状态更新，可拒绝过期建议。

## 5 控制流与时序约束

| 事件 | 最大允许延迟 | 依据 |
|---|---|---|
| 邻居失效检测 | 12 s（可下调） | `ND_LOST_MS` |
| 单向→双向确认 | 9 s | `ND_CONFIRM_MS` |
| 路由发现（RREQ→RREP→选用） | 1500 ms 硬截止，200 ms 收敛窗口 | `SR_DEADLINE / SR_W` |
| 待发排队 | 250 ms（长链不足，P2 可配置） | `SR_QUEUE_MS` |
| LET 重算 | ≤ 1 s 或状态变化触发 | 本设计 |
| LRN2 上报 | 10 s 基线（P5 随 N 放大） | `T ≥ m·τ/ρ` |
| LRC1 生效 | 由 `apply_at` 指定，过期即弃 | 本设计 |

## 6 改造范围（明确边界）

| 模块 | 本轮 | P2 | P3+ |
|---|---|---|---|
| `mobility.*` | 新增（已完成） | 接入 ND | 参与选路打分 |
| `neighbors.*` | 不动 | 增加移动字段只读缓存 | 不变 |
| `source_route.*` | 不动 | 待发窗口可配置 | 候选打分、主备 |
| `lora_ref/*` | 不动 | 不变 | LRN2/LRC1 新帧 |

**线上格式（ND01 / SR01 / LRN1）本轮一律不改**，任何扩展必须新类型号 + 版本字段 + 兼容回退。
