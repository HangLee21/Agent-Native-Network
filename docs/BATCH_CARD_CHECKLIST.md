# 批量做卡：需要准备什么（远程 15 张）

## 一、先回答"要不要 API key"

**只有一个密钥类的东西：Tailscale auth key。** 没有别的云服务、没有 API token。

| 项 | 是什么 | 谁生成 |
|---|---|---|
| **Tailscale auth key** | 类似 API key，一次性授权凭证 | **运维自己在自己的 tailnet 后台生成** |
| WiFi SSID / 密码 | 普通账号密码 | 现场提供 |
| 802.1X 账号（可选） | 校园网那种身份 | 现场提供 |
| SSH 密钥对 | 不是 API key，是登录凭证 | 刷板机自己生成（已有可复用） |

> 如果现场不需要跨网络管理，`TAILSCALE_AUTHKEY` 可以留空，**连这个 key 都不用**。

---

## 二、一次性准备（在刷板机上做一次）

### 1. 软件

| 需要 | 说明 |
|---|---|
| Python 3 | 跑 `mkcard.py` |
| `PyYAML` | 改 cloud-init 配置用，缺了会直接报"需要 PyYAML" |
| `ssh` / `scp` | 远程刷板用（Windows 10+ 自带） |
| Raspberry Pi Imager | 先把基础镜像写到每张卡 |

### 2. SSH 密钥对

```
~/.ssh/id_ed25519_eora        私钥（留在刷板机，用于 SSH 到各台 Pi）
~/.ssh/id_ed25519_eora.pub    公钥（会被写进每一张卡）
```

**做卡只需要公钥**；`fleet.py` 刷板时用私钥。没有就用：

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519_eora -N '""'
```

### 3. 现场配置文件（`--env` 指向它，**不要**用仓库里的）

```ini
# D:\ops\site-remote.env

# --- WiFi ---
WIFI_SSID=SiteRemoteWiFi
WIFI_AUTH=psk              # psk = 普通密码；eap = 802.1X（需 WIFI_IDENTITY）
WIFI_PASSWORD=********

# --- 管理平面（远程刷板必需）---
# 运维自己的 tailnet 生成的一次性 key；每张卡建议一个
TAILSCALE_AUTHKEY=tskey-auth-XXXXXXXX-YYYYYYYY
```

如果现场是 802.1X：

```ini
WIFI_AUTH=eap
WIFI_IDENTITY=hli21
WIFI_PASSWORD=********
```

### 4. Tailscale auth key 怎么拿（关键）

1. 用**运维自己的账号**登录 Tailscale 管理后台
2. Settings → Keys → Generate auth key
3. **勾选一次性（non-reusable）**、建议设 24 小时过期
4. 15 张卡 → 生成 15 个（或一个 reusable 但在部署完成后立即吊销）

> **绝对不要用开发者的 key。** 做卡工具会硬拦截：
> 仓库内 `.local` 的 key 会被拒绝，除非显式 `--i-know-this-is-the-dev-key`。

---

## 三、每张卡需要的东西

| 项 | 说明 |
|---|---|
| 一张用 Imager 写好的基础卡 | 用户 `eora`、SSH 打开、公钥 |
| **节点编号** | 唯一，1..255。本地 5 块占 1–5，**远程 15 块用 6–20** |
| 插拔 | 一张一张写，写完换下一张 |

**编号与卡的对应关系只写在卡上**，不需要维护中央名单——
开机后编号随 LRN1 帧上传，前端从空口解出。

---

## 四、批量做卡命令

### 一张一张自动编号（推荐）

```powershell
python tools\mid_baseline\gateway_probe\mkcard.py --batch --from 6 --count 15 --env D:\ops\site-remote.env
```

流程：

```
== waiting for card #6 ...          ← 插第一张
   写入完成（暂存 → 校验 → 备份 → 原子替换）
== #6 done. 拔卡，换下一张。
== waiting for card #7 ...          ← 拔掉旧的，插新的，自动继续
...
== batch finished: 15 card(s) prepared
```

- **自动识别"未准备过的卡"**（有 `cmdline.txt` 但还没有 `eora-firstboot.sh`）
- 拔卡后自动等下一张，不需要重跑命令
- 每张卡都会在卡内留一个 `eora-backup-*` 目录（原始配置副本）

### 或者仍用一键入口（单张，手动输编号）

```powershell
MK_CARD.cmd          # 回车自动找卡，然后输入编号
```

---

## 五、做卡前后检查清单

### 做卡前

| 检查 | 命令 |
|---|---|
| 配置文件齐全 | `mkcard.py --check --env D:\ops\site-remote.env` |
| 公钥有效 | 同上（会校验 ed25519 格式） |
| 不是开发者的 key | 同上（在仓库内用会拒绝） |

### 每张卡做完

| 检查 | 期望 |
|---|---|
| `meta-data` 的 `instance-id` | 形如 `eora-air-07-<uuid>` |
| `cmdline.txt` 的 `i=` | 与上面**同一个** uuid（这个最容易错） |
| `network-config` | `psk` 时是 `password:`，`eap` 时是 `auth:` |
| `eora-firstboot.sh` | 约 46 KB |
| 卡上有 `eora-backup-*` | 有 |

### 插电后（2–5 分钟）

卡上 `/boot/firmware/eora-status.txt` 应该是：

```
6/6 DONE host=eora-air-07 overlay=<tailnet IP> ip=<局域网 IP>
```

失败会写 `FAILED: <哪一步>`，把卡拔回来重跑 `MK_CARD.cmd` 会先打印上次失败原因。

---

## 六、做完之后还要两步

### 1. 设成 group 2（隔离远程那张网）

```powershell
fleet.py group --group 2 --channel 6 --only eora-air-06 ... eora-air-20
```

返回里核对 `group_reported == 2`，不能只看 `ok`。

### 2. 建议远程组换 LoRa 频率

本地 5 块在 470.5 MHz，远程 15 块建议 470.7 MHz，避免 20 块挤一个频点
（此前实测：单频点会出现连续 2–6 帧丢失）。

---

## 七、15 张卡的实际工作量估计

| 步骤 | 单张耗时 | 15 张 |
|---|---|---|
| Imager 写基础镜像 | 3–5 分钟 | 45–75 分钟（可流水线） |
| `--batch` 写入身份 | 5–10 秒 | 约 3 分钟 + 换卡时间 |
| 上电首启 | 2–5 分钟（并行） | 可同时上电 |
| 设 group / 频率 | 每台 20–30 秒 | 约 8 分钟 |

**建议流水线**：先一次性用 Imager 把 15 张都写好 →
再逐张跑 `--batch` 写身份 → 最后一起上电。

---

## 八、当前状态

| 项 | 状态 |
|---|---|
| `--batch` 自动编号 + 等卡换卡 | ✅ 已实现（复用单卡写卡逻辑，含备份与原子替换） |
| `--env` 现场配置 | ✅ 已实现 |
| 开发者 key 硬拦截 | ✅ 已实现 |
| Wi-Fi 两种认证 | ✅ 已实现 |
| **15 张卡实做** | ❌ 未做（等现场 WiFi 与运维 tailnet key） |
