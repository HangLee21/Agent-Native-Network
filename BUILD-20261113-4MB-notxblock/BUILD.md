# BUILD 2026-11-13：4 MB 分区 + 非阻塞事件输出

## 关键标识

| 项 | 值 |
|---|---|
| build_id | `mid-lora-ref-v1-2267bc60fa3a31b1d02be4ba5c3fd5d11a171fc3b2e3b17d7f7aa6231cf1b7c2` |
| app 镜像 | 953,008 B，sha256 `23c927542fefcb7b4ac9a07f876b9f24c7bd1318fb5c8100bdf2f4b394531c9e` |
| 分区表 | `partitions.csv`（已归档） |
| 编译 | ESP-IDF v5.5.1，0 warning / 0 error |
| 烧录方式 | **全量**（0x0 bootloader + 0x8000 分区表 + 0x10000 app）；后续可恢复 app-only |

## 改动 1：flash 4 MB + 自定义分区表（用户已确认）

- 器件实测 4 MB，但 `sdkconfig.defaults` 写的是 2 MB → 默认分区表把 app 限制为 1 MiB。
- 改为 `CONFIG_ESPTOOLPY_FLASHSIZE_4MB` + `partitions.csv`：

| 分区 | 偏移 | 大小 |
|---|---|---|
| nvs | 0x9000 | 24 KB（**与旧表一致**） |
| phy_init | 0xF000 | 4 KB |
| factory | 0x10000 | **4032 KB** |

- app 余量：**9% → 77%**（`Smallest app partition is 0x3f0000`）。
- **NVS 偏移/大小未变**，实测五板烧完后 `group=31 / channel=11 / LoRa 角色 / autostart` 全部自动恢复。

## 改动 2：事件输出不再阻塞主循环

**根因**：`output()` 用 `puts()` 写 stdout，底层是 4 KB 的 UART TX 环；
主机停止读串口 → 环满 → `puts()` 阻塞 → 主循环停摆 → 输入队列溢出 → 丢发送回调。

实测证据（修复前）：拆掉所有串口读取，60 s 内 A +42、C +62、D +30 次 `input_overflow_total`；
C 在无读取时 `stats` 直接超时。

**修复**：`output()` 先用 `uart_get_tx_buffer_free_size()` 检查剩余空间，
不足则丢事件并累加 `stats.uart_tx_drops`，绝不阻塞接收路径。

## 实板验证（五板，`2267bc60`）

| 板 | 模式 | locked | 60 s 无读取时 ovf 增量 | uart_tx_drops |
|---|---|---|---:|---:|
| A | active | false | **0** | 0 |
| B | active | false | **0** | 0 |
| C | active | false | **0** | 0 |
| D | active | false | **0** | 0 |
| **E** | active | false | **+80** | 0 |

修复前同条件下 4/5 板块持续溢出；修复后 4/5 归零。**E 仍异常**，见「未解决」。

## 未解决

1. **E 板仍周期性溢出**：`send_callback_timeouts=9`（五板最高），但 `route_process_max_us=1738 µs`、
   `input_overflow_total` 持续增长，且 `uart_tx_drops=0`（说明不是输出阻塞）。
   下一步：抓 E 的 `native.jsonl` 看溢出时刻的帧类型分布，判断是否与其邻居拓扑/重传有关。
2. ELF/MAP 未入库（`.gitignore`），仅本地归档。

## 回滚

上一版（1 MiB 分区）：`BUILD-20261113-fieldagent-stable/images/` 的
`bootloader.bin` + `partition-table.bin` + `mid_edge.bin`，全量烧回即可。
