# 操作员手册（一页速查 + 全部约定）

面向两类人：**开发/运维（你，有私钥）** 和 **现场运维（同事，用账号密码）**。
所有相关文档见文末索引。

---

## 一、两台机器的分工

| | 你的电脑 | 同事的电脑 |
|---|---|---|
| 私钥 `id_ed25519_eora` | ✅ 有 | ❌ **没有** |
| 登录方式 | **私钥** | **账号 + 密码** |
| Tailscale | ✅ 装，加入组织 tailnet | ✅ 装，加入**同一个**组织 tailnet |
| 做卡 | ✅ | ✅ |
| 刷板 | ✅ | ✅（密码通道） |
| 编译固件 / 前端 | ✅ | ❌ |

> 两个人**都不需要用对方的账号**：Tailscale 用组织 tailnet，各登录各的。

---

## 二、每台电脑上的配置文件

### 2.1 你的 `D:\ops\site.env`

```ini
WIFI_SSID=现场WiFi名称
WIFI_AUTH=psk
WIFI_PASSWORD=现场WiFi密码
TAILSCALE_AUTHKEY=组织里自己生成的一次性key
# 你的机器有私钥，不需要密码字段
```

### 2.2 同事的 `D:\ops\site.env`

```ini
WIFI_SSID=现场WiFi名称
WIFI_AUTH=psk
WIFI_PASSWORD=现场WiFi密码
TAILSCALE_AUTHKEY=组织里自己生成的一次性key

# 关键：他没有私钥，必须靠密码
SSH_PASSWORD=现场统一口令
```

> `SSH_PASSWORD` 会写进卡：设 `eora` 的密码并开启 `PasswordAuthentication`。

### 2.3 同事要用 fleet 工具刷板时，还要设两个环境变量

```powershell
$env:EORA_SSH_PASSWORD = '现场统一口令'   # 用于 SSH 登录
$env:EORA_PASS         = '同一口令'        # 用于 Pi 上的 sudo
```

> 工具检测到**没有私钥且有 `EORA_SSH_PASSWORD`** 时，会自动改走密码通道
> （用 Windows OpenSSH 的 `SSH_ASKPASS`，不需要 sshpass / paramiko）。

想显式指定、不靠推断：

```powershell
$env:EORA_SSH_TRANSPORT = 'password'      # 或 'key'
```

### 2.4 密码通道覆盖哪些操作

| 操作 | 走密码通道 | 说明 |
|---|:--:|---|
| `fleet.py status` | ✅ | 每条命令都经 `run_ssh` |
| `fleet.py run "..."` | ✅ | 同上 |
| `fleet.py update <镜像>` | ✅ | 先 scp 推 helper（`push_file`），再远程执行 |
| `fleet.py push <镜像>` | ✅ | scp 走密码通道 |
| `fleet.py group` | ✅ | 停/起 node_reader + 串口命令 |
| `fleet.py logs` | ✅ | |
| `FLASH_NODES.cmd` | ✅ | 它转调 `fleet.py update`，并保留父进程环境变量 |
| 做卡 `MK_CARD.cmd` | — | 纯本机操作，与 SSH 无关 |

---

## 三、做卡（两人都能做）

### 3.1 必填字段（就 7 个）

| 键 | 必填 | 说明 |
|---|:--:|---|
| `WIFI_SSID` | ✅ | |
| `WIFI_AUTH` | 建议 | `psk` / `eap`（默认 eap） |
| `WIFI_PASSWORD` | ✅ | |
| `WIFI_IDENTITY` | 仅 eap | 802.1X 账号 |
| `TAILSCALE_AUTHKEY` | 远程要用就填 | 留空 = 不装 Tailscale |
| `SSH_PASSWORD` | 同事必填 | 设密码并开密码登录 |
| `SSH_ALLOW_PASSWORD` | 可选 | 只开开关不改密码 |

### 3.2 每张卡填编号

```powershell
# 单张
MK_CARD.cmd                       # 回车自动找卡，再输编号

# 批量（自动编号、自动等下一张）
mkcard.py --batch --from 6 --count 15 --env D:\ops\site.env
```

**号段约定**：

| 谁 | 号段 |
|---|---|
| 你（调试） | 1–5 |
| 同事（生产 15 张） | 6–20 |

### 3.3 做卡机需要的东西

| 项 | 说明 |
|---|---|
| Python 3 + PyYAML | |
| `fleet.pub` | **你提供**，一行一把公钥；可放多把 |
| Imager 写好的基础卡 | |

---

## 四、开密码登录（分两种情况）

### 新卡

`site.env` 里设 `SSH_PASSWORD` 即可，首启自动完成：

```
2b/6 eora password set
2c/6 ssh password login enabled
```

### 老卡（现有 5 块，做卡时还没这个功能）

**只有你能做**（需要私钥）：

```powershell
cd "D:\Multi-Agent Network"
$env:EORA_NEW_PASSWORD = '现场统一口令'
python tools\mid_baseline\fleet\enable_ssh_password.py --all
```

它会逐台：设 `eora` 密码 → 写 `sshd_config.d/20-eora-password.conf` → reload ssh →
回显 `passwordauthentication yes` 和 `passwd -S eora` 的结果。

只开开关、不改密码：

```powershell
python tools\mid_baseline\fleet\enable_ssh_password.py --all --allow-only
```

> 幂等：重复执行不会变坏。

### 验证对方能登

```powershell
ssh -o PubkeyAuthentication=no eora@eora-air-06      # 应该提示输入密码
```

---

## 五、Tailscale：谁必须装

| 场景 | 需要装吗 |
|---|---|
| 只做卡 | ❌ |
| 在同一局域网 SSH | ❌ |
| **跨网络 SSH / 刷板** | ✅ **必须** |

**密码解决"你是谁"，Tailscale 解决"怎么找到那台机器"** —— 两件事。

树莓派在 WiFi 后面没有公网 IP，跨网络只能靠 tailnet 地址（`100.x.x.x`）。

两人都装、都加入**同一个组织 tailnet**（各自账号），设备与卡片都在这个组织里。

---

## 六、两个 group（本地 5 块 / 远程 15 块）

```powershell
# 本地五块 -> group 1
fleet.py group --group 1 --channel 1 --only eora-air-01 eora-air-02 eora-air-03 eora-air-04 eora-air-05

# 远程十五块 -> group 2
fleet.py group --group 2 --channel 6 --only eora-air-06 ... eora-air-20
```

**核对返回的 `group_reported`，不能只看 `ok`。**

按组刷板：

```powershell
# 需要 config/fleet.groups.json（名字 -> 组号）
fleet.py update <镜像> --group 1
fleet.py update <镜像> --group 2
```

> group 隔离 ESP-NOW 组网与路由，**不需要重刷固件**（NVS 运行时配置）。

---

## 七、日常命令速查

### 你的电脑

```powershell
cd "D:\Multi-Agent Network"

# 机群总览（第一行会告诉你当前传输方式：tailnet / 本地主机表）
python tools\mid_baseline\fleet\fleet.py status

# 刷固件（全部 / 某一组 / 某几台）
python tools\mid_baseline\fleet\fleet.py update BUILD-xxx\images\mid_edge.bin
python tools\mid_baseline\fleet\fleet.py update BUILD-xxx\images\mid_edge.bin --group 2
python tools\mid_baseline\fleet\fleet.py update BUILD-xxx\images\mid_edge.bin --only eora-air-06

# 设 group / 信道
python tools\mid_baseline\fleet\fleet.py group --group 2 --channel 6 --only eora-air-06

# 做卡（调试）
python tools\mid_baseline\gateway_probe\mkcard.py --batch --from 1 --count 5 --env D:\ops\site.env
```

### 同事的电脑（无私有密钥）

```powershell
$env:EORA_SSH_PASSWORD = '现场统一口令'
$env:EORA_PASS         = '现场统一口令'

python fleet\fleet.py status
python fleet\fleet.py update <镜像> --group 2
```

---

## 八、故障判定表

| 现象 | 先看什么 |
|---|---|
| `fleet status` 说 Tailscale `NoState` | 网络问题，不是设备问题：管理员 `Restart-Service Tailscale` |
| `fleet status` 说"没有设备"但 tailnet 正常 | 卡片没上电/没连 WiFi；看卡上 `eora-status.txt` |
| 做卡报"拒绝写入：来自仓库内的开发配置" | 用 `--env` 指向现场文件，别用仓库里的 |
| 做卡报 `FAILED: 802.1X needs EORA_IDENTITY` | `WIFI_AUTH=eap` 却漏了 `WIFI_IDENTITY` |
| 首启卡在 `4a/6 时钟` | 树莓派无 RTC，等 NTP；超过 5 分钟检查 WiFi |
| 首启 `FAILED: tailscale installation` | 时钟没同步 → apt 拒签（已在 4a 步处理） |
| 对方 `ssh` 提示 `Permission denied (publickey)` | 老卡没开密码登录 → 跑 `enable_ssh_password.py` |
| 对方能 ping 通 IP 但 `ssh` 超时 | 大概率不在同一 tailnet |

---

## 九、卡里有什么 / 没有什么

详见 [CARD_CONTENTS.md](CARD_CONTENTS.md)。

一句话：**身份（编号/主机名）+ WiFi + 可选 Tailscale key + 可选 SSH 密码 + 管理公钥 + 4 个 helper**。
**没有固件、没有私钥、没有仓库。**

---

## 十、文档索引

| 文档 | 内容 |
|---|---|
| **[SITE_OPERATOR_RUNBOOK.md](SITE_OPERATOR_RUNBOOK.md)** | **现场同事的逐步操作单（做卡 + 批量刷板）** |
| [CARD_CONTENTS.md](CARD_CONTENTS.md) | 卡上到底写了什么（逐项、含大小） |
| [BATCH_CARD_CHECKLIST.md](BATCH_CARD_CHECKLIST.md) | 批量做卡准备与检查清单 |
| [CARD_PROVISIONING_MODES.md](CARD_PROVISIONING_MODES.md) | WiFi 两种认证、Tailscale 三种模式、两台刷板机 |
| [DEV_PROD_SPLIT.md](DEV_PROD_SPLIT.md) | 开发/生产解耦、生产包内容、权限 |
| [FLEET_GROUPS.md](FLEET_GROUPS.md) | 两个 group 的隔离范围、信道分配、验收 |
| [PORT_TO_DEPLOY_PLAN.md](PORT_TO_DEPLOY_PLAN.md) | 推到 deploy 分支的移植清单 |
| [LRN1_FRAME.md](LRN1_FRAME.md) | LoRa 上行帧结构 |

---

## 十一、尚未完成（如实记录）

| 项 | 状态 |
|---|---|
| 现有 5 块板开密码登录 | ❌ **未执行**（Tailscale 当前 `NoState`，设备不可达） |
| 15 张生产卡实做 | ❌ 等现场 WiFi 与组织 tailnet key |
| 密码通道的实际验证 | ❌ 未验证（无可用主机）——实现为 `SSH_ASKPASS` 方式，需现场确认 |
| 设 group 1/2 | ❌ 等设备可达 |
