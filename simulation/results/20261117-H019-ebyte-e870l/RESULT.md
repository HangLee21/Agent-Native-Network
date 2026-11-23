# 亿佰特 E870-L 网关接入（2026-11-17 打通）

## 结论

**端到端打通**：Ebyte `E870-L470LG11-S` 网关接收 A/B/C 三块 EoRa 节点的 LRN1 帧，
经 UDP 转发到 PC，由 `topology_server` 解码，Studio 页面显示
`LoRa 接收器 E870L-470 · 正在实收`。

## 设备

| 项 | 值 |
|---|---|
| 型号 | **E870-L470LG11-S**（成都亿佰特 Ebyte） |
| 固件 | FW-9252-0-10 |
| SN | S5203996S |
| MAC | `a4:f0:0f:e5:7b:83` |
| 主机名 | `E870L-ETH`（DHCP 上报） |
| 地址 | **192.168.137.11**（由本机迷你 DHCP 分配，租约表固定） |
| 管理界面 | `http://192.168.137.11/`，标题 `NetConfig` |
| 默认账号 | `admin` / `admin`（**登录框 placeholder 里就写着**，非猜测） |

### 射频（与旧网关 RHF2S008 完全一致）

```
radio0_freq = 470600000     radio1_freq = 471400000
→ 8 信道: 470.3 / 470.5 / 470.7 / 470.9 / 471.1 / 471.3 / 471.5 / 471.7 MHz
→ ch1(实测) = 470.5 MHz，与 A/B/C 板的发射频率一致
```

## 改了三个字段

原配置在 `basic.json` 里指向 `192.168.1.1:1700`——**一个不存在的服务器**，
所以它静默无输出，看起来像"没工作"。

| 字段 | 原值 | 新值 |
|---|---|---|
| `server_address` | `192.168.1.1` | **`192.168.137.10`** |
| `serv_port_up` | `1700` | **`1680`** |
| `gateway_ID` | `FFFFFFFFFFFFFFFF` | **`a4f00fe57b830000`** |

原始配置备份：`basic_before.json`、`static.json`（同目录）。

改完必须 **重启设备** 才生效（`POST /DeviceContrl` body `web set device reboot`）。

## 管理 API（逆向自其 Web 前端）

登录：

```
GET  /login.js                     → RAND_KEY（每次开机随机）
POST /loginsubmit.json             body = HMAC-SHA1(key=密码, msg=用户名+RAND_KEY) 的十六进制
                                   → 返回 token
```

所有后续请求都要带 **`token=<token>&date=<毫秒时间戳>`**，**少了 date 会退回登录页**。

配置：

```
GET  /basic.json?token=..&date=..     读配置
POST /basic.json?token=..&date=..     写配置（JSON body）
POST /DeviceContrl?token=..&date=..   应用 / "web set device reboot" 重启
```

## 验证结果

```
gateway_id : a4f00fe57b830000 / E870L-470
state      : receiving   chan=1  freq=470.5 MHz
frames=14  lrn1=14  foreign=0  bad=0
reports    : A(2 邻居) B(2) C(2)
```

Studio 页面（无头渲染）：4 个节点、6 条连线、节点列表 `E870L-470, B, A, C`。

## 复现步骤

1. 网线接 PC，迷你 DHCP 给到 `192.168.137.11`
2. 浏览器打开 `http://192.168.137.11/`，用 `admin/admin` 登录
3. 改 `server_address` 为 PC 地址、`serv_port_up` 为 1680，保存并重启
4. PC 上跑 `python -m tools.mid_baseline.gateway_probe.topology_server --udp-port 1680 --port 8780 --labels <labels.json>`
5. 打开 Studio（8794）

## 注意

- 该网关**没有 `lorawan_public` 之类的显式开关**，同步字由 `lora_region` 决定；实测 A 板的
  sync 0x34 能正常被接收。
- 端口扫描还看到 25/110/143 接受连接但无 banner，判断为固件 TCP 栈特性，未深究。
