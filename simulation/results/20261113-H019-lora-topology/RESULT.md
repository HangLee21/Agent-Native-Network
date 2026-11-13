# H-019 LoRa 拓扑与五板稳定性（2026-11-13）

本目录是 `simulation/outputs/H-019/` 中两份现场证据的**采纳副本**。
原始字节仍留在 `simulation/outputs/`（该目录按仓库约定不入库），逐文件路径与 sha256 记在 `SOURCE.json`。

| 文件 | 内容 |
|---|---|
| `TOPOLOGY.md` | 5 节点 LoRa 拓扑实测：全网格、D 孤立消除、85% 交付率与根因 |
| `RECEIVE_RESULT.json` | 解码器输出：17 帧、0 重复、1 个网关、端口全部关闭 |
| `SOAK.json` | 五板 3 分钟压力测试：overflow/heal/locked 均为 0，A 收 LoRa 119 帧 |
| `SOURCE.json` | 原始文件路径、字节数、sha256、build_id |

## 结论

- 构建：`mid-lora-ref-v1-e345154c…`，五板一致。
- 网关：A（`90:da:72:48:a4:f8`）`role=rx`、470 MHz、`start_on_boot=true`，掉电重插后零命令自动恢复。
- 拓扑：B/C/D/E 四观察者全部 4 邻居 `bidirectional`，**5 节点全网格，无孤岛**。
- 交付率：50 s 内 20 帧预期、解码 17 帧（**约 85%**）。四板同频 470 MHz 随机接入，占空约 13%，
  与 ALOHA 模型预期的约 23% 冲突损失吻合——属单信道固有限制，非缺陷。
- 稳定性：3 分钟压力运行 `input_overflow_total=0`、`radio_heal_attempts=0`、`locked=false`，
  heap 稳定在 90.5 KB。

## 已修复的缺陷（本构建）

1. **D 板孤立**：输入队列溢出 → 发送回调被丢 → 1 s 超时被误判为射频故障 → `stop_all()` 自愈 3 次用尽 → 永久锁死。
   修复为「回调超时只记本地发送失败，仅当整板 1 秒无收帧才判射频故障」，新增 `send_callback_timeouts` 区分两类事件。
2. **网关身份硬编码**：`lora_reader.py` 曾写死 A 的 USB 位置 `1-1.3`（实际 `1-1`），导致端口匹配失败、串口从未打开。
   改为从 `bindings.local.json` 按 MAC 解析，并支持自动发现与持久化（`.local/mid/H-020/gateway.json`）。

## 限制

- A 板作为网关会出现物理掉电（esptool 也无法连接，非固件崩溃）。作为唯一接收方，掉电即拓扑中断，需可靠供电。
- 85% 交付率是实测值；调度化上行（仿真 95%）尚未上板。
