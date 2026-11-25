# LoRa 拓扑实测（2026-11-13 修复后）

## 构建

`mid-lora-ref-v1-e5a7d870f541fcc7105b0fda3f4ccb8118473b79a843bc8a09ceff6eb429d255`
五板一致。本版修掉了"发送回调丢失被误判为射频故障"导致的永久锁死。

## 网关

A（`90:da:72:48:a4:f8`）`role=rx`、470 MHz、`start_on_boot=true`，**掉电重插后零命令自动恢复**。

## 抓取

`tools.mid_hardware.lora_ref.receive --port COM8 --duration 50`
输出：`reports.jsonl`、`RESULT.json`（本目录）。
解码 17 帧、0 重复、1 个网关 ID、未发生网关互换、端口全部关闭。

## 拓扑（4 个观察者的最新一帧）

| 观察者 | 上报数 | 帧 RSSI | SNR | 看到的邻居 |
|---|---:|---:|---:|---|
| C | 5 | −43 dBm | 15 | A✅ B✅ D✅ E✅ |
| D | 5 | −69 dBm | 14 | A✅ B✅ C✅ E✅ |
| E | 4 | −56 dBm | 2 | A✅ B✅ C✅ D✅ |
| B | 3 | −59 dBm | 16 | A✅ C✅ D✅ E✅ |

**5 节点全网格，所有边都是 `bidirectional`。D 的孤立状态已消除。**

## 交付率

50 s 内 4 个发送端 × 10 s 周期 = 20 帧预期，解码 17 帧 → **约 85%**。

原因是四块板**都在同一频点 470 MHz 单信道随机接入**：占空 4×0.328/10 ≈ 13%，
按 ALOHA 模型预期冲突损失约 23%，与实测 15% 损失吻合。
这与仿真给出的单信道量级一致，属于已知短板（8 信道或调度化上行可解）。

## 关于 D 的根因（本版修复项）

```
输入队列溢出 → 发送回调被丢 → 1 s 超时被当成射频故障
  → locked=1 + stop_all() → 自愈 3 次用尽 → 永久锁死 → 拓扑上成为孤岛
```

修复：发送回调超时只记为本地发送失败（交路由层重试），
**仅当整板 1 秒内没有收到任何帧**时才判定射频故障并自愈。
新增 `stats.send_callback_timeouts` 与 `stats.input_overflow_total` 区分这两类事件。

## 关于 A 的掉电

A 在烧录后约 1 分钟完全静默，esptool 也无法连接（`No serial data received`），
说明芯片本体未运行——是供电/EN 问题，不是固件崩溃（崩溃仍可进 ROM）。
重新插紧后立即恢复，boot 更新，LoRa 角色与频率自动还原。
**建议：A 作为网关应使用可靠供电（直连机箱口或有源 HUB）。**

## 复现命令

```powershell
python -X utf8 -m tools.mid_hardware.lora_ref.receive --port COM8 --duration 50 `
  --output simulation/outputs/H-019/<新目录> --gateway-mac 90:da:72:48:a4:f8 --task-id H-019
```
