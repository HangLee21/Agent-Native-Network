# 做卡侧到底写入了哪些信息

依据：对一张实际生成的卡（`eora-air-12`，PSK + 密码登录 + 双公钥）逐项提取。

---

## 一、卡（boot 分区）上写完后的 5 个文件 + 1 个备份目录

| 文件 | 大小 | 内容 |
|---|---:|---|
| `eora-firstboot.sh` | 47 KB | 安装器：身份 + 公钥 + 4 个 helper + 逻辑脚本（全部 base64 内嵌） |
| `user-data` | 0.2 KB | `hostname`、`ssh_pwauth`、`runcmd: bash /boot/firmware/eora-firstboot.sh` |
| `meta-data` | 0.1 KB | `instance-id: eora-air-12-<uuid>`、`local-hostname` |
| `cmdline.txt` | 0.1 KB | `ds=nocloud;i=<同一个 uuid>`（**必须与 meta-data 一致**） |
| `network-config` | — | WiFi 条目（psk 或 eap）+ eth0 DHCP |
| `eora-backup-<uuid>/` | — | 上述文件的**原始副本**，失败可回滚 |

> 没有 `fat.conf`、没有额外脚本、没有固件。

---

## 二、安装器携带的 9 项身份信息（`/etc/eora/identity.env`）

| 键 | 示例值 | 敏感 |
|---|---|:--:|
| `EORA_HOST` | `eora-air-12` | |
| `EORA_NUMBER` | `12` | |
| `EORA_SSID` | `FactoryWiFi` | |
| `EORA_WIFI_AUTH` | `psk` / `eap` | |
| `EORA_IDENTITY` | 802.1X 账号（psk 时为空） | |
| `EORA_WIFI_PASS` | WiFi 密码 | 🔴 |
| `EORA_AUTHKEY` | Tailscale auth key（可空） | 🔴 |
| `EORA_SSH_PASS` | eora 的 SSH 密码（可空） | 🔴 |
| `EORA_SSH_ALLOW_PASS` | `yes` 时只开开关不改密码 | |

---

## 三、安装器内嵌的 6 个载荷（base64）

| 目标路径 | 大小 | 作用 |
|---|---:|---|
| `/usr/local/lib/eora/install_fleet_key.py` | 1,500 B | 把公钥写进 `eora` 的 authorized_keys |
| `/usr/local/lib/eora/node_reader.py` | 8,255 B | Pi 侧串口常驻服务 |
| `/usr/local/lib/eora/node_update.py` | 7,083 B | Pi 侧烧写器（远程刷板用） |
| `/usr/local/lib/eora/pi_node_probe.py` | 6,291 B | 串口探针库 |
| `/usr/local/lib/eora/eora-node-reader.service` | 529 B | systemd 单元 |
| `/usr/local/sbin/eora-firstboot-logic.sh` | 17,495 字符 | 实际的安装逻辑 |

另有 `/etc/eora/fleet.pub`：**管理公钥，可多行**（本例 2 把）。

---

## 四、首启后 Pi 上最终落盘的东西

### 4.1 身份与密钥

| 路径 | 内容 | 权限 |
|---|---|---|
| `/etc/eora/identity.env` | 上面 9 项 | 0600 |
| `/etc/eora/fleet.pub` | 全部管理公钥 | — |
| `/home/eora/.ssh/authorized_keys` | 同样这些公钥 | 0600 |
| `/etc/ssh/sshd_config.d/20-eora-password.conf` | `PasswordAuthentication yes`（仅在设密码/允许密码时） | — |

### 4.2 程序与服务

| 路径 | 说明 |
|---|---|
| `/usr/local/lib/eora/` | 4 个 helper + service 单元 |
| `/usr/local/sbin/eora-firstboot-logic.sh` | 安装逻辑本体 |
| `/etc/systemd/system/node_reader.service` | **已 enable + start** |
| `/etc/systemd/system/eora-firstboot.service` | 成功后**自我禁用**（不再重跑） |
| `/home/eora/eora/` | `node_reader.py`、`node_update.py`、`pi_node_probe.py`、`logs/` |

### 4.3 网络与系统设置

| 项 | 说明 |
|---|---|
| NetworkManager 连接 `wifi-<SSID>` | psk 用 `wpa-psk`，eap 用 `wpa-eap`+peap+mschapv2 |
| `hostname` | 改成 `eora-air-NN` |
| `/etc/hosts` | 同步主机名 |
| `eora` 加入 `dialout` 组 | 串口权限 |
| `/etc/gai.conf` | `precedence ::ffff:0:0/96 100`（优先 IPv4） |
| `python3-pip` + `pyserial==3.5` + `esptool==5.6.0` | 远程刷板依赖 |
| Tailscale | **仅在 `EORA_AUTHKEY` 非空时安装并 `tailscale up`** |

### 4.4 日志（都在卡上，方便拔卡排查）

| 文件 | 内容 |
|---|---|
| `/boot/firmware/eora-install.log` | 安装器自身输出 |
| `/boot/firmware/eora-firstboot.log` | 首启逻辑输出 |
| `/boot/firmware/eora-status.txt` | **一行结论**，成功 `6/6 DONE ...`，失败 `FAILED: <哪一步>` |

---

## 五、9 个进度点（失败时能定位到具体一步）

```
1/6  firstboot starting
2/6  hostname 设置
2b/6 eora 密码设置
2c/6 SSH 密码登录开启
3/6  WiFi 配置
4/6  网络起来（拿到 wlan0 地址）
4a/6 时钟同步（树莓派无 RTC，等 NTP）
5/6  Tailscale（或 skipped）
6/6  DONE / INCOMPLETE
```

---

## 六、卡上**没有**的东西

| 没有 | 原因 |
|---|---|
| 固件镜像 | 由开发侧远程刷写 |
| 任何**私钥** | 只装公钥；私钥永不离开操作员机器 |
| 代码仓库 / 构建脚本 | 生产不需要 |
| 前端 / 接收器 / fleet 工具 | 只在开发侧运行 |

---

## 七、敏感信息与暴露面（安全评估）

| 信息 | 明文位置 | 卡被捡到的后果 |
|---|---|---|
| **WiFi 密码** | `network-config`（netplan 明文）+ `identity.env` | 可接入该 WiFi |
| **Tailscale auth key** | `identity.env` | 设备可加入 tailnet；一次性 + 24 h 过期可缓解 |
| **SSH 密码** | `identity.env` | 可登录 eora |
| 管理公钥 | `fleet.pub` | 不敏感 |

**结论：卡本身就是凭据载体，必须按"密钥介质"管理**（随卡登记、丢失即吊销）。

三项可降低风险：

1. 用**一次性** Tailscale key（non-reusable、24 h）
2. 首启成功后**删除 `/etc/eora/identity.env`**（目前未做）
3. 能只用公钥时**不要设 `SSH_PASSWORD`**

---

## 八、一处设计说明

`identity.env` 里存的是**明文**，权限 0600、属主 root。
之所以不用加密：首启时没有任何可用的外部密钥来源来解密，
强行加密只是把密钥换个地方放。真正的缓解是**用完即删**（见第七节第 2 条）。
