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

## 3. 烧树莓派（批量，不用一台台插网线）

身份写在 SD 卡里；首次启动依赖可用的校园网和 Tailscale。免网线流程需要在目标设备上实际验证。

### 一次性准备（只做一次）

`.local\mid\pi\device.env`（**不进版本库**，放敏感信息）：

```
WIFI_SSID=Tsinghua-Secure
WIFI_IDENTITY=hli21
WIFI_PASSWORD=你的校园网密码
TAILSCALE_AUTHKEY=tskey-auth-....     ← Reusable + Pre-approved，Ephemeral 关
```

制卡电脑还需要已有机群管理公钥 `%USERPROFILE%\.ssh\id_ed25519_eora.pub`，以及与之配套的 SSH 别名配置和私钥。公钥缺失或格式错误时，制卡会停止且不修改卡；请联系管理员恢复，勿复制或提供私钥。

### 每张卡

1. **Raspberry Pi Imager** 写镜像：用户名 `eora`、开启 SSH、填入你的公钥
2. 双击 **`MK_CARD.cmd`** → 输入盘符（如 `E:`）→ 输入编号（如 `7`）
3. 卡插进 Pi，上电

Pi 首次启动后会尝试完成以下步骤：

```
设主机名 eora-air-07
给 eora 账户登记机群管理公钥，保留已有 SSH 授权
建 802.1X WiFi 配置（Imager 做不了这个）
装 Tailscale + 用 auth key 入网
装 pyserial / esptool
部署 node_reader 与刷写工具，启动服务
全部成功后自动 disable（下次开机零开销）
```

制卡时会保存原文件到卡内的 `eora-backup-*` 目录，并同步 NoCloud 实例号；不要删除备份。若中途失败，可插回电脑检查卡内 `eora-install.log`、`eora-firstboot.log` 和 `eora-status.txt`；服务未完成时会在后续启动重试。日志不存在也可能表示首次启动流程未运行，不能视为成功。

### 一次做多张

```
MK_CARD.cmd   E:  7
MK_CARD.cmd   F:  8
MK_CARD.cmd   G:  9
```

`MK_CARD.cmd --list` 可以看哪些卡已经配好。

节点入网且本机的别名和名称解析已配置后，可按编号登录，例如 `ssh eora-air-05` 或 `ssh eora-air-105`。新节点首次入网和名称解析仍需在现场验证。

### 之后

```
双击 FLEET_STATUS.cmd    ← 看它在不在、跑什么固件
双击 FLASH_NODES.cmd     ← 给它的节点刷固件
```

> 为什么以前要插网线：镜像里没有 WiFi/Tailscale 配置，主机名和编号也得手工设。
> 现在这两件事都写进卡里了，**网线只在排查故障时才用**。

---

## 4. 给节点刷固件（双击即可）

**双击仓库根目录的 `FLASH_NODES.cmd`。**

它会按顺序做四件事，任何一步不满足都会直接说清楚原因：

```
== 1/4 fleet reachability     ← 检查 Tailscale 与在线的 Pi
== 2/4 image                  ← 自动选 BUILD-* 里最新的 mid_edge.bin
== 3/4 credential             ← 首次输入设备密码，之后记在 .local 里
== 4/4 flashing               ← 逐台：停读取服务 → esptool → 校验 build_id → 重启服务
```

### 它会自己修的东西

| 缺什么 | 结果 |
|---|---|
| Pi 上没有 `node_update.py` / `pi_node_probe.py` | **自动推送** |
| Pi 上没装 `esptool` | **自动 pip 安装**（一次性，约 30 秒） |
| 刷完 SSH 会话断开 | 只要出现 `VERIFIED` 就判成功，不误报 |

### 为什么必须校验

刷写后用 `info` 读回 `build_id` 比对，**不一致会自动回滚**到上一版。
所以看到 `VERIFIED` 才是真的成功，不是"命令没报错"。

### 只想刷一台

```powershell
.\FLASH_NODES.cmd --only eora-air-02
```

### 看有哪些镜像

```powershell
.\FLASH_NODES.cmd --list
```

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

### 新节点不需要登记就会出现

设备一发帧就被登记（`state.py` 按收到的报告建节点，不查名单）。
没有编号的节点显示 **MAC 尾号**，例如 `48:aa:bb`，不会显示成"故障"。

编号只是**显示名**，不是准入门槛。

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


## LoRa 观测记录与回放

在 LoRa 页面选择当前接收来源，点击“开始记录”；走测结束后点击“结束记录”。选择实验并打开回放，通过滑块选择历史快照，播放或暂停；“索引观测变化”逐页生成事件列表，选择事件可跳转。返回实时后恢复当前接收来源。回放时间是电脑的观察时间，滑块是快照序号，不保证等距时间。

事件以历史快照中的明确状态为依据；来源切换、中断或邻居缺行不推定无线断链。RSSI、SNR、信道和年龄按各自来源显示；上行质量中的“序号覆盖率”不是实测空口成功率。状态块和 GPS 块仅在报告提供时显示，有效定位才用于 GPS 地图。上行 RSSI 趋势仅覆盖当前加载页，按报告身份去重。

GPS 样本年龄缺失时详情显示未知；地图只能按报告收报年龄这一时间下界作暂时展示，不能据此证明定位仍新鲜。

记录状态若提示异常中止，需查看提示原因；重新打开页面可读取当前服务报告的错误。回放接口使用当前 Studio 同源，不受“网关地址”输入框影响。
