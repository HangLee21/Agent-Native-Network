# 把本周成果推到 deploy 的准备清单

对比基准：
- 我方：`codex/baseline-reproduction-20261023`（HEAD `2815f46`）
- 目标：`codex/production-deployment`（`d27bb3e`，**未被修改**）
- 分叉点：`f304632`（11-14）

---

## 一、总体差异

| 项 | 数量 |
|---|---:|
| 我方独有提交 | **81** |
| deploy 独有提交 | **21** |
| 两边都存在的路径 | **仅 4 个** |
| 我方新增/修改的路径 | 777 |

**4 个重叠路径**（需要小心合并，其余都是纯新增）：

```
.gitignore
FLASH_NODES.cmd
START_STUDIO.cmd
config/fleet.default.json
```

> **结论：不要 merge。** deploy 有 21 个我们完全没有的提交（网关部署、本机刷写台、
> Studio 源解耦、密集拓扑），merge 会大面积冲突，也容易覆盖它们的打包布局。
> **采用「文件级搬运 + 分主题提交」。**

---

## 二、deploy 的目录布局（决定文件往哪放）

```
app/flash/          console.py  flash_nodes.py  serial_adapter.py  workflow.py   ← 本机 USB 刷写
app/gateway_setup/  setup_gateway.py  linux_installer.py  ssh_*  bootstrap.ps1   ← 网关部署
app/services/
  assets/mobile_gateway/   view.js  studio-model.js  studio.js  fleet-model.js    ← 前端
  tools/mobile_gateway/    studio.py  sources.py  fleet_registry.py               ← 前端后端
  firmware/                                                                        ← 打包固件
app/start/launcher.py                                                              ← 启动器
firmware/           mid_edge.bin  manifest.json  partition-table-4k.bin
runtime/            网关运行时 tar.gz + Python 运行时
config/fleet.default.json
FLASH_NODES.cmd  SETUP_GATEWAY.cmd  START_STUDIO.cmd
```

**关键发现：deploy 里没有 `topology_server`（UDP 接收器）。**
而它的 `sources.py` 里 `legacy_local` 模式正是去轮询 `127.0.0.1:8780`。
→ **deploy 目前缺这一块，前端拿不到 LoRa 数据。这是必须补上的第一件。**

---

## 三、做卡（deploy 完全没有）

| 我方文件 | 部署位置 | 说明 |
|---|---|---|
| `tools/mid_baseline/gateway_probe/mkcard.py`（26.9 KB） | `app/card/mkcard.py` | 核心逻辑 |
| `MK_CARD.cmd` | 根目录（新增） | 一键入口 |

**mkcard 内含的关键修复**（这些都是踩出来的，别丢）：

1. **cloud-init 实例身份**：改写 `cmdline.txt` 里的 `ds=nocloud;i=...`，
   并断言 `ds=nocloud` 恰好出现一次（只改 `meta-data` 无效）
2. **802.1X 改写**：Imager 写的密码型 WiFi 改写成 `eap/peap/mschapv2`
3. **NTP 时钟等待**：树莓派无 RTC，先等 `NTPSynchronized=yes` 再动 apt，
   否则仓库签名校验失败 → Tailscale 装不上
4. **esptool 固定 5.6.0**：4.x/5.x CLI 拼写不同
5. **自动找卡**：接受 `F` / `f:` / `F:\`，盘符错了自动回退检测
6. **失败原因回显**：重写前先打印卡上 `eora-status.txt` 的上次失败原因

**依赖（不进仓库，目标机需自备）**：
`.local/mid/pi/device.env`（WiFi + Tailscale auth key）、`sudo_pass.txt`。

---

## 四、远程更新（Tailscale 机群，deploy 完全没有）

| 我方文件 | 部署位置 | 说明 |
|---|---|---|
| `tools/mid_baseline/fleet/fleet.py`（14.8 KB） | `app/services/tools/fleet/fleet.py` | 按名管理、推送、远程刷写 |
| `tools/mid_baseline/fleet/flash_nodes.py`（5.3 KB） | `app/services/tools/fleet/remote_flash_nodes.py` | **必须改名**，见风险 2 |
| `tools/mid_baseline/fleet/refresh_labels.py`（5.6 KB） | `app/services/tools/fleet/refresh_labels.py` | 标签/编号刷新 |
| `tools/mid_baseline/gateway_probe/node_reader.py`（8.1 KB） | `app/services/pi/node_reader.py` | Pi 侧串口常驻服务 |
| `.../node_reader.service` | `app/services/pi/node_reader.service` | systemd 单元 |
| `.../node_update.py`（7.1 KB） | `app/services/pi/node_update.py` | Pi 侧烧写器（含 esptool 双拼写兜底） |
| `.../pi_node_probe.py`（6.1 KB） | `app/services/pi/pi_node_probe.py` | 串口探针 |
| `FLEET_STATUS.cmd` | 根目录（新增） | 一键看机群 |

**这些修复必须一起带过去**：

- `fleet.py`：**每次同步 helper 脚本**（原先"存在就跳过"，导致改了工具设备仍跑旧版）
- `fleet.py`：`ESPTOOL_VERSION = "5.6.0"`，版本不对就升级/降级
- `fleet.py`：Tailscale `NoState` 要报"服务没起来"，不能报"没有设备"
- `fleet.py`：`VERIFIED` 视为成功（SSH 收尾超时不算失败）
- `flash_nodes.py`：无终端时**直接报错**，不能挂在密码输入
- `node_update.py`：按 `esptool version` 切换**整套 CLI 拼写**（子命令+选项+选项值）

---

## 五、接收器（deploy 缺失，优先补）

| 我方文件 | 部署位置 |
|---|---|
| `tools/mid_baseline/gateway_probe/topology_server.py`（30.1 KB） | `app/services/tools/gateway_probe/topology_server.py` |
| `tools/mid_baseline/gateway_probe/start_frontend.py`（10.8 KB） | 与 `app/start/launcher.py` 合并 |
| `tools/mid_baseline/gateway_probe/netmode.ps1`（7.1 KB） | `app/services/tools/gateway_probe/netmode.ps1` |

**必带的能力**：
- UDP 收包线程**异常自愈**（重建 socket），ACK 发送失败不杀线程
- `worker_state / worker_error / worker_restarts / ack_errors` 上报
- `gateway_observed` 必须同时要求 worker 在运行
- 下行命令通道 `POST /api/v1/lora/command`（LRC2 + txpk）
- LRN1 状态块解析（含 `wifi_channel`）

---

## 六、前端（6 个文件有差异，需要逐个合）

| 文件 | 我方比 deploy 多/少（行） |
|---|---|
| `view.js` | +188 / −27 |
| `studio-model.js` | +25 / −19 |
| `studio.py` | +27 / −3 |
| `sources.py` | +24 / −9 |
| `fleet-model.js` | +6 / −2 |
| `fleet_registry.py` | +1 / −1 |

**我方多出来的东西（合的时候不能丢）**：

1. 节点年龄**按节点**计算（原来用全局时间 → 停机节点永不失效）
2. `state` 字段按**字符串**解析（原来数字对字符串，导致"互证/失效"永不出现）
3. 状态块字段显示：电压、温度、信道、复位原因、路由/队列/丢帧
4. 标签优先用 LoRa 数字编号（不再 WiFi 优先）
5. 网关失联告警（`gateway_last_pull_age_ms`）

---

## 七、固件

| 项 | 现状 |
|---|---|
| deploy | `firmware/mid_edge.bin` + `manifest.json`（冻结候选 default31） |
| 我方最新 | `BUILD-20261120-lrn1-health/images/mid_edge.bin`（971,408 B，sha256 `2AA298FC...`） |

**建议**：新增一个 `BUILD-*` 目录并把 deploy 的 `firmware/mid_edge.bin` 与
`manifest.json` 指过去，**同时保留旧镜像**，便于回滚。

我们这版固件相对 deploy 冻结版的增量：
节点编号入帧、状态块（复位/电压/温度/内存/队列/路由/SF/功率/故障位/信道）、
GPS 块预留、组帧容量修复、邻居淘汰、esptool 无关的协议修复。

---

## 八、风险点

| # | 风险 | 处理 |
|---|---|---|
| 1 | **直接 merge 会大冲突** | 用文件级搬运 + 分主题提交 |
| 2 | **`flash_nodes.py` 同名不同物**：deploy 的是本机 USB 刷写台，我们的是 Tailscale 远程 | 我们的改名 `remote_flash_nodes.py`，不要覆盖 deploy 的 |
| 3 | `START_STUDIO.cmd` / `FLASH_NODES.cmd` 两边实现不同 | **以 deploy 入口为骨架**，把我们新增的分支逻辑合进去 |
| 4 | `config/fleet.default.json` schema | 确认两边都是 `{schema_version:1, nodes:[]}` |
| 5 | `.local/` 被 gitignore | 目标机需重新准备 `device.env` / `sudo_pass.txt` |
| 6 | deploy 的 21 个提交不能丢 | 推送前 `git log deploy` 存档，推送后逐条确认仍在 |

---

## 九、建议执行顺序

```
1. 从 deploy 拉一个 feature/port-1123 分支（不直接推 deploy）
2. 补接收器       topology_server + start_frontend + netmode      ← 没有它前端无数据
3. 补做卡         mkcard + MK_CARD.cmd                             ← 纯新增，零冲突
4. 补远程更新     fleet + remote_flash_nodes + pi 三个脚本 + FLEET_STATUS
5. 合前端 6 个文件（逐个核对上面第六节的 5 条能力）
6. 换固件镜像 + 更新 manifest（保留旧镜像）
7. 在干净机器上按 README 走一遍验收
```

---

## 十、验收清单（推完后逐条跑）

| # | 检查 | 通过标准 |
|---|---|---|
| 1 | 起接收器 | `worker_state=running`，`frames` 持续增长 |
| 2 | 拔网线再插回 | `worker_restarts` 增加但**服务不死**，数据自动恢复 |
| 3 | `MK_CARD.cmd` 空参回车 | 自动找到卡；写入后 `cmdline` 的 `i=` 与 `meta-data` 一致 |
| 4 | `MK_CARD.cmd` 给错盘符 | 提示后自动回退，不假装失败 |
| 5 | `FLEET_STATUS.cmd` | 列出五台，含节点 MAC / build / 温度 |
| 6 | `fleet.py update` 单台 | `VERIFIED`，且 esptool 版本被统一 |
| 7 | Studio | 五节点在线；节点卡片显示电压/温度/信道；断网者显示"失效" |
| 8 | 下行命令 | `POST /api/v1/lora/command` 返回 frame_hex；节点回执可匹配 |
