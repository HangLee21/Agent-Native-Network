# RHF2S008 网关接收 EoRa 节点 LRN1（2026-11-13 打通）

## 结论

**端到端打通**：4 块 EoRa tx 板（B/C/D/E）的 LRN1 拓扑帧，被 RisingHF RHF2S008 八通道
网关收到、校验通过、按信道标号、经 Semtech UDP 转发到 PC，并由 Studio 前端显示。

## 实际生效的配置改动

**网关侧只改了 `local_conf.json`**（`gateway_conf` 覆盖 `global_conf.json`），
未动 `global_conf.json`、未改频率计划、未重启整机：

```json
{
  "gateway_conf": {
    "gateway_ID": "b827ebFFFE32e2c1",
    "server_address": "192.168.137.10",
    "serv_port_up": 1680,
    "serv_port_down": 1680,
    "forward_crc_valid": true,
    "forward_crc_error": true,
    "forward_crc_disabled": true
  }
}
```

原文件备份在同目录 `local_conf_localhost_1680.json.orig`（174 B）。
回滚：`sudo cp ...json.orig ...json && sudo systemctl restart pktfwd`。

**节点侧**：5 块板 `frequency_hz` 470,000,000 → **470,500,000**、`sync_word` 18 → **52 (0x34)**，
以匹配网关既有信道 ch5 与 `lorawan_public: true`。（改回：`sync_word=18`、`frequency_hz=470000000`。）

## 实测数据

| 项 | 值 |
|---|---|
| 接收信道 | **ch5 = 470.500 MHz**（`datr=SF7BW125`、`codr=4/5`、`stat=1`） |
| 网关侧 RSSI / SNR | −43 … −57 dBm / 8.8 … 11.0 dB |
| 帧长 | 128 B（`n=4` 邻居行） |
| 结构校验 | **29/29 帧 CRC32 正确**，`LRN1` 魔数、`hdr=44`、`row=20` 全部匹配 |
| 上报节点 | B/C/D/E 各 7–8 帧；每帧 4 个邻居，`state=2`（双向） |
| 同信道干扰 | 另有 22 帧 `HELLO_0xx`（9 B ASCII），非我们设备，已在前端过滤 |

样本：`lrn1_samples.jsonl`（5 帧原始十六进制）；生效配置：`local_conf_active.json`。

## 一并解决的疑问

- 「SX1301 能否收非 LoRaWAN 帧」：**能**。128 B 二进制 LRN1 + 显式头 + CRC 开，
  被正确解析且 `stat=1`，CRC32 由我们自己在主机侧二次校验通过。
- 之前 0 帧的原因是**转发器实例状态问题**：重启 `pktfwd`（加载了放宽 CRC 的
  `local_conf`）后立即开始收到。节点侧参数在同一时间已正确，A 板自收自验 25 s 收到 10 帧。

## 前端

`tools/mobile_gateway/studio.py` 的 `/api/v1/lora/topology` 改为
**网关源优先、串口 A 兜底**；网关数据由
`tools/mid_baseline/gateway_probe/topology_server.py` 提供（UDP 1680 → 解码 LRN1 →
`lora.topology.v1`）。

验证：`http://127.0.0.1:8794/api/v1/lora/topology` 返回
`source=gateway_udp_lrn1`、`reports=4`、`gw=b827ebfffe32e2c1`、`labels` 含 `RHF2S008`。

## 未做 / 未验证

- 未验证 8 信道**并行**收（本次只用了 ch5 一个频点，因为 4 块板同频）。
- 未做下行（LRC1）；网关 `radio_0/1` 的 `tx_enable` 仍为原值，未使用。
- 未做多信道分配实验（把 4 块板分散到 470.3/470.5/470.7/470.9）。
