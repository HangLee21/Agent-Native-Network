# 把 LoRa 上报从“临时拿一块板当网关”换到正式网关

状态：迁移说明。本次改动已让 `receive.py` 不再写死 A 的 MAC，但**没有**任何实板证据证明
换网关流程已经跑通。

## 为什么“网关”需要被指定

LRN1 帧**没有目的地址字段**（44 B 头只有 observer MAC / boot / report_seq / snapshot /
Wi-Fi group / 行数 / period / tx_delay）。空口上唯一起“寻址”作用的是这六项 PHY 参数：

```
frequency_hz + sf + bandwidth_hz + coding_rate + sync_word + preamble_symbols
```

六项一致就是同一个 LoRa 信道。**谁配成 `role=rx`，谁就是网关**，没有发现、没有关联、
没有握手、没有 ACK。串口事件里的 `gateway_id` 是接收板在封套里**填自己的 MAC**，不是帧里带过来的。

由此得到两个直接结论：

- 换网关 = **换哪块板处于 `role=rx` 且 PHY 相同**，不需要改帧、不需要重新烧写；
- 只要还有一块板在 `role=rx` 且 PHY 相同，它就**照样会收**——旧网关不会自动停止。

## 三种“新网关”要分开处理

| 新网关是什么 | 要做的事 | 是否需要重新编译 |
|---|---|---|
| **同类板（EoRa-HUB + 本固件）** | 按下面第 1 节切角色即可 | 不需要 |
| **第三方点对点 LoRa 模块/网关** | 必须让它讲 LRN1（同 PHY、同 44+20n+CRC 格式），否则收不到 | 不需要改本仓库固件，但需要网关侧实现 LRN1 |
| **商业 LoRaWAN 网关** | **不能直接用**。LRN1 是裸 LoRa 点对点帧，没有 LoRaWAN MAC 层（没有 join、没有 DevAddr、没有上行帧头），LoRaWAN 网关不会转发它 | 需要另做 LoRaWAN 栈，属于新固件而不是配置 |

## 1 同类板：切角色的最小步骤

`lora_ref_config` 支持部分更新（只带要改的字段），每次成功都会写 NVS 并立即生效，**不用重启**。

前提：新旧网关的 PHY 六项必须完全一致，发送板不需要任何改动。

```json
// (1) 新网关板：接上同一根 Sub-GHz 天线（② 号 IPEX-1 口），切接收
{"cmd":"lora_ref_config","nonce":"switch-rx","role":"rx","start_on_boot":true}

// (2) 旧网关板（现在的 A）：停掉接收，避免两块板同时抢当网关
{"cmd":"lora_ref_config","nonce":"switch-off","role":"off","start_on_boot":false}
```

判据（依次收紧，缺一不可）：

1. 新板 `lora_ref_status`：`requested_generation == applied_generation`、
   `lora_ref_worker_state == 1`、`lora_chip_type` 为 LR1121、`start_on_boot: true`、
   `boot_role_suppressed: false`、`frequency_hz`/`sf`/`bandwidth_hz` 与发送板完全一致。
2. 旧板：`lora_ref_worker_state == 0` 且 `requested_role == "off"`。
3. **真正的证据只在新板**：`lora_ref_rx_frames` 增长、`lora_ref_last_rx_ms` 变化、
   `rx_bad` 不增长。这三个字段是本次新加的，就是为了回答“换了网关到底有没有收到”。
4. 主机侧采集必须显式指定新网关：

```powershell
python -X utf8 -m tools.mid_hardware.lora_ref.receive ^
  --port COM<n> --duration 35 --task-id H-020 ^
  --gateway-mac <新网关 MAC> ^
  --output simulation/outputs/H-020/<新的目录>
```

迁移过程中还没确认新网关能收时，可以先这样“先收后认”：

```powershell
python -X utf8 -m tools.mid_hardware.lora_ref.receive --port COM<n> --duration 35 ^
  --any-gateway --task-id H-020 --output simulation/outputs/H-020/<新的目录>
```

`--any-gateway` 不校验身份，只在 `RESULT.json` 里记录 `gateway_ids` 实际出现过哪些板，
用于判断“是不是接错了口/还有旧网关在抢”。**确认之后必须回到 `--gateway-mac` 的严格模式**，
否则不同网关的帧会被当成同一路数据混在一起。

## 2 两块网关同时在线的后果

因为帧里没有目的地，**两块 `role=rx` 的板会同时收到同一批帧**，各自产生一条
`lora_ref_rx`，`gateway_id` 不同而 `frame_hex` 相同。这在空口上是合法的（广播监听），
但会导致：

- 主机如果同时读两个串口，会得到**重复**的报告（同一 observer/boot/report_seq 两份）；
- 按“收到份数”算的任何比率都会翻倍。

所以契约只写了单网关。迁移期间请按顺序切：**先开新网关确认在收，再关旧网关**，
不要长期双开；双开时必须在主机侧按 `gateway_id` 分组，不能合并统计。

## 3 天线与物理口

手册里 ① 是 LoRa 2.4 GHz、② 是 LoRa Sub-GHz（IPEX-1）。**只有 ② 能收 433/470 的 LRN1 帧。**
新网关如果插在 ① 上，`lora_ref_rx_frames` 会一直是 0，且没有任何错误提示——
这是最容易误判成“固件坏了”的情况。

## 4 不值得做的两件事

- **不要把网关 MAC 写进帧**。LRN1 的 44 B 头与 48+20n+CRC32 布局是 E1-029 的冻结合同，
  `decoder.py` 与合成样本都按它校验；加字段等于换 LRN2，需要整套重做与重新验收，
  而对“换网关”没有收益——接收方本来就知道自己是谁。
- **不要用 `role:tx` 的板当网关**。`role=tx` 的 worker 只发不收（`lref_port_apply` 里
  `role==1` 才会 `set_rx_with_timeout`），配错了不会报错，只会一条都收不到。
