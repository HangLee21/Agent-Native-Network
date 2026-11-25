# 链路层可切换后端（link backend）设计

状态：设计稿。当前固件只实现 `espnow`；`lora24` 已可配置但标记 pending。

## 1. 目标

一块固件烧一次，之后用树莓派脚本决定每个节点用什么链路层、以及用什么射频参数，
不需要重新烧板。两种后端：

| 后端 | 射频 | 特点 |
|---|---|---|
| `espnow` | ESP32 Wi-Fi 2.4 GHz | 独立电台，与 470M 真并行，链路预算低（余量约 19 dB） |
| `lora24` | LR1121 2.4 GHz | 与 470M 共用一颗电台，需分时；链路预算高（实测余量约 58 dB） |

实测依据见 `BUILD-20261125-rx-rssi/` 与提交 `2ed62c7`。

## 2. 现有边界（改造点）

链路层与协议层目前是直接耦合的，只有三处发送和一处收包：

```
app_main.c
  route_pump()      esp_now_send(next.mac, bytes, len)     // 路由数据，单播
  telemetry_pump()  esp_now_send(broadcast, bytes, len)    // 遥测，广播
  pump()            esp_now_send(next.mac, bytes, len)     // 控制包，单播
  receive_cb()      → input{type=1, mac, rssi, data} → inputs 队列
  send_cb()         → input{type=2, ok}          → inputs 队列
```

`inputs` 队列是唯一的收包入口，`input.type==1/2` 被统一处理。
因此后端抽象只需要覆盖 **发送** 与 **上报 type=1/2**，上层（邻居、路由、遥测、显示）不动。

LR1121 侧由 `lora_ref` 的 worker 任务独占 SPI，通过两个队列交互：

```
frames 队列：上层 → worker   (要发的帧)
events 队列：worker → 上层   (收帧、TX 完成、故障)
```

`lora24` 后端必须走这两个队列，**不能在 app_main 里直接操作 SPI**。

## 3. 接口

```c
typedef struct {
  int  (*start)(void);                      /* 初始化射频，失败返回非 0 */
  void (*stop)(void);
  int  (*send)(const uint8_t mac[6], const uint8_t*data, unsigned len);
  const char *name;                         /* "espnow" / "lora24" */
} link_backend;

extern const link_backend *link;            /* 启动时按 link_mode 选定 */
```

三处发送改为 `link->send(...)`；接收回调统一构造 `input{type=1,...}` 后投递，
回调来源是 ESP-NOW 的 `receive_cb` 或 lora24 的收帧事件。

`link_mode` 已在 NVS（命名空间 `link`，键 `mode`），由
`tools/mid_baseline/fleet/node_config.py link --mode ...` 写入。

## 4. lora24 的收发与分时

### 4.1 帧长

- `mid` / `sr` 包最大 250 B；`lref_port_tx` 目前上限 208 B。
- v1 策略：>208 B 的包**不发送**，计入 `link_tx_oversize`，并在状态里可见。
  不静默截断（截断会产生非法帧）。
- 后续可评估把邻居表等结构瘦身到 208 B 以内。

### 4.2 分时

470M 上行必须保住：

```
每 10 s： 470M 发 LRN1（328 ms @ SF7/BW125）
          → 切到 2.4G（1.1 ms 实测）
          → 2.4G 驻留（链路收发）
          → 上行到期前切回 470M（20 ms 实测，含 image 校准）
```

盲区 = 328 + 1 + 20 ≈ **350 ms / 10 s = 3.5%**。
调度原则：**上行优先**；切换只在 TX_DONE 之后发生，避免打断接收中的帧。

### 4.3 双向

链路层需要 hello/ACK 双向。v1 只在 2.4G 收，收到后走既有的三态邻居逻辑；
ACK 由协议层生成，仍经 `link->send`。

## 5. 失败策略

| 情况 | 行为 |
|---|---|
| `lora24` 启动失败 | 不自动改 NVS；`link_mode_active` 报 `espnow`，`link_fault` 记录原因 |
| 切换失败 | 立即回退到整机 apply（已在 `runtime.c` 实现） |
| 连续收不到任何帧 | 保持当前后端，`link_rx_starved` 计数递增，由脚本/人决定是否切回 |

**不做自动漂移**：链路层选择是可预期的运维动作，自动切换会掩盖故障。

## 6. 可观测性

`info` / `stats` 计划新增：

```
link_mode            已存配置
link_mode_active     实际生效
link_mode_pending    两者不一致时为 true
link_tx_frames       link->send 成功次数
link_tx_oversize     >208 B 被拒的包数
link_rx_frames       经 link 收到的 type=1 次数
link_rx_rssi/snr     最近一帧质量
link_switch_count    频段切换次数
link_switch_us_max   最慢一次切换耗时
```

前端与现场脚本都读这份状态，因此这些字段是"后端是否健康"的唯一判据。

## 7. 分阶段实施

| 阶段 | 内容 | 验证 |
|---|---|---|
| 2a | 加 `link_backend` 抽象，只实现 `espnow`；三处发送与两处回调改为走接口 | 5 台行为与现在完全一致（对照 build 与 RSSI） |
| 2b | `lora24` 只承载 hello/ACK，不接路由数据 | 两台节点在 2.4G 上互相进入邻居表 |
| 2c | 接路由/遥测 + 470M 分时 | 端到端：2.4G 邻居 + 470M 上行同时正常 |

每阶段可单独烧、单独回滚（回滚镜像见各 `BUILD-*/` 目录）。

## 8. 风险

1. **板内共存**：ESP-NOW 与 2.4G LoRa 同板 2 cm、相距 58 MHz，实测丢包中 2 帧为 CRC 错，
   指向干扰。形态 B（lora24 模式关闭 Wi-Fi）可规避；形态 C 需额外验证。
2. **单电台分时的抖动**：Wi-Fi 抢占会让切换变慢（实测偶发 261 ms）。需要上限保护。
3. **帧长限制**：208 B 上限可能挡掉部分路由包，必须先量化实际包长分布。
4. **法规**：470M 功率已限制在 +14 dBm；2.4G 在 +13 dBm 以内。
