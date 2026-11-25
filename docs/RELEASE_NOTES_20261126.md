# 本次更新说明（2026-11-26）

本次是链路层方向的一次大幅更新：在**不破坏原有 ESP-NOW 与 470 MHz 上行**的前提下，
把 2.4 GHz LoRa 作为可选的链路层接进来，并补齐状态回显、参数脚本化、前端显示与发布同步。

---

## 一、一句话总览

节点现在支持两种链路层，可由一条命令切换：

| 模式 | 链路层 | 上行 | 适用 |
|---|---|---|---|
| `espnow`（默认） | 2.4 GHz ESP-NOW | 470.5 MHz LoRa | 常规，兼容全部旧节点 |
| `lora24` | **2.4 GHz LoRa（LR1121）** | 470.5 MHz LoRa（时分切换） | 距离更远、抗干扰更强 |

关键点：`lora24` 模式下**不是一直占用 2.4 GHz**。每 10 秒把射频切回 470 MHz 发一次上行，
发完立刻切回 2.4 GHz（实测：切到 2.4G 1.1 ms，切回 470M 16~21 ms）。

---

## 二、固件更新

### 2.1 新增链路抽象（`app_main.c`）

```c
typedef struct { const char* name; int (*send)(const uint8_t mac[6], const uint8_t* data, unsigned len); } link_backend;
static const link_backend LINK_ESPNOW = {"espnow", espnow_link_send};
static const link_backend LINK_LORA24 = {"lora24", lora24_link_send};
```

- 所有发送点统一走 `link->send(...)`，不再直接调用 ESP-NOW。
- 超过 208 字节的帧不再发送，计入 `link_send_oversize`（与 `lora_ref` 的缓冲一致）。
- 新增 `link_mode`（NVS 命名空间 `link`，键 `mode`），默认 `espnow`。
- `radio_start()` 在 `lora24` 下**不启动 Wi-Fi/ESP-NOW**（避免两个 2.4G 电台互相干扰）。
- `info` 新增字段：`link_mode`、`link_mode_active`、`link_mode_pending`、`link_backend`、
  `link_send_ok`、`link_send_fail`、`link_send_oversize`。

### 2.2 链路态与收发（`lora_ref/runtime.c`）

- `role=3`（`link`）：常驻 2.4 GHz 接收，收到的帧进入 8 槽环形缓冲。
- `lora_ref_link_pop()`：主任务取帧。
- `lora_ref_link_send()`：主任务投递链路帧，SPI 仍由 worker 独占。
- `role==3` 下同时服务 `frames` 队列（发送 + 等待 TX_DONE + 回到监听）。
- **时分调度**：发送上行前 `lref_port_switch(470.5MHz/SF7/BW125)`，发完切回链路频段。
- `lora_ref_status` 新增 `link_rx_frames`、`link_rx_dropped`。

### 2.3 射频表与快速切换（`lora_ref/port.c`）

- 生成式 LF/HF 功率表：470M `-17..+22 dBm`，2.4G `-18..+13 dBm`（硬件上限）。
- 带宽映射支持 203/406/812 kHz（仅 2.4G）与 125/250/500 kHz（Sub-GHz）。
- 2.4G 跳过镜像校准，切换耗时从 385 ms 降到约 286 ms 全流程。

### 2.4 启动修复

- `app_main()` 入口调用 `link_mode_load()`，保证 `radio_start()` 选择电台前已知模式。
- `link_mode_active()` 返回真实后端（原先硬编码 `"espnow"`，会误导状态判断）。

---

## 三、脚本更新

### 3.1 `tools/mid_baseline/fleet/node_config.py`（新）

读改节点参数，全部经串口下发并回读校验：

```powershell
python tools\mid_baseline\fleet\node_config.py read
python tools\mid_baseline\fleet\node_config.py lora --sf 8 --power 15
python tools\mid_baseline\fleet\node_config.py link --mode lora24
```

### 3.2 `tools/mid_baseline/fleet/set_link_mode.py`（新）

只改链路模式，可选重启。

### 3.3 `tools/mid_baseline/fleet/switch_link.py` + `SWITCH_LINK.cmd`（新）

一条命令完成「射频参数 + link_mode + 重启 + 读回校验」，避免两者不同步：

```powershell
SWITCH_LINK.cmd lora24                 # 全部在线节点
SWITCH_LINK.cmd espnow
SWITCH_LINK.cmd status                 # 只读
SWITCH_LINK.cmd lora24 eora-air-01     # 指定设备
```

**自动跳过离线节点**，不会因为某台没电而卡住。

### 3.4 `tools/release/check_decoder_parity.py`（新）

校验前端 `compat_decoder.py` 与主机解码器解码结果一致，当前 **7/7 通过**。

---

## 四、前端更新

| 改动 | 说明 |
|---|---|
| 网关节点渲染 | `NetworkTopology.vue` 不再把 `role=gateway` 从 Wi-Fi 视图里过滤掉 |
| 上行连线默认可见 | `NetworkView.vue` 的 `linkFilter` 默认由 `wifi` 改为 `all` |
| 上行连线样式 | 改为虚线 + 浅色（`#8fd6d1`，`stroke-dasharray: 5 7`，`opacity: .55`） |
| 启动即连本地网关 | `network-config.json` 改为 `enabled: true`、`mode: gateway` |

### 两个工作区（重要）

| 入口 | 端口 | 用途 |
|---|---|---|
| `START_STUDIO.cmd` | 10518 | **真实工作区** `studio.html`，需要网关数据 |
| `START_STUDIO_MOCK.cmd` | 5188 | **隔离 Mock** `mock-studio.html`，合成数据，可录制回放 |

Mock 由 `scripts/network-studio/dev.mjs`（**不带 `--real`**）提供：
合成 API 在 18081，页面在 5188。录制/回放只在 Mock 工作区启用，
真实工作区不会回退到合成数据。

---

## 五、实测数据（真机）

### 5.1 链路层

| 项 | 结果 |
|---|---|
| 2.4G 双向邻居 | 节点 1 ↔ 3、5 均为 `bidirectional`，age 1~2 s |
| 时序切换 | 链路态下网关仍收到上行（−50 / −55 dBm，age 4~7 s） |
| 切换耗时 | 2.4G 方向 1.1 ms；470 方向 16~21 ms |
| 盲区占比 | 328 ms(发) + 21 ms(切) ≈ 350 ms / 10 s ≈ **3.5 %** |

### 5.2 功率与距离

| 配置 | 470M RSSI | 说明 |
|---|---|---|
| 0 dBm | 约 −106 dBm（推算） | 余量仅 30 dB |
| **+14 dBm** | −84 dBm（2 号） | 合规配置 |
| **+15 dBm** | −83 ~ −99 dBm | 当前现场值 |
| +22 dBm | −77 dBm（2 号） | 比 +14 提升 7 dB，但**超出微功率 EIRP 限值** |

### 5.3 天线问题的判断依据（可复用）

- 现象：**节点搬到网关旁边 RSSI 仍为 −99 dBm**
- 结论：天线未接通（信号只经接头泄漏）
- 处置：重新插拔天线后 **−99 → −54 dBm（+45 dB）**
- 另一佐证：+22 dBm 只带来 1.5 dB 提升（功率加在开路端）

---

## 六、已知限制

1. **2.4G 发射上限 +13 dBm**，是 LR1121 硬件限制，配置无法突破
2. **`link_mode` 需要重启生效**（`radio_start()` 在启动时决定）
3. **只设 `link_mode` 不设 `role=link` 会导致失联**（无 Wi-Fi 也无 2.4G 链路）
4. `uplink_from()` **沿用链路配置的功率**（13 dBm）。**这是保留的设计选择，不是缺陷**：470M 上行实测稳定（链路态下 age 仍为 4~7 s），无需调回 15 dBm；若将来需要，改 `uplink_from()` 一行即可
5. 上行频段在固件里以常量 `LREF_UPLINK_HZ` 固定为 470.5 MHz，尚未做成配置项
6. ESP-NOW 与 2.4G LoRa 共存会互相干扰（实测丢包），切换是操作动作，不会自动回退

---

## 七、回滚

| 目标 | 操作 |
|---|---|
| 回 ESP-NOW | `SWITCH_LINK.cmd espnow` |
| 回旧固件 | 刷 `BUILD-20261120-lrn1-health/images/mid_edge.bin`（sha256 `2AA298FC…`） |
| 回滚 deploy | `git revert f24d6d5` 或回到 `0307c65` |

---

## 八、发布校验

```
verify_release.py            PASS（36 个文件哈希一致）
check_decoder_parity.py      7/7 一致
compileall app/ tools/       通过
```

节点镜像：`firmware/mid_edge.bin`
sha256 `67636CC875B09873CCBD4291DB807874C0DE97C2D04053C75F7E5FBE310FEF36`
