# LoRa 网关：实测参数与配置清单

- 生成日期：2026-11-13
- 设备：RisingHF **RHF2S008**（**已登录实测**，非推测、非规格书）
- 配套工具：`tools/mid_baseline/gateway_probe/`（`probe.py` 网络探测、`pi_dump.sh` 只读盘点）

## 1 设备与访问（实测）

| 项 | 值 |
|---|---|
| 型号 | **RisingHF RHF2S008**（hostname `rhf2s008`） |
| 硬件 | Raspberry Pi **Compute Module 3 Rev 1.0**，载板 HW 3.0 |
| 固件 | RHF **0.1.3 (CM3)**，2018-07-04 |
| 系统 | Raspbian GNU/Linux 8 (jessie)，内核 `4.4.50-v7+`，armv7l |
| MAC | `b8:27:eb:32:e2:c1` |
| IPv4 | **192.168.137.200/24**，网关 `192.168.137.1` |
| IPv6 LL | `fe80::ba27:ebff:fe32:e2c1`（EUI-64，由 MAC 推出） |
| 登录 | SSH `rxhf@<ip>`；用户属 `adm/dialout/sudo/spi/gpio/i2c` |
| 开放端口 | **仅 22/tcp**（1–10000 全扫，IPv4/IPv6 皆同） |
| 管理方式 | **SSH + 本地脚本，无 Web 界面** |

> 排查教训：上一轮只用 IPv4 工具（ARP/DHCP/SSDP/mDNS）全部落空。正确顺序是
> **先查 IPv6 邻居表 → `ping6 fe80::` → 端口扫描 → 再谈 IPv4**。

## 2 集中器与射频参数

活动配置是**软链**：`/opt/risinghf/pktfwd/global_conf.json -> global_conf_cn470_ch00_07.json`
（同目录另有 as920/us915/eu868/cn470 全信道组等约 40 个备选）。

| 参数 | 值 |
|---|---|
| 集中器 | **RHF0M301-470**（SX1301 + 2× SX1255），SPI `/dev/spidev0.0` |
| `lorawan_public` | **true** → 监听**公有 sync 0x34** |
| `clksrc` | 1 |
| `antenna_gain` | 0 |
| `radio_0` | **470,600,000 Hz**，`tx_enable: true`，TX 范围 470–510 MHz |
| `radio_1` | **471,400,000 Hz**，`tx_enable: false` |
| `chan_Lora_std` | **disabled** |
| `chan_FSK` | **disabled** |

### 2.1 八个并行信道（radio 频率 + IF 偏移算出）

| 信道 | 配置项 | IF | 实际频率 |
|---:|---|---:|---:|
| 0 | `chan_multiSF_0` (radio_1) | −300 kHz | 471.100 MHz |
| 1 | `chan_multiSF_1` (radio_1) | −100 kHz | 471.300 MHz |
| 2 | `chan_multiSF_2` (radio_1) | +100 kHz | 471.500 MHz |
| 3 | `chan_multiSF_3` (radio_1) | +300 kHz | 471.700 MHz |
| 4 | `chan_multiSF_4` (radio_0) | −300 kHz | **470.300 MHz** |
| 5 | `chan_multiSF_5` (radio_0) | −100 kHz | 470.500 MHz |
| 6 | `chan_multiSF_6` (radio_0) | +100 kHz | 470.700 MHz |
| 7 | `chan_multiSF_7` (radio_0) | +300 kHz | 470.900 MHz |

全部 **BW125**，多 SF 并行（SF7–SF12）。

## 3 转发与配置参数

`gateway_conf`（全局）+ `local_conf.json`（覆盖，生效）：

| 参数 | 全局值 | 本地覆盖（当前生效） |
|---|---|---|
| `gateway_ID` | `AA555A0000000000`（占位） | **`b827ebFFFE32e2c1`**（= MAC 的 EUI-64，正确） |
| `server_address` | `localhost` | `localhost` |
| `serv_port_up/down` | 1680 / 1680 | 1680 / 1680 |
| `keepalive_interval` | 10 s | — |
| `stat_interval` | 3600 s | — |
| `push_timeout_ms` | 100 | — |
| `forward_crc_valid` | **true** | — |
| `forward_crc_error` | **false** | — |
| `forward_crc_disabled` | **false** | — |

**转发链路已就绪**：`lora_pkt_fwd` 以 Semtech UDP JSON（`PUSH_DATA` / `rxpk`）发到
`localhost:1680`。机上已有两个接收脚本：

- `/home/rxhf/lora_receiver.py`：打印 freq/RSSI/SNR/CRC/datr/payload hex，并回
  `PUSH_ACK`/`PULL_ACK` —— **通用接收器，正合我们使用**。
- `/home/rxhf/lora_test.py`：100 包测试，但**只接受 `stat==1`（CRC 有效）且载荷匹配
  `HELLO_<n>`** 的包；`lora_test.csv` **只有表头、0 条记录** → 该测试从未收到过有效帧。

服务：`pktfwd.service` → `/opt/risinghf/pktfwd/pktfwd.sh` → `./pktfwdbin`，
`Restart=always`，`After=network-online.target`。

## 4 与节点侧的三处不匹配（这就是收不到帧的原因）

| # | 网关 | 我们的节点（5 板） | 后果 |
|---|---|---|---|
| 1 | 最低信道 **470.300 MHz** | **470.000 MHz** | 差 300 kHz，BW125 外 → **收不到** |
| 2 | `lorawan_public: true` → 公有 sync **0x34** | sync **18 (0x12)** 私有 | 同步字不符 → **根本不解调** |
| 3 | 只转 CRC 有效帧 | LRN1 是自定义格式 + 自定义 CRC32，**非 LoRaWAN** | CRC 判定失败 → **不转发** |

## 5 推荐方案：改网关（节点零改动）

在 `/opt/risinghf/pktfwd/` 新建 `global_conf_adhoc.json`（**不改原文件**），
把 8 个信道整体下移到 470.0–471.4 MHz，并放开同步字与 CRC：

```json
{
  "SX1301_conf": {
    "lorawan_public": false,
    "clksrc": 1,
    "antenna_gain": 0,
    "radio_0": { "enable": true, "type": "SX1255", "freq": 470300000,
                 "rssi_offset": -176.0, "tx_enable": false },
    "radio_1": { "enable": true, "type": "SX1255", "freq": 471100000,
                 "rssi_offset": -176.0, "tx_enable": false },
    "chan_multiSF_0": { "enable": true, "radio": 0, "if": -300000 },
    "chan_multiSF_1": { "enable": true, "radio": 0, "if": -100000 },
    "chan_multiSF_2": { "enable": true, "radio": 0, "if":  100000 },
    "chan_multiSF_3": { "enable": true, "radio": 0, "if":  300000 },
    "chan_multiSF_4": { "enable": true, "radio": 1, "if": -300000 },
    "chan_multiSF_5": { "enable": true, "radio": 1, "if": -100000 },
    "chan_multiSF_6": { "enable": true, "radio": 1, "if":  100000 },
    "chan_multiSF_7": { "enable": true, "radio": 1, "if":  300000 }
  },
  "gateway_conf": {
    "gateway_ID": "b827ebFFFE32e2c1",
    "server_address": "192.168.137.10",
    "serv_port_up": 1680, "serv_port_down": 1680,
    "keepalive_interval": 10, "stat_interval": 3600, "push_timeout_ms": 100,
    "forward_crc_valid": true,
    "forward_crc_error": true,
    "forward_crc_disabled": true
  }
}
```

信道映射（radio_0 = 470.3）：ch0=**470.000**、ch1=470.200、ch2=470.400、ch3=470.600；
（radio_1 = 471.1）：ch4=470.800、ch5=471.000、ch6=471.200、ch7=471.400。

切换与回滚：

```sh
cd /opt/risinghf/pktfwd
sudo ln -sfn global_conf_adhoc.json global_conf.json
sudo systemctl restart pktfwd
# 回滚
sudo ln -sfn global_conf_cn470_ch00_07.json global_conf.json && sudo systemctl restart pktfwd
```

把 `server_address` 指向 PC（`192.168.137.10`）后，**接收端在 Windows 上**，Pi 上无需装任何东西。

### 备选方案：改节点（网关只动两个开关）

- 节点频率 `470,000,000` → **`470,300,000`**（5 块板，一条命令）
- 网关仅改 `lorawan_public: false` + `forward_crc_disabled: true`

> 推荐前者：一次把 8 个信道都对齐，节点侧零改动，后续扩信道有余量。

## 6 已知风险：SX1301 对「非 LoRaWAN 帧」的解析（必须实测）

SX1301 的 multiSF 解调器按 **LoRaWAN 显式头**工作：把载荷首字节当 MHDR 解析长度与
CRC 形式。我们的 LRN1 首字节是 `'L' (0x4C)`，不是合法 MHDR，可能出现：

- 长度解析错 → 交付截断或超长载荷；
- 仍标 `stat=0`（CRC 错）→ 只能靠 `forward_crc_disabled/forward_crc_error` 转发。

**不能假设它一定工作。** 若不工作，两条退路：

1. 节点侧加 **2 字节 LoRaWAN 兼容头**（MHDR + 长度），载荷仍是 LRN1；
   需同步改 `decoder.py` 与主机解析。
2. 改用 SX1276/SX1262 类**单通道收发器**做原始收包（SX1301 本非为此设计）。

## 7 验收步骤

1. 网关上重启 `pktfwd`，`journalctl -u pktfwd -n 30` 检查信道初始化是否报错。
2. PC 上起接收器（UDP 1680）。
3. 4 块 tx 板按 10 s 周期发 LRN1，观察 `rxpk`：
   - 有 `rxpk` 且 `freq` 落在 470.0–471.4 → 射频通；
   - `stat=0` → CRC/头解析问题（§6）；
   - `data` base64 解码后首字节不是 `0x4C` → 被截断或错位。
4. 记录每帧 `freq / rssi / lsnr / datr / stat`，回填本文档。

## 8 我们侧要跟着改的

| 项 | 现状 | 方案 A 后 | 备选方案 B 后 |
|---|---|---|---|
| 节点频率 | 470,000,000 | 不变 | 470,300,000 |
| 节点 sync | 18 (0x12) | 不变 | 不变 |
| 网关 `lorawan_public` | true | **false** | **false** |
| 网关 CRC 转发 | 只转有效 | **全转** | **全转** |
| 接收端位置 | Pi 本机 | **Windows 192.168.137.10** | Pi 本机 |
| `lora_reader` 来源 | 串口 `lora.ref.v1` | 新增 **UDP/JSON 适配器** | 同左 |
| 上报周期 | 10 s | 不变（8 信道下可缩短） | 同左 |

## 9 安全提示（不阻塞）

Raspbian 8 + OpenSSH 6.7p1 已停止维护（CVE-2016-6210 用户枚举、CVE-2018-15473 等）。
RHF 固件与该镜像耦合，**升级系统风险高于收益**，建议以网络隔离为主：仅接内网、
改密钥登录、限制源地址。
