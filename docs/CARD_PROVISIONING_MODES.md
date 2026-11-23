# 做卡的生产化配置：WiFi 与 Tailscale 都不再写死

回答两个问题：
1. 生产环境的电脑不可能登录个人 Tailscale 账号 → 怎么办
2. 生产环境不是校园网 → WiFi 能不能用 `.env` 配

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
