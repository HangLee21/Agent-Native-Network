# 两个 group：本地 5 块 + 远程 15 块

## 一、要不要重新刷写？**不需要**

`group`（编组）和 `channel`（WiFi 信道）都是**运行时配置，存在节点 NVS 里**，
不是编译进固件的常量。

固件里对应的命令（`app_main.c:311-319`）：

```
{"cmd":"discover_config","group":N,"channel":C,"autostart":true}
```

写入 NVS 的 blob 是 `NDc1` + group(4 B) + channel(1 B) + autostart(1 B)，
重启后自动恢复。

**所以：现有五块板保持当前固件（`BUILD-20261120-lrn1-health`）不动，
只需要改它们的 group 值。**

---

## 二、group 到底隔离了什么

| 层面 | 是否受 group 影响 |
|---|---|
| **ESP-NOW 组网** | ✅ **完全隔离**——固件在收包时校验 `group`，不同组直接丢弃 |
| **路由** | ✅ 隔离（路由表按组建立，跨组不建路） |
| **LoRa 上行** | ❌ 不受影响——每个节点都直接发给网关，group 只作为标签出现在帧里 |
| **网关** | 一台网关可以同时收两个组（帧头带 `wifi_group`） |

**所以"两个 group"= 两张互不相通的网格，共用或各用一台网关都可以。**

---

## 三、强烈建议：两个组用不同 LoRa 信道

这是前面诊断出来的问题（5 块挤一个频点，相位锁死连续撞车）。

如果 20 块都在 470.5 MHz，碰撞会明显恶化。建议：

| 组 | group | LoRa 频率 | 网关信道 |
|---|---|---|---|
| 本地 5 块 | 1 | 470.5 MHz | ch1 |
| 远程 15 块 | 2 | 470.7 MHz | ch2 |

网关 8 个解调器本来就支持，改 `frequency_hz` 即可（也是运行时配置）。

> 注意：改 LoRa 频率用的是另一条命令（`lora_ref_config` + `frequency_hz`），
> 和 group 不是同一条；两者都要设。

---

## 四、怎么设 group

### 远程设置（推荐）——通过各自的 Pi

```powershell
# 本地五块 -> group 1，WiFi 信道 1
python tools\mid_baseline\fleet\fleet.py group --group 1 --channel 1 --only eora-air-01 eora-air-02 eora-air-03 eora-air-04 eora-air-05

# 远程十五块 -> group 2，WiFi 信道 6（与本地错开）
python tools\mid_baseline\fleet\fleet.py group --group 2 --channel 6 --only eora-air-06 ... eora-air-20
```

执行过程（对每台）：
```
停 node_reader（它独占串口）
  -> 推送 set_group.py
  -> 节点执行 stop / discover_config / info
  -> 读回实际值确认
  -> 重启 node_reader
```

返回示例：

```json
{"ok": true, "group_requested": 1, "channel_requested": 1,
 "group_reported": 1, "channel_reported": 1, "mode": "active"}
```

**`group_reported` 与 `group_requested` 不一致就是没生效**，不要只看 ok。

### 用组过滤来刷板

```
config/fleet.groups.json      ← 复制 config/fleet.groups.example.json 改
{
  "nodes": [
    {"name": "eora-air-01", "group": 1},
    {"name": "eora-air-06", "group": 2}
  ]
}
```

之后可以只对某一组操作：

```powershell
python tools\mid_baseline\fleet\fleet.py update BUILD-xxx\images\mid_edge.bin --group 1
python tools\mid_baseline\fleet\fleet.py run "df -h /" --group 2
```

---

## 五、两组的远程刷板前提（都不需要同局域网）

| 前提 | 说明 |
|---|---|
| **每块板所在的 Pi 在同一个 tailnet** | 卡片里带同一个运维 tailnet 的 auth key |
| **刷板机登录同一个 tailnet** | 只有这一台机器需要装 Tailscale |
| **网关不需要 Tailscale** | 只走以太网 UDP |

**关键**：`fleet.py` 找设备靠**名字**（`eora-air-*`），不靠 IP。
所以五块在实验室、十五块在外地，只要都在 tailnet 里，**刷板操作完全一样**：

```powershell
fleet.py status              # 一次列出 20 台
fleet.py update <img> --group 2   # 只刷远程那 15 块
```

---

## 六、验收（改完 group 之后）

| 检查 | 期望 |
|---|---|
| 每组内部互见 | 组 1 的节点邻居里只有组 1 的成员 |
| 跨组不可见 | 组 1 的邻居列表**不出现**组 2 的 MAC |
| LoRa 上行都在 | 两组都能被网关收到（帧头 `wifi_group` 区分） |
| 前端区分 | 按 `wifi_group` 分色/分组显示 |
| 刷板互不影响 | `update --group 1` 不动组 2 的设备 |

---

## 七、当前状态与待办

| 项 | 状态 |
|---|---|
| `fleet.py group` 子命令 | ✅ 已实现（含读回校验） |
| `--group` 过滤（update / run） | ✅ 已实现 |
| `config/fleet.groups.example.json` | ✅ 已提供 |
| 五块板是否要重刷 | ❌ **不需要**，只改 group/channel |
| 是否已实测改 group | ❌ **未做**：Tailscale 处于 NoState，设备不可达 |
