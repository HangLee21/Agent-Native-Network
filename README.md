# EoRa 现场交付包

**打包分支 `codex/production-deployment`，发布标识 `v0.2.0-20261123`。**

开发分支（`codex/baseline-reproduction-20261023`）的前端、后端、做卡与机群工具已并入本分支，
运行方式仍适配原来的打包形态（`runtime\python` + `app\start\launcher.py`）。

---

## 一、五个入口，按你要做的事选一个

| 我要做什么 | 双击 | 说明 |
|---|---|---|
| **看实时拓扑 / 收数据** | `START_STUDIO.cmd` | 打包启动器（`runtime\python` + `app\start\launcher.py`） |
| **给新卡写入身份** | `SETUP_SITE.cmd` → `MK_CARDS.cmd` | 先配置一次，再批量做卡 |
| **跨网络刷固件** | `SITE_STATUS.cmd` → `FLASH_REMOTE.cmd` | 走 Tailscale，可跨网络 |
| **本机 USB 直连刷写** | `FLASH_NODES.cmd` | 串口直连，交付包自带的刷写台 |
| **部署一台新网关** | `SETUP_GATEWAY.cmd` | 网关安装向导 |

> **两个刷写入口不要混用**：`FLASH_NODES.cmd` = 本机 USB；`FLASH_REMOTE.cmd` = 跨网络机群。
> `SITE_FLASH.cmd` 是 `FLASH_REMOTE.cmd` 的菜单版（选组/选设备），实现是同一个。

**不确定某个脚本会走哪条路？加 `--which` 只查询不执行：**

```powershell
START_STUDIO.cmd --which
FLASH_NODES.cmd  --which
FLASH_REMOTE.cmd --which
```

---

## 二、看数据

1. 给设备和接收源通电，按实际接线连到电脑，双击 `START_STUDIO.cmd`。
2. 在 LoRa 页面“接收来源”选择自动或手动。页面分别显示手动优先来源和当前实际来源；
   优先来源中断时会回退，恢复后重新优先。
3. 显示“超时未见”或“观测中断”时，先查电源与连接，系统会继续尝试恢复。

**接收器已内置**：当 `config/fleet.default.json` 的 `gateway.mode` 为 `legacy_local` 时，
`START_STUDIO.cmd` 会自己拉起 UDP 1680 → HTTP 8780 的接收器，不需要额外脚本。

两种网关模式：

| mode | 含义 | 适用 |
|---|---|---|
| `remote` | 网关**自身**提供 HTTP 拓扑接口（8780） | RHF2S008 一类带 Web 服务的网关 |
| `legacy_local` | 网关只发 UDP，由本机接收器解析 | E870-L 一类纯透传网关 |

`candidate_hosts` 是**有序列表**：同一个候选连续失败 3 次后自动切到下一个，成功即固定。

---

## 三、做卡（给现场同事）

### 1. 一次性配置

双击 `SETUP_SITE.cmd`，回答几项：

```
WiFi 名称 / 认证方式 / WiFi 密码
Tailscale auth key（跨网络管理需要，可留空）
eora 的登录密码（没有私钥时用密码登录）
```

生成 `site.env` 并自动自检，看到下面两行就对了：

```
required keys present (auth=psk, tailscale=on)
fleet public key valid
```

> 想做**生产卡**就要用现场自己的 `site.env`（他们的 WiFi + 他们生成的一次性 key）。
> 从仓库 `.local` 的开发配置做卡会被工具直接拒绝，防止开发者账号外泄。

### 2. 批量做卡

双击 `MK_CARDS.cmd`，输入起始编号与数量（默认 6 / 15），然后**一张一张插卡**：

```
== waiting for card #6 ...
已准备节点 6；实例号已同步。
== #6 done. 拔卡，换下一张。
```

单张：`MK_CARDS.cmd 6 1`

**编号规则**：1–255，不能重号。调试卡（1–5）与生产卡要事先分号段。
已经做过的卡会被 `--batch` 跳过并提示，不会误改编号。

### 3. 首启检查

卡插到树莓派上电，2–5 分钟后拔回来看 `/boot/firmware/eora-status.txt`：

```
6/6 DONE host=eora-air-06 overlay=100.x.x.x ip=183.173.x.x
```

失败会写 `FAILED: <哪一步>`。

> 新卡首启要装依赖与 Tailscale，网络会抖动几分钟。**等 `6/6 DONE` 再远程操作。**

---

## 四、跨网络刷固件

```powershell
SITE_STATUS.cmd          # 先看有哪几台在线；第一行应为 transport: tailnet
FLASH_REMOTE.cmd --list  # 看会用哪个镜像
FLASH_REMOTE.cmd         # 刷全部；或 --group 2 / --only eora-air-06
SITE_FLASH.cmd           # 菜单版：1=本地组 2=远程组 3=全部 4=单台
```

刷完再跑一次 `SITE_STATUS.cmd`，确认 build 列一致。

- 镜像默认取 `firmware/mid_edge.bin`（交付包不带构建记录）。
- 每台必须出现 `VERIFIED` 才算成功。
- **`FLASH_NODES.cmd` 只做本机 USB 串口刷写**，与远程刷板无关。

---

## 五、分组

```powershell
SITE_GROUP.cmd           # 组号 + WiFi 信道
```

| 组 | group | 建议信道 |
|---|---|---|
| 本地（现有 5 块） | 1 | 11（实测在用） |
| 远程（15 块） | 2 | 6（与本地错开） |

ESP-NOW 只有同组才互相可见；LoRa 上行不受分组影响（帧头带 `wifi_group` 标签）。

> 改 group 会切换整张网格的配置：**必须整组一次改完**，分批改会出现两半互不可见。
> 命令返回里的 `group_reported` 才是实际值，只看 `ok` 不够。

---

## 六、目录结构（只留运行所需）

```
app/
  flash/            本机 USB 刷写台（FLASH_NODES.cmd 使用）
  gateway_setup/    网关部署向导（SETUP_GATEWAY.cmd 使用）
  services/
    assets/mobile_gateway/   前端资源（新版）
    tools/mobile_gateway/    前端后端（新版）
    tools/flight_link/       LoRa 网关服务 + ARM 端的 3.4 解码器副本
    tools/fleet/             机群：刷板、分组、做卡包生成
    tools/gateway_probe/     做卡、Pi 侧 helper
  start/launcher.py  打包版启动器（发布清单校验 + 硬件探测）
firmware/            mid_edge.bin + manifest.json + 分区表
runtime/             随包 Windows Python 与网关运行时
config/              fleet.default.json（现场默认配置）+ 两个示例
docs/                9 份现场文档
tools/
  mid_baseline/gateway_probe/   接收器（topology_server + start_frontend）
  release/                      发布清单刷新/校验、解码器一致性检查、迁移脚本
fleet.pub            管理公钥（做卡时写进每张卡；私钥不在仓库）
```

### 有意不在包里的

| 不在 | 原因 |
|---|---|
| `simulation/`、`tests/` | 本地仿真与开发测试，现场不跑 |
| `BUILD-*/` 构建记录 | 交付用 `firmware/mid_edge.bin` |
| `firmware/flight_link/`、`tools/flight_link/` 源码 | 打包位置已有 `app/services/tools/flight_link/` |
| 开发侧 fleet / probe 副本 | 只用 `app/services/tools/` 那一份 |
| `coordination/`、周报、交接文档 | 开发过程记录 |

---

## 七、改完代码后必做的三件事

### 1. 重算发布清单（改了 `app/services` 下任何文件）

`app/start/launcher.py` 用 `firmware/manifest.json` 冻结 `app/services` 下每个
`.py / .js / .css / .html / .json` 的 SHA256。**哈希不符或有未登记文件就拒绝启动。**

```powershell
python tools\release\refresh_release_manifest.py
python tools\release\verify_release.py
```

### 2. 不启动硬件也能验证整包

```powershell
runtime\python\python.exe -X utf8 app\start\launcher.py --dry-run
```

期望输出 `"release_ready": true`。

### 3. ARM 端解码器副本一致性

`app/services/tools/flight_link/compat_decoder.py` 是 ARM 网关（Python 3.4）用的手工副本，
与 `app/services/firmware/.../lora_ref/decoder.py` 是两份实现：

```powershell
python tools\release\check_decoder_parity.py --deploy .
```

必须 `7/7 一致`。它已经抓到过一次真实漂移（旧帧的 `node_number` 一个返回 `None`、一个返回 `0`）。

---

## 八、常用命令（命令行等价）

| 双击 | 等价命令 |
|---|---|
| `SETUP_SITE.cmd` | `runtime\python\python.exe app\services\tools\fleet\write_site_env.py site.env` |
| `MK_CARDS.cmd` | `... app\services\tools\gateway_probe\mkcard.py --batch --from 6 --count 15` |
| `SITE_STATUS.cmd` | `... app\services\tools\fleet\fleet.py status` |
| `FLASH_REMOTE.cmd` | `... app\services\tools\fleet\flash_nodes.py` |
| `SITE_GROUP.cmd 2 6` | `... app\services\tools\fleet\fleet.py group --group 2 --channel 6` |

密码从 `site.env` 自动读取，**不需要手工设置环境变量**；
没有私钥的机器会自动改走密码通道（Windows OpenSSH 的 `SSH_ASKPASS`，不需要额外工具）。

---

## 九、文档

| 文档 | 内容 |
|---|---|
| [docs/SITE_OPERATOR_RUNBOOK.md](docs/SITE_OPERATOR_RUNBOOK.md) | 现场同事的双击式操作单 |
| [docs/OPERATOR_HANDBOOK.md](docs/OPERATOR_HANDBOOK.md) | 两人分工、配置字段、命令速查、故障表 |
| [docs/DEPLOY_LAYOUT.md](docs/DEPLOY_LAYOUT.md) | 路径对照、改代码流程、密码策略、启动脚本说明 |
| [docs/CARD_CONTENTS.md](docs/CARD_CONTENTS.md) | 卡上写了什么（逐项） |
| [docs/CARD_PROVISIONING_MODES.md](docs/CARD_PROVISIONING_MODES.md) | WiFi 两种认证、Tailscale 三种模式 |
| [docs/DEV_PROD_SPLIT.md](docs/DEV_PROD_SPLIT.md) | 开发/生产解耦与生产包内容 |
| [docs/FLEET_GROUPS.md](docs/FLEET_GROUPS.md) | 两个 group 的隔离与信道 |
| [docs/BATCH_CARD_CHECKLIST.md](docs/BATCH_CARD_CHECKLIST.md) | 批量做卡准备清单 |
| [docs/LRN1_FRAME.md](docs/LRN1_FRAME.md) | LoRa 上行帧结构（协作方可查） |

---

## 十、与开发分支的关系

本分支由 `codex/baseline-reproduction-20261023` **合并**而来，之后所有代码改动都走
**「改 baseline → 迁移到 deploy」** 一条路，不再直接改本仓库源码。

### 10.1 迁移方式

```powershell
# 在开发仓库里
python tools\release\sync_to_deploy.py --deploy <deploy 路径> --check   # 先看差哪些
python tools\release\sync_to_deploy.py --deploy <deploy 路径>           # 同步
```

对应关系（39 个文件）写死在 `sync_to_deploy.py` 的 `PAIRS` 里。同步后必须重算发布清单。

### 10.2 允许本仓库单独存在的东西

| 内容 | 原因 |
|---|---|
| `app/start/launcher.py`、`app/flash/`、`app/gateway_setup/` | 打包/硬件适配层，开发仓库没有 |
| `app/services/tools/flight_link/compat_decoder.py` | ARM 运行时（Python 3.4）副本 |
| `firmware/manifest.json` | 由脚本生成，不手改 |
| `config/fleet.default.json` | 现场默认配置（节点表、网关、分组） |
| 根目录 `*.cmd` | 交付入口（内容与开发仓库**完全相同**，靠运行时自检分流） |
| `docs/` 子集、`README.md` | 交付文档 |

### 10.3 验证两边一致

```powershell
python tools\release\sync_to_deploy.py --deploy <deploy 路径> --check
# 输出“两边一致。”才算迁移完成
```

---

## 附录：原现场测试包说明（保留原文）

这是现场测试包，LoRa 下行控制当前关闭。

1. 给设备及所选接收源通电，按实际接线方式连接电脑，然后双击 `START_STUDIO.cmd`。
2. 在 LoRa 页面“接收来源”选择自动或手动来源。页面分别显示手动优先来源和当前实际来源；优先来源中断时可能回退，恢复后重新优先使用。显示“超时未见”或“观测中断”时，先检查对应设备电源和连接，系统会继续尝试恢复。

原有网关无需升级固件或修改配置。现场旧网关固定向 `192.168.137.10:1680` 发送 UDP，电脑网络仍须能按原路径接收；换电脑不会自动改变旧网关保存的发送目标。电脑端兼容该旧 UDP、既有 HTTP 和节点串口接收；HTTP 仅用于已部署接口，不要求旧网关安装新服务。接收源身份通过真实报告核验，不能仅凭接口出现认定节点在线。

页面中灰色连线为历史观察，不能当作当前连通；“超时未见”不直接证明设备断电。需要更新设备时按窗口提示使用 `FLASH_NODES.cmd`；运行记录位于 `data/logs/`。旧网关兼容和切源恢复须经现场条件验收，尚未现场复测。

布局可选“清晰布局”“手动布局”和“GPS 布局”。清晰布局按连接分簇，点击节点聚焦一跳邻居；手动布局中拖动节点，位置按接收来源保存在当前浏览器，刷新后保留，可用“重置布局”恢复；这两种位置均不代表真实地理位置。GPS 布局仅显示有有效坐标的节点，未定位节点仍可在列表查看。连接较多时默认收起连线，可选择“全部连接”；地图会显示实际方向、连接总数和当前绘制数，隐藏不代表连接不存在。右侧可按编号、标签或 MAC 搜索并筛选状态，筛选只影响列表。

## 日常操作（三条命令）

```powershell
FLASH_REMOTE.cmd              # 更新算法/固件：先归一化链路状态，再刷机，最后逐台读回校验
SWITCH_LINK.cmd lora24        # 启用 2.4 GHz LoRa 链路层
SWITCH_LINK.cmd espnow        # 切回 ESP-NOW
```

补充：

```powershell
SWITCH_LINK.cmd status              # 只读，看当前链路配置
SWITCH_LINK.cmd toggle              # 在两个链路层之间来回切，不必记当前是哪个
SWITCH_LINK.cmd lora24 eora-air-01  # 只操作指定设备
FLASH_REMOTE.cmd --skip-normalize   # 只刷机，保留当前 NVS 链路配置
FLASH_REMOTE.cmd path\to\image.bin  # 指定镜像（回滚用）
```

### FLASH_REMOTE 与 FLASH_NODES 的关系

| 能力 | FLASH_NODES.cmd | FLASH_REMOTE.cmd |
| --- | --- | --- |
| 刷写固件 | 是 | 是（内部调用 FLASH_NODES） |
| 刷前归一化链路状态 | 否 | 是 |
| 刷后读回配置校验 | 只校验 build id | 追加参数读回 |
| 单台定向刷写 | 是（`--only`） | 否，需直接用 FLASH_NODES |
| 列出可用镜像 | 是（`--list`） | 否 |

所以两者不是重复：`FLASH_REMOTE` 是**带安全护栏的默认入口**，
`FLASH_NODES` 是**底层原语**（批量刷写、单台定向、列镜像时使用）。

为什么必须归一化：esptool 只写 app 分区，NVS 保留 `link_mode` 与射频角色。
节点若停在 `lora24` 且未设 `role=link`，重烧后会既无 Wi-Fi 也无 2.4G 链路，
只能拆下来接 USB。`FLASH_REMOTE` 默认先写回 `espnow` 规避这一点。