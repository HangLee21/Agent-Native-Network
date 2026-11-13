# 主动路由预热与移动性修补（已编译，未烧录未实测）

状态（2026-11-11）：

- ✅ **目标编译通过**：用保留的 ESP-IDF v5.5.1（`.local/espnow/E1-015`）构建 `field_agent`
  目标，`MID_HEADLESS=OFF`，**0 warning / 0 error**。
- ✅ **路由重路由单测通过**：主机 gcc 编译真实 `mid.c` + `source_route.c`，15 项断言全过
  （无路由→RREQ、缓存路由→DATA、首跳失败→一次重发现、同 `seq` 不二次重试、新 `seq` 独立配额）。
- ✅ **470 MHz 默认值确认进镜像**：`mid_edge.bin` 中 `470000000` 出现 1 次、`433000000`
  出现 0 次（`lora_ref` 的 `cfg` 静态初值）。
- ❌ **未烧录、未上电、无任何空口或移动性实测**。第 2、3 节的行为只有代码与主机单测支撑。

构建结果：`mid_edge.bin` = **951,712 B**（0xE85A0），1 MiB app 分区余 **0x17A60（9%）**；
新 `build_id` = `mid-lora-ref-v1-158bf1db1c611f9d024537bda6c51117068d66d0b97db67c64aff734934a948f`，
已部署旧镜像为 `mid-lora-ref-v1-6f62fc56a70718250928d818fadd2a943d965587acb6622d36dd04c4b6d7ce50`，
因此 `flash.py --current-build/--target-build` 与任何按 build_id 的守卫都要换成新值。

构建产物本次放在系统临时目录（`.local/` 与 `simulation/` 当前对会话不可写），属临时文件；
正式记录应在 `.local/` 恢复可写后按 `RUN_MANIFEST.json` 模板重跑并归档。

本文记录 2026-11-11 对 `field_agent` 候选的三处行为改动。改动前的行为与问题：

- 多跳路由**只在业务包发现没有缓存路径时**才由 `sr_submit` 触发 RREQ；上电后节点只有邻居图、
  没有路由，要等发生器恰好选中一个非直连目的地才“看起来”建了网。
- 路由缓存 `SR_CACHE_MS=10000` 过期后同样要等下一个业务包才重建。
- 发往下一跳的数据包只要断在第一跳就被丢弃，不做任何重试。
- 发送回调 1000 ms 不来会 `locked=1` 并 `stop_all()`，**必须物理复位**才能再开射频。
- 邻居失联判定最长 `ND_LOST_MS=12000` 才生效；发送失败不会立刻催促该邻居重新确认。

## 1 主动路由预热

实现在 `idf/main/field_runtime.inc` 的 `field_warm_tick()`，由 `field_tick()` 在
`active && route_mode` 之后调用：

| 常量 | 值 | 作用 |
|---|---:|---|
| `WARM_SLOTS` | 10 | 预热目的地上限 |
| `WARM_TICK_MS` | 500 | 两次 `sr_query` 之间的最小间隔（只发一条控制帧） |
| `WARM_KEEP_MS` | 4000 | 路由剩余有效期大于该值就跳过本轮 |
| `WARM_RETRY_MS` | 5000 | 查询失败后的重试间隔 |

暖列表来自两处，任何一处变化都会重建（`warm_sig` 比对，不逐 tick 重算）：

1. `agent.cfg.roster`（`field_config` 保存的 0..8 个业务目的地）；
2. `fg_service(gateway.pc_id)`，仅当 `gateway.agent_to_pc` 且本板**没有**当前 PC 租约
   （`!field_ip_live(now)`）；本板就是入口时那条路是直连 IP，不需要路由。

每次判定顺序：

```
直连邻居（nd_direct，state==2）        → 跳过，1 跳不需要路由
已有路由且剩余 > WARM_KEEP_MS          → 跳过
否则 sr_query()                       → 1 已有/直连；0 已发起 RREQ；-1 无空槽
```

只复用既有 `SR_ROUNDS=4`、`SR_DEADLINE=1500`、`SR_W=200`、TTL≤4 的有界 RREQ，
**不新增帧类型、不放大泛洪、不改变 `SR_HEADER`/`SR01` 编码**。没有业务流量时它也会运行，
所以“上电即建网”成立。

新增证据（`stats`）：

- `route_warm_queries`：实际发起的预热查询数
- `route_warm_hits`：直连或已有有效路由而未发查询的次数
- `route_warm_misses`：无空槽/取消失败次数
- 路由建立本身仍由既有 `route_request` / `route_selected` 事件逐条呈现

## 2 失效下一跳的即时探测

`idf/main/app_main.c` 新增 `neighbor_demand()`：路由数据帧的 ESP-NOW 回调返回**失败**时，
立刻向该下一跳单播一条 `ND01` HELLO，让邻居状态在毫秒级重新确认或降级，而不是等它下一个
2–3 s 的 HELLO，或等满 9 s 的 ACK 窗口。限速与显式 `neighbor_probe` 命令共用
`probe_after`（1 s），并且要求该邻居仍在表中。

只在“回调正常返回失败”时触发，不改变原来的作废语义：`sr_tx_result(ok=0)` 已经
`invalidate` 了该边。

## 3 单次本地重路由

`source_route.c` 的 `failed()` 增加一条分支：**本地发起的 DATA 在其第一跳失败**时，
先用 `retried_take()` 检查这个 `(boot, seq)` 是否已经重试过（`sr_node.retried`
是长度 `SR_PENDING` 的环），未重试过就调用 `sr_submit()` 重新发起一轮 RREQ，
把包放回 `pending` 等新路径。

- 每个包身份**只重试一次**，不会形成重试风暴；
- 只对本地业务数据生效；中继包和控制帧保持原行为（继续沿 `SR_ERROR`/`SR_SERR` 回传）；
- 新计数 `stats.route_retries`。

## 4 有界射频自愈

原来三处“发送回调 1000 ms 未到”都直接 `locked=1` + `stop_all()`，`radio_start()` 之后
一律拒绝，**必须人工复位**。对无人值守的移动节点这是最贵的一种失效。

现在这三处改为同时置 `heal_at = now + HEAL_DELAY_MS`，主循环开头调用 `radio_heal()`：

| 常量 | 值 |
|---|---:|
| `HEAL_MAX` | 3（每 boot 最多 3 次） |
| `HEAL_DELAY_MS` | 3000 ms 隔离窗 |

安全性依据：超时分支在置锁前已清 `waiting`，`stop_all()` 因此会执行
`esp_now_deinit()` + `esp_wifi_stop()`；ESP-NOW 会话被销毁后旧回调不可能再被匹配到
下一次发送，这正是原注释要防的场景。3 s 隔离窗是额外余量。第 3 次之后仍失败则打印
`radio_lock_final` 并保持锁定，交人工处理。

**输入溢出两处也已纳入自愈**（2026-11-12 补充）：`input_queue_overflow` 与 `uart_rx_overflow`
以前是永久锁，实测中会在主机反复开关串口时把节点锁成 idle —— 当天现场在 **B、E 两板上各复现一次**，
只有物理复位能恢复。现在它们与射频超时走同一套 `radio_heal()`：停射频 → 3 s 隔离窗 →
重新 `discovery_start()`，每 boot 合计最多 3 次，用尽才打印 `radio_lock_final` 并保持锁定。

`radio_heal()` 另外补了两点：有在途发送（`waiting`）时**推迟**这一次尝试而不是消耗它；
重启前确认 `close_radio()` 已执行，保证旧 ESP-NOW 会话的回调不可能匹配到新发送。
新增计数 `stats.input_overflow_total`。

边界要说清：输入溢出意味着主任务没来得及排空 16 深的输入队列，**重启射频并不修复根本原因**，
它只是避免“一块板静默掉线直到有人去按复位”。若现场仍频繁触发，应优先降低事件输出速率，
而不是继续放宽自愈次数。

新增事件与计数：`radio_healed` / `radio_heal_failed`（含 `attempt`、失败时 `code`）/
`radio_lock_final`；`stats.radio_heal_attempts`、`stats.radio_heal_pending`。

## 仍然没有解决（不要外推）

- `ND_CONFIRM_MS=9000` / `ND_LOST_MS=12000` 未改。第 2 节能在失败后**立刻**探测，
  但一个没有业务、也没有失败的静默失联邻居，仍要 12 s 才降级。
- 在途包只保留一条路径，重试是“整包重新发现”，不是逐跳局部修复；
  重试期间 `pending` 生命周期仍受 `SR_QUEUE_MS=250` 约束，第二轮未必来得及。
- 无应用层 ACK、无端到端确认，`destination_status` 仍恒为 `unconfirmed`。
- 容量未变：邻居 8 / 路由 8 / pending 8 / 候选 16。
- **预热需要一个目的地清单**。清单只来自 `field_config` 的 `roster`（最多 8 个）和 PC 逻辑地址。
  如果配置成 `dest_mode=observed`（目的地由观察动态决定），就没有固定清单，此时仍然只能靠
  业务包或 PC 的 `route` 查询触发发现——这不是遗漏，而是“没有目标就没有路由”的必然结果。
- 稳态开销：路由有效期 10 s、`WARM_KEEP_MS` 4 s，所以每个目的地大约每 **6 s** 发一次 RREQ。
  五节点/四个目的地下约 0.67 次/秒，是单条控制帧的量级，但没有做自适应退避；
  若后续发现占用偏高，应改成“按需延长 `WARM_KEEP_MS`”或只在失联后才持续预热。
- LoRa 侧完全未改（帧格式、角色、PHY 都不动）。

## 验收清单（必须由 H 在实板上做）

下面是新行为可核的最低要求。第 1 步已在本机完成，其余仍需 H 在实板上做。

1. ✅ **编译**（已完成）：ESP-IDF v5.5.1 构建 `field_agent`，0 warning / 0 error；
   四个新符号确在 ELF 中（`nm` 实测 `t field_warm_tick` 0x4200e688、
   `t neighbor_demand` 0x42010f64、`t radio_heal` 0x42010880、`t retried_take` 0x42016a24，
   另有 `warm_build` 0x4200e59c、`warm_remaining` 0x4200d9bc）。
2. **预热**：`route_config` + `field_config` 写入后**停掉发生器**（`field_pause`），
   冷启动五板；不发送任何业务，只在 8794/串口观察。预期：约 6–8 s 后出现
   `route_selected`，`route_warm_queries` 增长，`stats.routes` 中含有非直连目的地。
   对照组：旧镜像同样条件下 `route_selected` 应为 0。
3. **重路由**：一对非直连节点持续发包时，人为移走中间节点。预期新出现
   `route_retries` 增长，并且**至少一个原本会丢的包**在 `pending` 窗口内被第二轮 RREQ 救回，
   形成目的端 `rx_local`。判据只用目的端 `rx_local` + payload 一致。
4. **自愈**：构造一次发送回调缺失（断开或屏蔽该板），确认串口出现
   `callback_timeout` → `radio_healed`，且随后 `stats.radio` 重新为 true、
   `intent`/`mode` 回到 active；连续 3 次后应出现 `radio_lock_final`。
5. **回归**：五板原有 ESP-NOW 双向交付与 LoRa 上报不退化；`stats` 中原字段含义不变。

`firmware/mid_baseline/field_agent/INTERFACE.md` 与 `BASE_ROUTING.md` 尚未同步这些新增
`stats` 字段和事件，验收通过后再一并更新合同文本。
