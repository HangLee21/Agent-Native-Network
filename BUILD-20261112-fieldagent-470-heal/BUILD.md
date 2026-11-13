# 构建归档 v3：输入溢出可自愈（2026-11-12）

一次固件目标编译的产物归档，不是实验运行、也不是验收结论。仓库 `coordination/` 命名空间由 M 维护，
本目录未占用任何角色任务 ID。

## 与 v2 的差异

| 项 | v2（`…158bf1db…`） | v3（`…0a290c94…`） |
|---|---|---|
| `input_queue_overflow` / `uart_rx_overflow` | 永久 `locked`，必须物理复位 | 与射频超时共用 `radio_heal()`，3 s 隔离窗、每 boot 最多 3 次 |
| `radio_heal()` 前置检查 | 无 | `waiting` 时推迟一次尝试；重启前确认 `close_radio()` |
| `stats` | 无输入溢出计数 | 新增 `input_overflow_total` |

## 关键标识

- `build_id`：`mid-lora-ref-v1-0a290c94692323daf80f1be08ddaf2dbd9d1fae907ebbc914d429c574e240272`
- 镜像：`images/mid_edge.bin`，951,872 B（0xE8640），1 MiB app 分区余 0x179C0（9%）
- 镜像 SHA256：`e06c4499e04c4d394b2d51f7676d2789a95193f1fbefa759ec332454b5e623a5`
- 编译：0 warning / 0 error，ESP-IDF v5.5.1（保留工具链）
- 回滚目标：上一版 v2 镜像 `BUILD-20261111-fieldagent-470/images/mid_edge.bin`

## 实板验证（2026-11-12）

- 五板 app-only 烧录到 v3，每板一次写入、端口全关，写后 `build_id` 与 idle 态核对通过。
  证据：`simulation/outputs/H-019/20261112-14..18-flash-*-v3`。
- **LoRa 与 Wi-Fi 自启动**：五板 RTS/EN 硬件复位、零配置命令后，`mode=active`、`radio=true`、
  `group=31`、LoRa 角色 A=rx / B–E=tx、`freq=470000000`、`start_on_boot=true`、`gen 1/1` 全部恢复。
- **输入溢出自愈**：对 D 板连续灌 400 条命令不读取，触发 `input_overflow_total=62`。
  +7 s 时仍是 `locked=true`、`radio_heal_pending=true`（在 3 s 隔离窗内且被在途发送推迟）；
  随后的复查为 `mode=active`、`radio=true`、`locked=false`、`radio_heal_attempts=1`。
  **同一故障在 v2 上需要物理复位。**
  记录：`.local/mid/heal-check-20261112.json`。

## 仍未验证

- 自愈只在 D 上做过一次注入测试，未做多轮连发与「3 次用尽后永久锁」的边界验证。
- 输入溢出的根本原因是事件输出速率高于主任务排空 16 深队列的速度；自愈只是兜底，
  没有降低输出速率。若现场高频触发，应优先解决输出量而非依赖自愈。
- 没有做移动性、断链恢复、LoRa 距离/方向图与 470 MHz 合规功率的验证。
