# 现场运维操作单（做卡 + 批量刷板）

对象：**没有私钥、用账号密码登录**的现场同事。
目标：把 15 张卡做好，并把固件刷进 15 块板。

> 本单按顺序执行，每步都有"检查点"。任何一步与预期不符，**停下来**，不要继续。

---

## 0. 前置条件（缺一项都做不下去）

| # | 条件 | 谁提供 | 怎么确认 |
|---|---|---|---|
| 1 | Tailscale 已装并登录**组织 tailnet** | 自己 | `tailscale status` 能看到自己 |
| 2 | 做卡包（含 `fleet/`） | 开发侧 | 目录里有 `MK_CARD.cmd`、`fleet\fleet.py` |
| 3 | `fleet.pub`（管理公钥） | 开发侧 | 在包的根目录 |
| 4 | 固件镜像 `mid_edge.bin` | **开发侧** | 有 `BUILD-*/images/mid_edge.bin` |
| 5 | Python 3 + PyYAML | 自己 | `python -c "import yaml"` |
| 6 | Raspberry Pi Imager | 自己 | — |
| 7 | `site.env`（第 1 步创建） | 自己 | — |

---

## 1. 写现场配置（一次性，5 分钟）

在包目录下新建 `site.env`：

```ini
WIFI_SSID=现场WiFi名称
WIFI_AUTH=psk
WIFI_PASSWORD=现场WiFi密码

# 组织里自己生成的 Tailscale key（一次性、24 小时过期）
TAILSCALE_AUTHKEY=tskey-auth-XXXX

# 关键：你没有私钥，靠这个密码登录
SSH_PASSWORD=现场统一口令
```

### 检查点

```powershell
python gateway_probe\mkcard.py --check --env site.env
```

预期输出：

```
required keys present (auth=psk, tailscale=on)
fleet public key valid
```

出现「拒绝写入：这份 Tailscale 授权来自仓库内的开发配置」= 你拿到了**开发者的**包，停下来找开发侧要正式包。

---

## 2. 写基础镜像（每张一次）

用 Raspberry Pi Imager：

| 项 | 填什么 |
|---|---|
| 系统 | Raspberry Pi OS（64-bit）Lite 或 Desktop |
| 主机名 | 随便（做卡时会改成 `eora-air-NN`） |
| 用户名 | **`eora`**（必须） |
| 密码 | 先填一个临时密码（做卡后会改成 `SSH_PASSWORD`） |
| 启用 SSH | ✅ **必须勾选** |
| 认证方式 | 选"使用密码登录"（你没有私钥） |

一次做完 15 张，再统一做下一步（流水线更快）。

---

## 3. 批量做卡（15 张，约 10 分钟）

```powershell
python gateway_probe\mkcard.py --batch --from 6 --count 15 --env site.env
```

流程：

```
== waiting for card #6 ...           ← 插第一张，等它识别
已准备节点 6；实例号已同步。
== #6 done. 拔卡，换下一张。          ← 拔掉，插下一张
== waiting for card #7 ...           ← 自动继续，不用重跑命令
...
== batch finished: 15 card(s) prepared
```

### 检查点

- 每张都出现 `已准备节点 N；实例号已同步。`
- 出现 `no card appeared within 15 minutes` = 卡没插好或没识别
- 出现 `目标目录非空`/`找到多张卡` = 只留一张卡在读卡器里

**编号必须是 6–20**（1–5 是开发侧的调试卡，重号会让前端互相覆盖）。

---

## 4. 上电与首启（15 块一起，等 2–5 分钟）

把卡插到对应的树莓派，上电。

### 检查点

把卡拔回来插到电脑，读 `/boot/firmware/eora-status.txt`：

```
6/6 DONE host=eora-air-06 overlay=100.x.x.x ip=192.168.x.x
```

| 看到 | 含义 | 处理 |
|---|---|---|
| `6/6 DONE` | ✅ 成功 | 继续 |
| `FAILED: wifi connection` | WiFi 名或密码错 | 改 `site.env`，重做该卡 |
| `FAILED: 802.1X needs EORA_IDENTITY` | `WIFI_AUTH=eap` 但没填 `WIFI_IDENTITY` | 补齐后重做 |
| 卡在 `4a/6 clock` 后超时 | 树莓派没拿到网络 | 检查 WiFi / 信号 |
| `FAILED: tailscale installation` | 时钟没同步或网络不通 | 先确认 WiFi 通，再重做 |

**不要跳过这一步**：首启没成功，后面 `fleet status` 会看不到设备。

---

## 5. 确认设备都在线

```powershell
$env:EORA_SSH_PASSWORD = '现场统一口令'
$env:EORA_PASS         = '现场统一口令'

python fleet\fleet.py status
```

第一行必须是：

```
transport: tailnet (remote flashing works across networks)
```

### 检查点

- 15 行设备，`rdr` 列是 `active`
- 如果显示 `transport: local network ...` → Tailscale 没连上，远程刷板做不了
- 如果 `Tailscale is not connected ... NoState` → 管理员执行 `Restart-Service Tailscale`

---

## 6. 批量刷板

```powershell
python fleet\fleet.py update BUILD-xxx\images\mid_edge.bin --group 2
```

> `--group 2` 依赖 `config\fleet.groups.json`（名字 → 组号）。
> 没有这个文件就改用 `--only`：

```powershell
python fleet\fleet.py update BUILD-xxx\images\mid_edge.bin --only eora-air-06 eora-air-07 eora-air-08 eora-air-09 eora-air-10
```

或者双击 `FLASH_NODES.cmd`（会自动找最新镜像并转调 `fleet.py update`）。

### 检查点

每台输出应包含 `VERIFIED`，且 build_id 一致。逐台确认：

```powershell
python fleet\fleet.py status
```

`node / build / mode` 列的 build 应该是同一个值。

**出现 `push node_update.py failed`** → 该台密码登录没开或密码错。
先单独试：

```powershell
ssh eora@eora-air-06
```

---

## 7. 分组与信道（可选，开发侧也能做）

```powershell
python fleet\fleet.py group --group 2 --channel 6 --only eora-air-06 ... eora-air-20
```

**必须核对返回里的 `group_reported == 2`**，只看 `ok` 不够。

---

## 8. 完成判定

| 项 | 标准 |
|---|---|
| 15 张卡 | `eora-status.txt` 全是 `6/6 DONE` |
| 15 台在线 | `fleet status` 显示 15 行 |
| 固件一致 | 所有 build 相同 |
| 分组 | `group_reported` 全部为 2 |
| 上报 | 网关能收到编号 6–20 的 LRN1 帧 |

---

## 9. 出问题时的最短排查

| 现象 | 先做 |
|---|---|
| `fleet status` 看不到设备 | 卡的首启日志（`eora-status.txt`） |
| 能 ping 通但 `ssh` 超时 | 大概率不在同一 tailnet |
| `ssh` 提示 `Permission denied (publickey)` | 卡里没开密码登录 → 找开发侧执行 `enable_ssh_password.py` |
| 刷板卡住 | `fleet.py logs <设备名>` 看 Pi 侧事件 |
| 全部超时 | 先看 `transport:` 那行，再 `Restart-Service Tailscale` |
