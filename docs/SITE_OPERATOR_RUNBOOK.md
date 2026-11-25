# 现场运维操作单（双击就行）

对象：**没有私钥、用账号密码登录**的现场同事。
目标：把 15 张卡做好，并把固件刷进 15 块板。

**你只需要双击 4 个文件，不用敲命令。**

---

## 准备（一次性）

| # | 条件 | 谁提供 |
|---|---|---|
| 1 | Tailscale 已装、登录**组织 tailnet** | 自己 |
| 2 | 做卡包（含 `fleet/`） | 开发侧 |
| 3 | `fleet.pub`（在包根目录） | 开发侧 |
| 4 | 固件镜像 `BUILD-*/images/mid_edge.bin` | **开发侧** |
| 5 | Python 3 + PyYAML、Raspberry Pi Imager | 自己 |

> 包里没有固件。刷板前把镜像目录拷进包里。

---

## 第 1 步：双击 `SETUP_SITE.cmd`

它会问几个问题（直接回车用方括号默认值）：

```
WiFi 名称:                     ← 现场 WiFi
认证方式 1=普通密码(psk) 2=企业802.1X(eap) [1]:
WiFi 密码:
Tailscale auth key:            ← 你组织后台生成的一次性 key
eora 的登录密码（至少 8 位）:   ← 你以后 ssh 用的密码
```

生成 `site.env`，并自动做一次自检。**看到下面两行就对了**：

```
required keys present (auth=psk, tailscale=on)
fleet public key valid
```

> 出现「拒绝写入：来自仓库内的开发配置」= 包不对，找开发侧要正式包。

---

## 第 2 步：用 Imager 把 15 张卡都写好

| 项 | 填什么 |
|---|---|
| 用户名 | **必须 `eora`** |
| 启用 SSH | ✅ **必须勾** |
| 认证方式 | **使用密码登录**（你没有私钥） |

一次写完 15 张，再做第 3 步更快。

---

## 第 3 步：双击 `MK_CARDS.cmd`

```
起始编号 [6]:        ← 直接回车 = 6
数量 [15]:           ← 直接回车 = 15
```

然后**一张一张插卡**，它会自动编号：

```
== waiting for card #6 ...
已准备节点 6；实例号已同步。
== #6 done. 拔卡，换下一张。
== waiting for card #7 ...
...
== batch finished: 15 card(s) prepared
```

**编号必须是 6–20**（1–5 是开发侧的调试卡，重号会让前端互相覆盖）。

单张也可以：`MK_CARDS.cmd 6 1`

---

## 第 4 步：卡片插到树莓派上电，等 2–5 分钟

把卡拔回来插电脑，读 `/boot/firmware/eora-status.txt`：

```
6/6 DONE host=eora-air-06 overlay=100.x.x.x ip=192.168.x.x
```

| 看到 | 处理 |
|---|---|
| `6/6 DONE` | ✅ 继续 |
| `FAILED: wifi connection` | WiFi 名/密码错 → 改 `site.env` 重跑 `SETUP_SITE.cmd`，重做该卡 |
| `FAILED: 802.1X needs EORA_IDENTITY` | 选 2 却没填账号 → 重跑 `SETUP_SITE.cmd` |
| 卡在 `4a/6 clock` 很久 | 网络不通，查 WiFi |
| `FAILED: tailscale installation` | 时钟未同步，先确认 WiFi 通 |

---

## 第 5 步：双击 `SITE_STATUS.cmd`

```
transport: tailnet (remote flashing works across networks)
device         rdr     node / build / mode      wifi     cable
eora-air-06    active  8 / abcdef / discover    ...
```

### 检查点

- **第一行必须是 `transport: tailnet`**
  - 显示 `local network` → 只能局域网操作，远程刷板做不了
  - 显示 `NoState` → 管理员执行 `Restart-Service Tailscale`
- 15 行设备，`rdr` 是 `active`

---

## 第 6 步：双击 `SITE_FLASH.cmd`

```
1 = 本地组 (group 1)
2 = 远程组 (group 2)
3 = 全部
4 = 只刷一台
选择 [3]: 2
```

它会自动找最新的 `BUILD-*/images/mid_edge.bin` 并逐台刷。

### 检查点

- 每台出现 `VERIFIED`
- 再跑一次 `SITE_STATUS.cmd`，build 列**全部相同**

**出现 `push node_update.py failed`** → 该台密码登录没开或密码错，先单独试：

```
ssh eora@eora-air-06
```

---

## 第 7 步（可选）：双击 `SITE_GROUP.cmd`

```
组号 (1 或 2): 2
WiFi 信道 (1-13): 6
```

**核对输出里的 `group_reported` 等于组号**，只看 `ok` 不够。

想只设某几台，在命令行带设备名：

```
SITE_GROUP.cmd 2 6 eora-air-06 eora-air-07
```

---

## 完成判定

| 项 | 标准 |
|---|---|
| 15 张卡 | `eora-status.txt` 全是 `6/6 DONE` |
| 15 台在线 | `SITE_STATUS.cmd` 显示 15 行 |
| 固件一致 | build 列全相同 |
| 分组 | `group_reported` 全为该组号 |
| 上报 | 网关收到编号 6–20 的 LRN1 帧 |

---

## 出问题看这里

| 现象 | 先做 |
|---|---|
| `SITE_STATUS.cmd` 一闪就退 | 用 `cmd /k` 打开看报错；大概率没装 PyYAML 或站点配置缺失 |
| 看不到设备 | 看卡上 `eora-status.txt` |
| 能 ping 通但 `ssh` 超时 | 不在同一 tailnet |
| `ssh` 提示 `Permission denied (publickey)` | 卡里没开密码登录 → 让开发侧跑 `enable_ssh_password.py` |
| 全部超时 | 先看 `transport:` 那行，再 `Restart-Service Tailscale` |
| 刷板卡住 | 开发侧 `fleet.py logs eora-air-XX` |

---

## 附：命令行等价操作（排障用）

| 双击 | 等价命令 |
|---|---|
| `SETUP_SITE.cmd` | `python fleet\write_site_env.py site.env` |
| `MK_CARDS.cmd` | `python gateway_probe\mkcard.py --batch --from 6 --count 15` |
| `SITE_STATUS.cmd` | `python fleet\fleet.py status` |
| `SITE_FLASH.cmd 2` | `python fleet\flash_nodes.py --group 2` |
| `SITE_GROUP.cmd 2 6` | `python fleet\fleet.py group --group 2 --channel 6` |

密码从 `site.env` 自动读，**不需要手工 set 环境变量**。
