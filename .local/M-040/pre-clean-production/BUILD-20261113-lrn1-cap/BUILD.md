# BUILD 2026-11-13：LRN1 组帧容量修复与行选择优化

## 关键标识

| 项 | 值 |
|---|---|
| build_id | `mid-lora-ref-v1-cd389e57767d43250a149a23b069ada250a2dd192f5b634471f52839f5b34783` |
| app 镜像 | 953,520 B，sha256 `493eabfa083883237f04847d0fce26eb262957a394195f84406e4a01a7c26286` |
| 编译 | 0 warning / 0 error（全新构建目录） |
| 烧录方式 | app-only（`0x10000`），分区表未变 |

## 修的是什么

原 `lora_ref/runtime.c` 的组帧函数遍历全部 `ND_PEERS`，**没有行数上限**：

```c
for (unsigned i = 0; i < ND_PEERS; i++) {
    uint8_t *r = data + 44 + 20 * count++;   // count 可以超过 8
```

缓冲区是 `frame_job.bytes[208]`（每行 20 B，头 44 B，CRC 4 B → 最多 8 行）。越界后果：

| 邻居数 | 末行写入偏移 | 后果 |
|---:|---:|---|
| 8 | 204 | 安全 |
| 9 | 224 | 越过 208，覆写 `len/seq/generation/sampled` |
| 14（30 节点平均度） | 324 | 越界 116 B，破坏栈/队列结构 |

5 块板平均度 4，所以此前未暴露；**上到 10 节点即会触发**。

## 改法

新增可移植模块 `lrn1_frame.{c,h}`（不依赖 ESP-IDF，可主机测试）：

1. **按缓冲区算容量**：`rows ≤ (cap − 44 − 4) / 20`，超限直接拒绝。
2. **行选择按信息价值**：
   - 第一优先：所有**非双向**（`nd_state != 2`）的邻居——它们代表拓扑变化；
   - 其余按**轮转游标**填充，保证邻居数 > 容量时，每个邻居在 `ceil(N/rows)` 帧内必出现一次。
3. `visible_rows`（偏移 34）记录**截断前**的合格邻居数，网关据此知道丢了行。
4. `lrn1_set_delay()` 负责发送前写入真实时延并重算 CRC（保持原行为）。

`runtime.c` 的 `capture()` 改为薄封装，删除两个不再使用的静态函数。

## 验证

主机测试 `firmware/mid_baseline/field_agent/test_lrn1.c`，**17 项全部通过**：

- 8 邻居 → 208 B 帧、8 行、CRC 有效
- **12 邻居 → 仍为 208 B、8 行、`visible_rows=12`、容量外金丝雀字节未被写**
- 非双向邻居必定入选
- 轮转：6 帧内 12 个邻居全部出现过
- 容量不足（40 B）时返回 0 而非越界
- 时延戳记后 CRC 仍有效、`period` 正确携带

固件编译 0 警告。

## 未完成

**未烧录**：执行时 5 块板全部从 USB 消失（`Get-PnpDevice -PresentOnly` 中无任何
`VID_1A86` 设备，仅剩蓝牙串口 COM3–6）。需恢复供电/重新插拔后再烧。

## 回滚

上一版 `BUILD-20261113-4MB-notxblock/images/mid_edge.bin`（`2267bc60`），app-only 烧回即可。
