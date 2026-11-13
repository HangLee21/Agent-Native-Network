# 固件版本沿革（field_agent）

build_id 与 sha256 均**从归档镜像中直接提取**，不是手抄。
每版的改动、验证与回滚目标见对应 `BUILD-*/BUILD.md`。

## 版本表（新 → 旧）

| # | build_id 前 8 / 尾 12 | 镜像大小 | sha256（前 12） | 归档目录 | 要点 |
|---|---|---|---:|---|---|
| 5 | `2267bc60` / `a6231cf1b7c2` | 953,008 B | `23c927542fef` | `BUILD-20261113-4MB-notxblock` | **4 MB 分区（app 4032 KB）+ 事件输出非阻塞** |
| 4 | `31279b6f` / `5f74afeb2b49` | 952,352 B | `02e7cc01a140` | `BUILD-20261113-fieldagent-stable` | 溢出背压语义、回调超时静默门控、自愈时间窗 |
| 3 | `45ed1aac` / `904a40026b3c` | 952,336 B | `ec2fdc9e0f31` | `BUILD-20261112-fieldagent-algv2` | 表容量 32/32/128/16 + 路由发现令牌桶 |
| 2 | `0a290c94` / `9c574e240272` | 951,872 B | `e06c4499e04c` | `BUILD-20261112-fieldagent-470-heal` | 有界自愈（溢出只丢帧）+ 470 MHz 默认 |
| 1 | `158bf1db` / `f734934a948f` | 951,712 B | `1c1f8b411db5` | `BUILD-20261111-fieldagent-470` | LoRa 默认 470 MHz 的基线 |

中间构建（**未归档**，被后续版本取代，仅记录以保持谱系完整）：

| build_id（尾 12） | 说明 |
|---|---|
| `ff6eb429d255` | 回调超时静默门控首次构建，已被 v4 取代 |
| `e345154cff2c` | v4 的 BOM 清理重建（逻辑等同 v4，曾烧过五板） |
| `111f2d67…` | v4 + `mobility.c`（链接器丢弃），未烧板 |
| `a5f08dd0…` | 首次 4 MB 分区构建，被 v5 取代 |

> 注：前 8 与 尾 12 都只是人工比对用的片段；**唯一权威标识是完整 build_id**
> （`stats`/`info` 返回的 `build_id` 字段）。

## 当前板上状态（2026-11-13）

| 板 | 版本 | 模式 | LoRa |
|---|---|---|---|
| A | `2267bc60` | active | rx @ 470 MHz |
| B–E | `2267bc60` | active | tx @ 470 MHz |

分区已改为 4 MB，**回滚必须全量烧录**：
`0x0 bootloader.bin` + `0x8000 partition-table.bin` + `0x10000 mid_edge.bin`。

## 变更纪律

1. 每次构建归档 `images/`（app + bootloader + 分区表）、`sdkconfig`、`BUILD.md`、`SHA256SUMS.txt`。
2. `BUILD.md` 必须写：改了什么、**怎么验证的**、回滚到哪一版。
3. ELF/MAP 不入库（`.gitignore`），可由源码重新构建得到。
4. 未在实板验证的改动，在 `docs/IMPLEMENTATION_STATUS.md` 标【编】，不得写成【板】。
