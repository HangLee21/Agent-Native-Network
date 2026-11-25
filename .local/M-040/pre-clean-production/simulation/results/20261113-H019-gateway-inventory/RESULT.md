# RHF2S008 网关参数盘点（2026-11-13）

只读登录采集，未修改网关任何配置。逐文件路径与 sha256 见 `SOURCE.json`。

## 设备

| 项 | 值 |
|---|---|
| 型号 | RisingHF **RHF2S008**（hostname `rhf2s008`） |
| 硬件 | Raspberry Pi Compute Module 3 Rev 1.0，载板 HW 3.0 |
| 固件 | RHF 0.1.3 (CM3)，2018-07-04 |
| 系统 | Raspbian 8 (jessie)，`4.4.50-v7+`，armv7l |
| MAC / IPv4 / IPv6 LL | `b8:27:eb:32:e2:c1` / `192.168.137.200` / `fe80::ba27:ebff:fe32:e2c1` |
| 开放端口 | 仅 22/tcp（1–10000 全扫） |

## 采集到的文件

| 文件 | 来源 | 内容 |
|---|---|---|
| `global_conf_cn470_ch00_07.json` | `/opt/risinghf/pktfwd/global_conf.json`（软链目标） | SX1301 配置：radio 频率、8 个 multiSF 信道、TX LUT |
| `local_conf_localhost_1680.json` | 同目录 `local_conf.json` 软链目标 | `gateway_ID=b827ebFFFE32e2c1`、`localhost:1680` |
| `pktfwd.service` | `/opt/risinghf/pktfwd/pktfwd.service` | `pktfwd.sh` → `pktfwdbin`，`Restart=always` |
| `lora_receiver.py` | `/home/rxhf/lora_receiver.py` | Semtech UDP 接收器（打印 freq/RSSI/SNR/payload hex） |

## 关键结论

1. **8 信道成立**：SX1301 + 2× SX1255，8 个 multiSF 信道同时解调，BW125。
2. **当前信道为 CN470 第 0–7 组**：470.3 / 470.5 / 470.7 / 470.9 / 471.1 / 471.3 / 471.5 / 471.7 MHz。
3. **与节点三处不匹配**（详见 `docs/LORA_GATEWAY_PARAMETERS.md` §4）：
   频率差 300 kHz、`lorawan_public: true` 的公有同步字、只转 CRC 有效帧。
4. **转发链路已就绪**：包转发器已把帧送到 `localhost:1680` 的 UDP JSON，
   机上通用接收器可直接打印。
5. `/home/rxhf/lora_test.csv` 只有表头 → 历史上的 100 包测试**从未收到有效帧**。

## 未做

- 未修改网关任何配置、未重启服务、未安装软件。
- 未做任何登录取参以外的操作。
