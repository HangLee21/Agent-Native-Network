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

## 7 机群管理（Tailscale + fleet）

### 问题

Pi 走校园网 DHCP，**地址每天变**；mDNS 被校园 WiFi 隔离，`eora-air-0X.local` 解析不到；
校园网还过滤 ICMP，`ping` 不通不代表设备死了。三台就已经管不过来，几十台更不可能靠台账。

实测三台的 WiFi 地址落在**三个不同网段**：

```
eora-air-01  183.173.46.234/21
eora-air-02  183.173.100.29/21
eora-air-03  101.5.13.81/21
```

### 方案：管理面与数据面分离

```
管理面  Tailscale  →  设备名 eora-air-NN，永久有效
数据面  WiFi       →  上网、NTP、遥测回传；地址怎么变都不影响运维
```

### 入网（一次授权，之后零点击）

在管理后台生成 **reusable auth key**（Ephemeral 关，避免离线设备被删除），然后：

```bash
sudo ~/eora/pi_enroll.sh eora-air-04 tskey-auth-xxxx
```

脚本做四件事：设主机名 → **强制 IPv4 优先** → 装包 → 用 key 入网。

> ⚠️ **节点密钥默认约 180 天过期**。长期外场设备建议在后台逐台 **Disable key expiry**，
> 或用 Tags 入网（带 tag 的设备不过期，但需要先配 ACL）。

### 日常操作

```powershell
fleet status                 # 全队：节点/build/WiFi/网线/磁盘/温度/运行时长
fleet update mid_edge.bin    # 全部刷同一版固件，逐台校验 + 失败回滚
fleet run "df -h /"          # 批量执行
fleet logs eora-air-02       # 看某台节点日志
```

`fleet update` 需要 `EORA_PASS` 环境变量（设备 sudo 密码）。

### 远程刷节点（这是它存在的理由）

节点挂在 Pi 的 USB 上，**所以 Pi 自己就能刷它**，不需要人去拔板子：

```
PC 编译一次 .bin → Tailscale 分发 → 每台 Pi 本地 esptool 刷自己的节点
                                  → 读回 build_id 校验
                                  → 不一致自动回滚上一版
```

实测（`eora-air-01`，A 板）：

```
flashing mid_edge.bin -> 0x10000
node reports: e72eaf651f100dfd
VERIFIED: node is running the image that was just flashed
```

## 8 踩过的坑（都已在脚本里处理）

| 坑 | 现象 | 修法 |
|---|---|---|
| 校园网 IPv6 不通但 DNS 优先返回 AAAA | 装包、入网、`tailscale up` 全部挂住 | `/etc/gai.conf` 加强 `precedence ::ffff:0:0/96 100`，WiFi profile 可设 `ipv6.method disabled` |
| 本机多网卡时 `255.255.255.255` 走错网卡 | 直连网线上的 Pi 收不到 DHCP OFFER | 同时发往链路广播 `169.254.255.255` |
| DHCP 守护收到带主机名的 DISCOVER 就崩 | 日志停在半路，设备拿不到地址 | 补初始化；另加看门狗兜底 |
| 硬断电后 ext4 在日志里留 NUL 字节 | `grep` 判定为二进制，节点信息空 | 用 `grep -a` |
| 开串口会拉 DTR/RTS 复位 ESP32 | 探针读不到任何回复 | 打开前 `dtr=False, rts=False`，打开后等 2.5 s |
| `node_reader` 独占串口 | 手工探针报 "multiple access on port" | 先 `systemctl stop node_reader` |

## 9 已知注意点

- **Pi 4 的 USB 总供电只有 1.2 A**，接节点没问题；接多个需带外部供电的 Hub。
- 单独一个节点时 `route_request` 约 **107 次/分钟**（不停为不存在的邻居发 RREQ），
  这是单节点空转的正常表现，但在大规模下正是泛洪问题的来源。
- 校园网 IP 会变、可能限制入站连接，**不要当控制链路**；外场应用 Pi 自建 AP 或 4G。
- Tailscale 在校园网偶发掉线（NAT 映射超时），`systemctl restart tailscaled` 可恢复。
