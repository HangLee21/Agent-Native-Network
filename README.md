# EoRa 现场交付包

**打包分支 `codex/production-deployment`。**
基线分支的做卡、机群、接收器能力已并入本分支；**原有启动脚本与打包结构保持不变。**

---

## 一、四个入口，按你要做的事选一个

| 我要做什么 | 双击 | 说明 |
|---|---|---|
| **看实时拓扑 / 收数据** | `START_STUDIO.cmd` | 打包版前端（`runtime\python` + `app\start\launcher.py`） |
| **给新卡写入身份** | `SETUP_SITE.cmd` → `MK_CARDS.cmd` | 先配置一次，再批量做卡 |
| **跨网络刷固件** | `SITE_STATUS.cmd` → `SITE_FLASH.cmd` | 走 Tailscale，可跨网络 |
| **部署一台新网关** | `SETUP_GATEWAY.cmd` | 网关安装向导 |

> `FLASH_NODES.cmd` 是**本机 USB 刷写台**（串口直连），不要和跨网络的 `SITE_FLASH.cmd` 混用。

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

## 六、目录结构

```
app/
  flash/            本机 USB 刷写台（FLASH_NODES.cmd 使用）
  gateway_setup/    网关部署向导（SETUP_GATEWAY.cmd 使用）
  services/
    assets/mobile_gateway/   前端资源
    tools/mobile_gateway/    前端后端
    tools/fleet/             机群管理：刷板、分组、做卡包生成      ← 新增
    tools/gateway_probe/     做卡、Pi 侧 helper、接收器            ← 新增
  start/launcher.py  打包版启动器
firmware/            打包固件（mid_edge.bin + manifest）
runtime/             随包 Python 与网关运行时
docs/                全部文档
config/              示例配置（fleet 主机表、分组表）
BUILD-*/             固件构建产物
```

---

## 七、常用命令（命令行等价）

| 双击 | 等价命令 |
|---|---|
| `SETUP_SITE.cmd` | `python app\services\tools\fleet\write_site_env.py site.env` |
| `MK_CARDS.cmd` | `python app\services\tools\gateway_probe\mkcard.py --batch --from 6 --count 15` |
| `SITE_STATUS.cmd` | `python app\services\tools\fleet\fleet.py status` |
| `SITE_FLASH.cmd 2` | `python app\services\tools\fleet\flash_nodes.py --group 2` |
| `SITE_GROUP.cmd 2 6` | `python app\services\tools\fleet\fleet.py group --group 2 --channel 6` |

密码从 `site.env` 自动读取，**不需要手工设置环境变量**。

---

## 八、文档

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

---

## 九、与开发分支的关系

本分支由 `codex/baseline-reproduction-20261023` 合并而来，但**只保留可运行的部分**：

| 保留 | 说明 |
|---|---|
| 做卡、机群、接收器工具 | 新增在 `app/services/tools/` |
| 文档 | `docs/` |
| 固件源码 | 打包位置 `app/services/firmware/mid_baseline/`（未重复引入开发树） |
| 仿真、协调记录、构建记录 | **不发布**（不属于现场交付） |

**合并后未删除、未修改任何原有交付文件**；`START_STUDIO.cmd`、`FLASH_NODES.cmd`、
`SETUP_GATEWAY.cmd`、`app/flash/`、`app/gateway_setup/`、`app/start/`、
`app/services/assets/`、`app/services/tools/mobile_gateway/`、`runtime/`、`firmware/`
均与合并前**逐字节一致**。

---

## 附录：原现场测试包说明（保留原文）

这是现场测试包，LoRa 下行控制当前关闭。

1. 给设备及所选接收源通电，按实际接线方式连接电脑，然后双击 `START_STUDIO.cmd`。
2. 在 LoRa 页面“接收来源”选择自动或手动来源。页面分别显示手动优先来源和当前实际来源；优先来源中断时可能回退，恢复后重新优先使用。显示“超时未见”或“观测中断”时，先检查对应设备电源和连接，系统会继续尝试恢复。

原有网关无需升级固件或修改配置。现场旧网关固定向 `192.168.137.10:1680` 发送 UDP，电脑网络仍须能按原路径接收；换电脑不会自动改变旧网关保存的发送目标。电脑端兼容该旧 UDP、既有 HTTP 和节点串口接收；HTTP 仅用于已部署接口，不要求旧网关安装新服务。接收源身份通过真实报告核验，不能仅凭接口出现认定节点在线。

页面中灰色连线为历史观察，不能当作当前连通；“超时未见”不直接证明设备断电。需要更新设备时按窗口提示使用 `FLASH_NODES.cmd`；运行记录位于 `data/logs/`。旧网关兼容和切源恢复须经现场条件验收，尚未现场复测。

布局可选“清晰布局”“手动布局”和“GPS 布局”。清晰布局按连接分簇，点击节点聚焦一跳邻居；手动布局中拖动节点，位置按接收来源保存在当前浏览器，刷新后保留，可用“重置布局”恢复；这两种位置均不代表真实地理位置。GPS 布局仅显示有有效坐标的节点，未定位节点仍可在列表查看。连接较多时默认收起连线，可选择“全部连接”；地图会显示实际方向、连接总数和当前绘制数，隐藏不代表连接不存在。右侧可按编号、标签或 MAC 搜索并筛选状态，筛选只影响列表。
