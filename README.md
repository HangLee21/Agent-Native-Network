# EoRa 现场交付包

**打包分支 `codex/production-deployment`。**
基线分支的前端、后端、做卡与机群工具已并入本分支（**推新版**），
只把运行方式适配到原来的打包形态（`runtime\python` + `app\start\launcher.py`）。

---

## 一、五个入口，按你要做的事选一个

| 我要做什么 | 双击 | 说明 |
|---|---|---|
| **看实时拓扑 / 收数据** | `START_STUDIO.cmd` | 打包版前端（`runtime\python` + `app\start\launcher.py`） |
| **给新卡写入身份** | `SETUP_SITE.cmd` → `MK_CARDS.cmd` | 先配置一次，再批量做卡 |
| **跨网络刷固件** | `SITE_STATUS.cmd` → `FLASH_REMOTE.cmd` | 走 Tailscale，可跨网络 |
| **本机 USB 直连刷写** | `FLASH_NODES.cmd` | 串口直连，原来的刷写台 |
| **部署一台新网关** | `SETUP_GATEWAY.cmd` | 网关安装向导 |

> **两个刷写入口不要混用**：
> `FLASH_NODES.cmd` = 本机 USB 直连；`FLASH_REMOTE.cmd` = 跨网络机群。
> `SITE_FLASH.cmd` 是 `FLASH_REMOTE.cmd` 的引导菜单版（选组/选设备），实现是同一个。

---

## 二、看数据

1. 给设备和接收源通电，按实际接线连到电脑，双击 `START_STUDIO.cmd`。
2. 在 LoRa 页面"接收来源"选择自动或手动。页面分别显示手动优先来源和当前实际来源；
   优先来源中断时会回退，恢复后重新优先。
3. 显示"超时未见"或"观测中断"时，先查电源与连接，系统会继续尝试恢复。

**如果打包版拿不到数据**（例如旧网关只往 `192.168.137.10:1680` 发 UDP），
可以用基线分支带来的接收器：

```
START_RECEIVER.cmd        ← UDP 1680 -> HTTP 8780，供前端轮询
```

这是**独立入口**，不影响 `START_STUDIO.cmd` 的行为。

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

### 2. 批量做卡

双击 `MK_CARDS.cmd`，输入起始编号与数量（默认 6 / 15），然后**一张一张插卡**：

```
== waiting for card #6 ...
已准备节点 6；实例号已同步。
== #6 done. 拔卡，换下一张。
```

单张：`MK_CARDS.cmd 6 1`

**编号规则**：1–255，不能重号。调试卡与生产卡要事先分号段。

### 3. 首启检查

卡插到树莓派上电，2–5 分钟后拔回来看 `/boot/firmware/eora-status.txt`：

```
6/6 DONE host=eora-air-06 overlay=100.x.x.x ip=192.168.x.x
```

失败会写 `FAILED: <哪一步>`。

---

## 四、跨网络刷固件

```powershell
SITE_STATUS.cmd          # 先看有哪几台在线；第一行应为 transport: tailnet
SITE_FLASH.cmd           # 选 1=本地组 2=远程组 3=全部 4=单台
```

刷完再跑一次 `SITE_STATUS.cmd`，确认 build 列一致。

**原 `FLASH_NODES.cmd` 未改动**，仍然只做本机串口刷写。

---

## 五、分组

```powershell
SITE_GROUP.cmd           # 组号 + WiFi 信道
```

- 本地组 = group 1 / 信道 1
- 远程组 = group 2 / 信道 6

ESP-NOW 只有同组才互相可见；LoRa 上行不受分组影响（帧头带 `wifi_group` 标签）。

---

## 六、目录结构（只留运行所需）

```
app/
  flash/            本机 USB 刷写台（FLASH_NODES.cmd 使用）
  gateway_setup/    网关部署向导（SETUP_GATEWAY.cmd 使用）
  services/
    assets/mobile_gateway/   前端资源（新版）
    tools/mobile_gateway/    前端后端（新版）
    tools/flight_link/       LoRa 网关服务
    tools/fleet/             机群：刷板、分组、做卡包生成      ← 新增
    tools/gateway_probe/     做卡、Pi 侧 helper                 ← 新增
  start/launcher.py  打包版启动器（发布清单校验 + 硬件探测）
firmware/            mid_edge.bin + manifest.json + 分区表
runtime/             随包 Windows Python 与网关运行时
config/              fleet.default.json（现场默认配置）+ 两个示例
docs/                9 份现场文档
tools/
  mid_baseline/gateway_probe/   接收器（topology_server + start_frontend）
  release/                      发布清单刷新与校验
fleet.pub            管理公钥（做卡时写进每张卡；私钥不在仓库）
```

### 有意不在包里的

| 不在 | 原因 |
|---|---|
| `simulation/` | 本地仿真，现场不跑 |
| `tests/` | 开发测试 |
| `BUILD-*/` 构建记录 | 交付用 `firmware/mid_edge.bin` |
| `firmware/flight_link/`、`tools/flight_link/` 源码 | 打包位置已有 `app/services/tools/flight_link/` |
| 开发侧 fleet / probe 副本 | 只用 `app/services/tools/` 那一份 |
| `coordination/`、周报、交接文档 | 开发过程记录 |

---

## 七、改完代码后必须做的一件事

`app/start/launcher.py` 用 `firmware/manifest.json` 冻结 `app/services` 下每个
`.py / .js / .css / .html / .json` 的 SHA256。**哈希不符或有未登记文件就拒绝启动。**

```powershell
python tools\release\refresh_release_manifest.py   # 改完 app/services 后重算
python tools\release\verify_release.py              # 等价校验启动器的检查
```

不启动硬件也能验证整包：

```powershell
runtime\python\python.exe -X utf8 app\start\launcher.py --dry-run
```

期望输出 `"release_ready": true`。

---

## 八、常用命令（命令行等价）

| 双击 | 等价命令 |
|---|---|
| `SETUP_SITE.cmd` | `runtime\python\python.exe app\services\tools\fleet\write_site_env.py site.env` |
| `MK_CARDS.cmd` | `runtime\python\python.exe app\services\tools\gateway_probe\mkcard.py --batch --from 6 --count 15` |
| `SITE_STATUS.cmd` | `... app\services\tools\fleet\fleet.py status` |
| `FLASH_REMOTE.cmd` | `... app\services\tools\fleet\flash_nodes.py` |
| `SITE_GROUP.cmd 2 6` | `... app\services\tools\fleet\fleet.py group --group 2 --channel 6` |

密码从 `site.env` 自动读取，**不需要手工设置环境变量**。
镜像默认取 `firmware/mid_edge.bin`。

---

## 九、文档

| 文档 | 内容 |
|---|---|
| [docs/SITE_OPERATOR_RUNBOOK.md](docs/SITE_OPERATOR_RUNBOOK.md) | 现场同事的双击式操作单 |
| [docs/OPERATOR_HANDBOOK.md](docs/OPERATOR_HANDBOOK.md) | 两人分工、配置字段、命令速查、故障表 |
| [docs/DEPLOY_LAYOUT.md](docs/DEPLOY_LAYOUT.md) | 本仓库路径与开发仓库的对照 |
| [docs/CARD_CONTENTS.md](docs/CARD_CONTENTS.md) | 卡上写了什么（逐项） |
| [docs/CARD_PROVISIONING_MODES.md](docs/CARD_PROVISIONING_MODES.md) | WiFi 两种认证、Tailscale 三种模式 |
| [docs/DEV_PROD_SPLIT.md](docs/DEV_PROD_SPLIT.md) | 开发/生产解耦与生产包内容 |
| [docs/FLEET_GROUPS.md](docs/FLEET_GROUPS.md) | 两个 group 的隔离与信道 |
| [docs/BATCH_CARD_CHECKLIST.md](docs/BATCH_CARD_CHECKLIST.md) | 批量做卡准备清单 |
| [docs/LRN1_FRAME.md](docs/LRN1_FRAME.md) | LoRa 上行帧结构（协作方可查） |

---

## 九、与开发分支的关系

本分支由 `codex/baseline-reproduction-20261023` **合并**（merge commit）而来。
合并策略是：**现场要用的能力并进来，交付形态一个字节都不动。**

### 9.1 并进来的（推新版）

| 内容 | 位置 | 说明 |
|---|---|---|
| **前端** | `app/services/assets/mobile_gateway/`（8 个） | 取 baseline 最新版，与 baseline **字节一致** |
| **前端后端** | `app/services/tools/mobile_gateway/`（9 个） | 取 baseline 最新版，补回 `replay.py` |
| 做卡与机群工具 | `app/services/tools/fleet/`、`gateway_probe/`（12 个） | 新增 |
| 一键脚本 | `SETUP_SITE.cmd`、`MK_CARDS.cmd`、`SITE_*.cmd`、`FLASH_REMOTE.cmd`、`START_RECEIVER.cmd` | 新增 |
| 接收器 | `tools/mid_baseline/gateway_probe/topology_server.py` | 打包版原本缺失 |
| 文档 | `docs/` | 新增 |
| 维护脚本 | `tools/release/`（刷新与校验发布清单） | 新增 |
| 开发树 | `tools/`、`simulation/`、`tests/`、固件源码 `firmware/` | 合并带入，运行不依赖 |

### 9.2 为适配打包形态所做的改动（仅两处）

新代码假设自己在开发树里，打包后路径不同，因此改了两处**路径解析**，逻辑不变：

| 文件 | 改动 |
|---|---|
| `app/services/tools/mobile_gateway/studio.py` | 前端资源目录：先试 `research/...`，不存在则用 `ROOT/assets/mobile_gateway` |
| 同上 | fleet 配置：依次试 `app/services/data`、`app/services/config`、**仓库根 `config/`** |

### 9.3 发布清单必须同步（关键）

`app/start/launcher.py` 用 `firmware/manifest.json` 里的 `service_files_sha256`
冻结 `app/services` 下每一个 `.py/.js/.css/.html/.json`；**哈希不符或有未登记文件就拒绝启动**。

本次替换 13 个、新增 12 个文件后，清单已重算为 36 条，并做了等价校验：

```
python tools\release\verify_release.py
   PASS: release manifest matches the tree
```

**以后凡是改 `app/services` 下的文件，都必须再跑一次：**

```
python tools\release\refresh_release_manifest.py
python tools\release\verify_release.py
```

### 9.4 保留原样的

`START_STUDIO.cmd`、`FLASH_NODES.cmd`、`SETUP_GATEWAY.cmd`、`app/start/launcher.py`、
`app/flash/`、`app/gateway_setup/`、`app/services/firmware/`、`runtime/`、`firmware/`。

这些是"适配原来硬件"的部分：启动器仍用 `runtime\python` 拉起
`app/services/tools/mobile_gateway/studio.py`（现在指向的是新版代码与新版前端）。

### 9.5 有意没并的

| 内容 | 原因 |
|---|---|
| `coordination/` | 开发过程记录，不属于交付 |
| `CHANGELOG.md`、`START_HERE.md`、`docs/IMPLEMENTATION_STATUS.md`、`docs/PROJECT_STATUS.md` | 同上 |
| `firmware/mid_baseline/field_agent/` 开发树 | 打包位置已有 `app/services/firmware/mid_baseline/`，避免两份源码 |

---

## 附录：原现场测试包说明（保留原文）

这是现场测试包，LoRa 下行控制当前关闭。

1. 给设备及所选接收源通电，按实际接线方式连接电脑，然后双击 `START_STUDIO.cmd`。
2. 在 LoRa 页面“接收来源”选择自动或手动来源。页面分别显示手动优先来源和当前实际来源；优先来源中断时可能回退，恢复后重新优先使用。显示“超时未见”或“观测中断”时，先检查对应设备电源和连接，系统会继续尝试恢复。

原有网关无需升级固件或修改配置。现场旧网关固定向 `192.168.137.10:1680` 发送 UDP，电脑网络仍须能按原路径接收；换电脑不会自动改变旧网关保存的发送目标。电脑端兼容该旧 UDP、既有 HTTP 和节点串口接收；HTTP 仅用于已部署接口，不要求旧网关安装新服务。接收源身份通过真实报告核验，不能仅凭接口出现认定节点在线。

页面中灰色连线为历史观察，不能当作当前连通；“超时未见”不直接证明设备断电。需要更新设备时按窗口提示使用 `FLASH_NODES.cmd`；运行记录位于 `data/logs/`。旧网关兼容和切源恢复须经现场条件验收，尚未现场复测。

布局可选“清晰布局”“手动布局”和“GPS 布局”。清晰布局按连接分簇，点击节点聚焦一跳邻居；手动布局中拖动节点，位置按接收来源保存在当前浏览器，刷新后保留，可用“重置布局”恢复；这两种位置均不代表真实地理位置。GPS 布局仅显示有有效坐标的节点，未定位节点仍可在列表查看。连接较多时默认收起连线，可选择“全部连接”；地图会显示实际方向、连接总数和当前绘制数，隐藏不代表连接不存在。右侧可按编号、标签或 MAC 搜索并筛选状态，筛选只影响列表。
