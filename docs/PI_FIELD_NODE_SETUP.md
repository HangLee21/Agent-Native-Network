# 树莓派作机载节点（1 台 Pi + 1 个 EoRa 节点）配置手册

实测日期：2026-11-16 · 设备：Raspberry Pi 4 Model B（64 GB TF 卡，Debian 13 trixie）

## 1 角色

```
EoRa 节点 ──USB 串口(460800, mid.serial.v1)──► 树莓派 ──WiFi──► 校园网/外场 AP
                                                 │
                                                 └──► 本机有界日志（node_reader）
```

- 一台 Pi 带**一个**节点，节点烧录时已设"上电自动启动"（`discovery_saved=true`、`discovery_autostart=true`），无需人工干预。
- Pi 的职责只有两件：**保持串口会话**、**把事件收成小体积日志**。

## 2 烧录时就要配好的（Raspberry Pi Imager 高级设置）

| 项 | 值 | 说明 |
|---|---|---|
| 主机名 | `eora-air-01`、`eora-air-02`… | 之后靠 `<主机名>.local` 访问 |
| 用户名 | `eora` | 统一身份 |
| SSH | **启用**，密码认证 | 首次登录用；之后改成密钥 |
| WiFi | 校园网在 Imager 里**配不了**，见下方说明 | 只有 WPA2 个人版能在这里设 |
| 时区 | `Asia/Shanghai` | 日志对齐 |

> **注意**：本项目的校园网是 **`Tsinghua-Secure`（WPA2-Enterprise / PEAP-MSCHAPv2）**，
> 认证用**校园网账号**（账号名，不是 SSID）。Imager 只能配 WPA2 个人版，配不了 802.1X，
> 因此校园网必须在开机后用 `pi_wifi_8021x.sh` 配置。

## 3 开机后一次性配置

```bash
scp pi_provision.sh eora@<ip>:~/
ssh eora@<ip>
sudo ~/pi_provision.sh eora-air-02            # 只配系统
sudo ~/pi_provision.sh eora-air-02 <wifi-ssid>  # 可选：WPA2 个人版 WiFi（交互输入密码）
```

脚本做的事（幂等）：

- 设主机名 + 修 `/etc/hosts`（避免 sudo 卡名字解析）
- 以太网 **DHCP + 链路本地回退**，**不写死任何 IP**
- 禁用 `NetworkManager-wait-online`（省 ~10 s 开机）与 cloud-init
- 启用 avahi（mDNS），设时区，装 `python3-serial`，加 `dialout` 组
- 可选：加 WPA2 个人 WiFi 并把它的路由 metric 设为 100

校园网（802.1X）另配：

```bash
sudo ~/pi_wifi_8021x.sh                 # 默认 Tsinghua-Secure，交互输入学号/密码
```

## 4 日志服务 `node_reader`

```bash
sudo systemctl status node_reader      # active / enabled
tail -f ~/eora/logs/node_events.jsonl
```

设计要点（为什么不是 `cat > log`）：

| 问题 | 做法 |
|---|---|
| 节点每秒约 8 条事件，原样存约 **175 MB/天** | 高频事件**按分钟聚合计数**；只有状态变化/故障类**逐条写** |
| 打开串口会拉 DTR/RTS → ESP32 复位 | 打开前 `dtr=False, rts=False`，**打开后等 2.5 s** 再发命令 |
| 每条命令重开端口 = 每次复位 | 整个会话复用同一个连接 |
| 节点自行重启或 USB 掉线 | 30 s 无数据即重开串口，并写一条 `session:reopen` |
| 日志无限增长 | `node_events.jsonl` 单文件 2 MiB，保留 3 份 → **上限 8 MiB** |

实测：**75 秒 417 字节（2 行）**，约 **480 KB/天**，够存两周以上。

写入内容示例：

```json
{"t":...,"session":"open","node_id":"90:da:72:48:a4:f8","build_id":"…","mode":"active","group":31}
{"t":...,"aggregate":{"tx_queued":15,"route_waiting":13,"tx_submit":13,"tx_link_ok":18,
                      "route_no_route":117,"route_request":107,"route_accepted":10}}
```

## 5 访问方式

| 场景 | 方式 |
|---|---|
| 同一 WiFi（校园网/个人路由） | `ssh eora@eora-air-01.local` |
| 直连网线（无 DHCP） | 链路本地 + mDNS：`ssh eora@eora-air-01.local` |
| 已知 IP | `ssh eora@<ip>` |

**永远不用记 IP**——地址会随网络变化，名字不变。

## 6 SSH 加固（已生效）

`/etc/ssh/sshd_config.d/10-eora.conf`：

```
PubkeyAuthentication yes
PasswordAuthentication no
Match Address 169.254.0.0/16
    PasswordAuthentication yes
```

| 路径 | 结果 |
|---|---|
| 密钥 · 任意网络 | ✅ |
| 密码 · 校园网 | ❌ 拒绝 |
| 密码 · 直连网线 | ✅ **救命通道**（密钥丢失时插网线即可进入） |

## 7 已知注意点

- **Pi 4 的 USB 总供电只有 1.2 A**，接节点没问题；接多个需带外部供电的 Hub。
- 单独一个节点时 `route_request` 约 **107 次/分钟**（不停为不存在的邻居发 RREQ），
  这是单节点空转的正常表现，但在大规模下正是泛洪问题的来源。
- 校园网 IP 会变、可能限制入站连接，**不要当控制链路**；外场应用 Pi 自建 AP 或 4G。
