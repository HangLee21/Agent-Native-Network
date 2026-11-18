# 日常使用手册

这份文档回答一个问题：**我要做某件事，该跑哪条命令。**

所有命令都在仓库根目录 `D:\Multi-Agent Network` 下执行。

---

## 0. 先看一张表

| 你要做什么 | 跑什么 | 需要管理员 |
|---|---|---|
| 上网 / 用有线网 | `.\netmode.ps1 campus` | ✅ |
| 看 LoRa 拓扑（网关接着） | `.\netmode.ps1 lab` → 双击 `START_STUDIO.cmd` | ✅ 仅第一步 |
| 烧一个新的树莓派 | `.\netmode.ps1 pi` | ✅ |
| 给节点刷固件 | `fleet update <镜像>` | ❌ |
| 看机群状态 | `fleet status` | ❌ |
| 改网关转发地址 | 浏览器开 `http://192.168.137.11` | ❌ |
| 切换节点显示编号 | `refresh_labels.py` | ❌ |

---

## 1. 网络模式：先切对，再干活

**一块网口三种用途，靠模式切换，不要手动加地址。**

```powershell
.\tools\mid_baseline\gateway_probe\netmode.ps1 campus   # 有线网，正常上网
.\tools\mid_baseline\gateway_probe\netmode.ps1 lab      # 接 LoRa 网关
.\tools\mid_baseline\gateway_probe\netmode.ps1 pi       # 烧树莓派
.\tools\mid_baseline\gateway_probe\netmode.ps1 status   # 看当前状态
```

| 模式 | 网口状态 | 能不能上网 |
|---|---|---|
| `campus` | DHCP | ✅ |
| `lab` | `192.168.137.10/24`，**无网关无 DNS** | ❌（但 WiFi 照常上网） |
| `pi` | 不配地址（169.254） | ❌（WiFi 照常） |

> **关键**：`lab` 和 `pi` 模式**没有默认路由**，所以绝不可能抢走 WiFi 的上网流量。
> 这是之前代理被搞炸的根本原因——那次我加了 `10.0.0.0/24` 等直连路由没清理。

**用完记得切回 `campus`。**

---

## 2. 看 LoRa 拓扑

### 步骤

```powershell
.\tools\mid_baseline\gateway_probe\netmode.ps1 lab     # 管理员
```
然后双击 **`START_STUDIO.cmd`**，浏览器自动打开 `http://127.0.0.1:8794/`。

### 启动脚本会做什么

1. 检查 `topology_server`(8780) 与 `Studio`(8794) 是否在跑，在跑就**复用**
2. 没跑就拉起（Studio 用 `legacy_local` 模式，接本机接收器）
3. 等到真正能应答，再打开浏览器
4. 打印网关名 / 帧数 / 报告者数

### 正常状态长什么样

```
gateway : E870L-470
frames  : 1234   reports: 3
节点列表: E870L-470, 1, 2, 3
```

### 页面上的东西

| 元素 | 含义 |
|---|---|
| 中间青色环 | 网关（接收器） |
| 节点 1/2/3 | 三块 EoRa 板（编号来自设备自身） |
| 板间箭头 | ESP-NOW 邻居关系 |
| 「来源」 | 本机 UDP 接收器 / 远程网关 / 串口节点 |
| 「布局」 | 自动 / 手动 / GPS |

---

## 3. 烧一个新的树莓派

```powershell
.\tools\mid_baseline\gateway_probe\netmode.ps1 pi        # 管理员
```

1. 用 Raspberry Pi Imager 烧 TF 卡（预先设好主机名、用户 `eora`、WiFi）
2. 插卡上电，等 60–90 秒
3. 找它的地址：`arp -a` 里看 `169.254.x.x`
4. `ssh eora@169.254.x.x`

### 入网（一次授权，之后零点击）

```bash
sudo ~/eora/pi_enroll.sh eora-air-04 tskey-auth-xxxx
```

> auth key 在 https://login.tailscale.com/admin/settings/keys 生成，
> 记得勾 **Reusable** + **Pre-approved**，**Ephemeral 关**。

### 部署节点读取服务

把 `node_reader.py` / `node_reader.service` / `node_update.py` 推到 Pi 上（脚本会做），
然后：

```bash
sudo systemctl enable --now node_reader
```

---

## 4. 给节点刷固件（不需要碰网线）

节点挂在 Pi 的 USB 上，**Pi 自己就是烧录器**。

```powershell
fleet status                       # 先看谁在线
fleet update BUILD-xxx\images\mid_edge.bin
```

它会对每台 Pi 执行：刷 `0x10000` → 读回 `build_id` 校验 → 不一致自动回滚 → 重启读取服务。

> 需要 `EORA_PASS` 环境变量（设备 sudo 密码）。

---

## 5. 换网关 / 改网关参数

### 进管理界面

`lab` 模式下浏览器打开 **`http://192.168.137.11`**，账号 `admin` / `admin`
（登录框 placeholder 里就写着）。

### 三处必须对

| 字段 | 值 | 为什么 |
|---|---|---|
| `server_address` | `192.168.137.10` | 往你的 PC 转发 |
| `serv_port_up` | `1680` | 接收端口 |
| `gateway_ID` | 任意 16 位十六进制 | 包的来源标识 |

改完**必须重启设备**才生效。

### 射频必须和板子对上

```
radio0_freq = 470600000   radio1_freq = 471400000
→ 8 信道: 470.3 / 470.5 / 470.7 / 470.9 / 471.1 / 471.3 / 471.5 / 471.7
```

板子的发射频率必须落在这 8 个之一（当前 470.5 MHz）。

---

## 6. 节点编号：只听真话，不预声明

**界面上出现的每个节点都必须是真实收到的**——没连上就不显示。
仓库里的 `config/fleet.default.json` 是**空名单**，不预填任何编号。

> 之前这里预写了 1/2/3，导致一台设备都没连也显示 1 2 3。
> 那是拿配置冒充事实，已废止。

### 加新节点（一条命令，40 台也一样）

```powershell
python tools\mid_baseline\fleet\refresh_labels.py --field node_number
```

它会：

1. 从 Tailscale 列出所有 `eora-air-*` 设备
2. SSH 进每台，读该节点自己上报的 `node_number`（与 OLED 一致）
3. 同时写两份文件
   - `.local\mid\pi\labels.json` —— 给 topology_server 显示名字
   - `data\fleet.json` —— 给 Studio 的编号表

然后重跑 `START_STUDIO.cmd` 生效。

### 为什么不能手写名单

手写的 MAC → 编号表在 40 台规模下必然过期：换板、重烧、改编号都会让它和现实脱节，
而且**未连接的节点会被当成已存在**显示出来——那是在骗自己。

### 想改回字母

```powershell
python tools\mid_baseline\fleet\refresh_labels.py --field device_label
```

---

## 7. 出问题时怎么查

### 页面空白 / 没有数据

按顺序查：

```powershell
.\tools\mid_baseline\gateway_probe\netmode.ps1 status    # 网口是不是 lab 且有 192.168.137.10
Get-NetUDPEndpoint -LocalPort 1680                       # 接收端在不在听
Test-NetConnection 192.168.137.11 -Port 80               # 网关能不能访问
```

### 常见症状对照表

| 症状 | 原因 | 处理 |
|---|---|---|
| 页面空白，`sources` 里 `available=false` | 网关没在转发 | 查网关 `server_address` / 重启网关 |
| 网关打不开 | 网口不在 `lab` 模式 | `.\netmode.ps1 lab` |
| 只有校园门户能开，别的网站打不开 | 网口残留静态地址，代理选路被带偏 | `.\netmode.ps1 campus` + 重启代理软件 |
| `udp/1680 is already in use` | 有两个接收端在抢端口 | 杀掉多余进程，或换 `--udp-port` |
| 节点显示 MAC 而不是编号 | 标签表过期 | 跑 `refresh_labels.py` |
| `fleet status` 里某台 offline | Tailscale 掉线 | `ssh` 进去 `sudo systemctl restart tailscaled` |

### 端口占用

```
8780  topology_server  (UDP 1680 → HTTP)
8794  Studio           (页面)
1680  网关数据入口
67    迷你 DHCP（只在烧新 Pi 且无链路本地时用）
```

---

## 8. 一条原则

> **每做一件事之前先切对模式，做完切回 `campus`。**

`lab` / `pi` 模式没有默认路由，所以安全；但只要有人手工 `New-NetIPAddress` 加了别的网段，
就又会把代理搞炸。**加地址只用 `netmode.ps1`，不要手敲。**
