# 做卡的生产化配置：WiFi 与 Tailscale 都不再写死

回答两个问题：
1. 生产环境的电脑不可能登录个人 Tailscale 账号 → 怎么办
2. 生产环境不是校园网 → WiFi 能不能用 `.env` 配

---

## 零、设计约束（这三条是硬要求）

### ① 只有"刷板机"需要 Tailscale

```
刷板机（运维的笔记本）   ← 装 Tailscale，加入【运维自己的】tailnet
        │  SSH over tailnet
        ├── eora-air-01 … 05   ← 卡片里带【运维自己生成的】auth key
        │
LoRa 网关（E870-L）      ← 不装、不加入、不需要 Tailscale
        │  以太网 UDP
        └── 刷板机（接收 + 显示）
```

**跨网络远程刷板 = 刷板机在 tailnet 里 + 卡片在同一个 tailnet 里。**
两者只要在同一个 tailnet，物理位置无关。

**LoRa 网关从来不需要 Tailscale**：它只有一根网线，向指定 IP:端口发 UDP。
代码里也已确认：`topology_server.py` / `start_frontend.py` / `node_reader.py` /
`node_update.py` / `pi_node_probe.py` **零处引用 Tailscale**。

### ② 生产卡绝不能带出开发者的账号

代码里已加**硬拦截**（`mkcard.py`）：

```
拒绝写入：这份 Tailscale 授权来自仓库内的开发配置，会泄露开发者个人账号。
  正确的做法：  --env D:\ops\site.env   （里面放现场自己的 TAILSCALE_AUTHKEY）
  仅当这是自用的调试卡时，才加 --i-know-this-is-the-dev-key
```

判定规则：`device.env` 位于**本仓库 `.local/` 内**且含 `TAILSCALE_AUTHKEY` → 拒绝，
除非显式加 `--i-know-this-is-the-dev-key`。

> 所以：**生产环境必须用 `--env` 指向现场文件**，开发者的 key 一步也带不出去。

### ③ 打包时不得包含 `.local/`

`.local/` 里有开发者的 WiFi 口令与 Tailscale key（已被 gitignore）。
推到 deploy 的打包脚本必须显式排除它——详见 `docs/PORT_TO_DEPLOY_PLAN.md` 风险 5。

---

## 一、配置文件：`device.env`

默认路径 `.local/mid/pi/device.env`（不进版本库）。
生产环境用 `--env` 指向自己的文件：

```powershell
python tools\mid_baseline\gateway_probe\mkcard.py --card F: --number 7 --env D:\ops\site-a.env
```

### 完整键表

| 键 | 必填 | 说明 |
|---|---|---|
| `WIFI_SSID` | ✅ | 现场 WiFi 名称 |
| `WIFI_AUTH` | 可选 | `eap`（默认，企业 802.1X）或 `psk`（普通密码 WiFi） |
| `WIFI_PASSWORD` | ✅ | WiFi 密码 |
| `WIFI_IDENTITY` | `eap` 必填 | 802.1X 账号（如校园网学号）；`psk` 时留空 |
| `TAILSCALE_AUTHKEY` | **可选** | 留空则**不装 Tailscale**，走局域网 |

> 没有 `TAILSCALE_AUTHKEY` 时，做卡会打印：
> `NOTE: 没有 TAILSCALE_AUTHKEY —— 卡片将不装 Tailscale（走局域网/mDNS）`

---

## 二、两种 WiFi 写法

### A. 企业 802.1X（校园网、单位内网）

```ini
WIFI_SSID=Tsinghua-Secure
WIFI_AUTH=eap
WIFI_IDENTITY=hli21
WIFI_PASSWORD=********
```

卡片里生成：

```yaml
access-points:
  Tsinghua-Secure:
    auth:
      key-management: eap
      method: peap
      identity: hli21
      password: ********
      phase2-auth: mschapv2
```

### B. 普通密码 WiFi（办公室路由器、手机热点）

```ini
WIFI_SSID=OfficeWiFi
WIFI_AUTH=psk
WIFI_PASSWORD=office-pass-123
```

卡片里生成：

```yaml
access-points:
  OfficeWiFi:
    password: office-pass-123
```

**为什么必须区分**：Imager 只会写"密码型"。喂给 802.1X 网络时它永远认证不上；
反过来把 802.1X 的 auth 块喂给普通路由器，也连不上。**两种必须显式声明。**

---

## 三、Tailscale：三种部署模式

### 模式 1：生产用自己的 tailnet（推荐）

运维在自己的 Tailscale 管理后台生成 auth key，写进他们的 `device.env`：

```ini
TAILSCALE_AUTHKEY=tskey-auth-<运维自己账号生成的>
```

- **不需要登录任何人的个人账号** —— key 就是授权凭证
- 建议用 **一次性 key**（reusable 关掉），一台一个，泄露影响面最小
- 卡片加入的是**运维的 tailnet**，不是开发者的

### 模式 2：完全不用 VPN（纯局域网）

```ini
TAILSCALE_AUTHKEY=
```

卡片**不装 Tailscale**，首启日志会写：

```
5/6 tailscale: skipped (no EORA_AUTHKEY; management over the local network)
6/6 DONE host=eora-air-07 overlay=none ip=192.168.1.27
```

然后运维用**静态主机表**让机群工具找到设备：

```
config/fleet.hosts.json        ← 复制 config/fleet.hosts.example.json 改
{
  "nodes": [
    {"name": "eora-air-01", "address": "192.168.1.21"},
    {"name": "eora-air-02", "address": "192.168.1.22"}
  ]
}
```

`fleet.py` 的发现顺序：**Tailscale 能用就用，不能用就读这个表**（两者可取并集）。

### 模式 3：现在这套（开发/实验）

```ini
TAILSCALE_AUTHKEY=tskey-auth-<开发者的>
WIFI_SSID=Tsinghua-Secure
WIFI_AUTH=eap
```

---

## 四、实施状态

| 项 | 状态 |
|---|---|
| `WIFI_AUTH` 支持 eap / psk | ✅ 已实现（安装器 + network-config 两处） |
| `TAILSCALE_AUTHKEY` 可留空 | ✅ 已实现（跳过安装、完成判定不再要求它） |
| 做卡时打印实际模式 | ✅ `required keys present (auth=psk, tailscale=off)` |
| `--env` 指定配置文件 | ✅ 已实现 |
| `config/fleet.hosts.json` 静态主机表 | ✅ 已实现（示例文件已放） |

**验证方式**：用假卡目录 + PSK 配置跑过一遍，确认

- `network-config` 生成 `password:` 而不是 `auth:` 块
- 安装器内嵌逻辑含 `wpa-psk` 分支
- 含 `5/6 tailscale: skipped` 分支
- 完成判定为 `overlay_ok`，不再强制要求 tailnet

---

## 五、两个安全提醒（生产必读）

1. **卡片 boot 分区上有明文口令**
   `cmdline`/`user-data`/`identity.env` 里都能读到 WiFi 密码与 auth key。
   建议：首启成功后把 `identity.env` 删掉，并用**一次性** tailscale key。

2. **密钥不进版本库**
   `.local/` 已在 `.gitignore` 里。生产环境请把 `site-a.env` 放在受控位置，
   不要提交，也不要用 `git add -A`。

---

## 六、批量做卡流程（生产）

```
1. Imager 写一张基础卡（用户 eora、SSH 打开、公钥）
2. 插到电脑，运行：
     MK_CARD.cmd                      ← 回车自动找卡，输入编号
   或
     mkcard.py --auto --number N --env D:\ops\site-a.env
3. 拔卡插到对应 Pi，上电
4. 首启日志（卡上 /boot/firmware/eora-status.txt）会写：
     6/6 DONE host=eora-air-0N overlay=<tailnet IP 或 none> ip=<局域网 IP>
5. 机群总览：
     FLEET_STATUS.cmd                 ← Tailscale 或静态主机表都能列出来
```

编号与卡的对应关系只存在于**卡上**，不需要维护中央名单；
开机后编号随 LRN1 帧上传，前端从空口解出。

---

## 七、远程刷板的前提（跨网络）

| 前提 | 说明 |
|---|---|
| 刷板机装 Tailscale 并登录**运维的**账号 | 只有这一台机器需要 |
| 卡片的 TAILSCALE_AUTHKEY 来自**同一个** tailnet | 用 --env 指向现场文件 |
| 刷板机能 SSH 到 eora-air-* | leet.py status 的 	ransport: 行会显示 	ailnet |
| 网关不需要任何改动 | 它只走以太网 UDP |

leet.py status 会先打印一行当前传输方式：

`
transport: tailnet (remote flashing works across networks)
transport: local network via config/fleet.hosts.json (no remote flashing)
`

**第二种情况不能远程刷板**——纯局域网模式能看数据、能本地 SSH，
但人在外地时够不到设备。跨网络刷板必须走 tailnet。

**每张卡一个一次性 key**（Tailscale 后台把 auth key 设为 non-reusable）：
卡片丢失或回收时只吊销那一个 key，不会影响其它节点。

---

## 八、两台刷板机怎么办

### 结论：**必须同一个 tailnet，但不必共用同一个账号**

只有"在同一个 tailnet 里"才能互相看见、也才能看见卡片。
同一个 tailnet **不等于**同一个账号——三种做法：

| 做法 | 账号 | 适用 | 代价 |
|---|---|---|---|
| **A. 组织 tailnet + 各自账号**（推荐） | 两人各用自己的身份 | 团队 / 生产 | 需要建组织（免费档也支持） |
| B. 同一账号在两台登录 | 共用 | 临时 / 单人两机 | 凭证共享、审计弱 |
| C. 节点共享 node sharing | 各自 tailnet | 跨组织临时协作 | ACL 复杂，不推荐做主方案 |

**推荐 A**：在 Tailscale 里建一个组织（org），把两个操作员都邀请进去；
各自用**自己的账号**登录，设备与卡片都在这个组织的 tailnet 里。
这样既满足"同一 tailnet"，又不需要任何人交出账号密码。

> 开发者本人的个人 tailnet **不能**用于生产——做卡工具已经硬拦截。

### 每台刷板机各自需要准备（不能共享的部分）

| 项 | 为什么 |
|---|---|
| **同一把 SSH 私钥** `~/.ssh/id_ed25519_eora` | 卡片里装的是那把**公钥**；换一把私钥就连不上 |
| `EORA_PASS` 环境变量或 `.local/mid/pi/sudo_pass.txt` | 刷板要在 Pi 上停/起 node_reader |
| Python + ssh/scp | 基础工具 |

`known_hosts` 是每台机器各自临时生成的，不需要同步。

### 两台同时操作时的纪律

代码里**没有跨机互斥**（没有分布式锁）。因此：

| 规则 | 说明 |
|---|---|
| **同一台设备不要被两台同时刷** | 会互相打断，结果不可预期 |
| 用 `--only` 明确分工 | 例：A 机刷 06–12，B 机刷 13–20 |
| **编号必须事先分配** | 编号写在卡上，没有中央登记；两台各自做卡前先约定号段 |
| 不要同时改同一台的 group | 两次 `discover_config` 会互相覆盖 |

示例分工：

```powershell
# 刷板机 A
fleet.py update BUILD-xxx/images/mid_edge.bin --only eora-air-06 eora-air-07 eora-air-08 eora-air-09 eora-air-10 eora-air-11 eora-air-12

# 刷板机 B
fleet.py update BUILD-xxx/images/mid_edge.bin --only eora-air-13 eora-air-14 eora-air-15 eora-air-16 eora-air-17 eora-air-18 eora-air-19 eora-air-20
```

---

## 九、SSH：多把公钥 + 可选密码登录

### 9.1 `fleet.pub` 支持多行

一行一把公钥，做卡时全部装进 `authorized_keys`：

```
ssh-ed25519 AAAAC3...  you@dev
ssh-ed25519 AAAAC3...  ops@site
```

### 9.2 开启密码登录

```ini
SSH_PASSWORD=现场统一口令        # 设置密码并开启密码登录
# 或
SSH_ALLOW_PASSWORD=yes          # 只开启登录开关，不改密码
```

卡片首启会写 `sshd_config.d/20-eora-password.conf` 并 reload ssh，
同时把 cloud-init 的 `ssh_pwauth` 强制为 `true`（覆盖 Imager 的"仅公钥"）。

### 9.3 公钥文件的查找顺序

```
--public-key 指定的路径
  → 工具同目录 fleet.pub
  → 上一级目录 fleet.pub（生产包布局）
  → ~/.ssh/id_ed25519_eora.pub
```

报错时会**打印实际使用的路径**，不会再指向错误的文件。
