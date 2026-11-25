# 交接给 Codex 的任务简报（2026-11-14）

> 用途：把本仓库当前实现状态与后续工作完整交代给新的执行窗口。
> 阅读顺序：本文件 → `docs/PROJECT_STATUS.md` → `firmware/mid_baseline/field_agent/ALGORITHM.md`。

---

## 一、任务背景

目标：**面向高速移动无人机集群的可扩展异构自组网**（ESP-NOW 板间 + 八通道 LoRa 网关回传）。

当前阶段：从"5 板实验台已验证"推进到"可上规模的算法与容量"，并把 LoRa 回传从"用一块板子顶替接收端"换成**独立八通道网关**。

三条链路已打通并实测：

1. **板间 ESP-NOW**：5 块 EoRa-HUB-400TB，three-state ND（hello/ACK），源路由（RREQ/RREP/RERR）。
2. **LoRa 上行**：5 板 → RisingHF RHF2S008 八通道网关（470.5 MHz / ch5 / SF7BW125 / 显式头 + CRC）。
3. **前端显示**：Studio（8794）从网关取 TopoJSON 渲染，网关作为独立顶点画出。

---

## 二、环境

| 项 | 值 |
|---|---|
| 仓库 | `D:\Multi-Agent Network` |
| 分支 | `codex/baseline-reproduction-20261023`（HEAD `c03027c`，工作区干净） |
| 远程 | `git@github.com:HangLee21/Agent-Native-Network.git` |
| 固件源码 | `firmware/mid_baseline/field_agent/` |
| IDF 构建目录 | `firmware/mid_baseline/field_agent/idf/` |
| 工具链根 | `D:\Multi-Agent Network\.local\espnow\E1-015`（`environment.json` 给出全部 IDF 环境变量，路径前缀 `R:\` 需替换为工具链根） |
| Python（工具/测试） | `.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe` |
| 文本文件 | **UTF-8**；不要用 `Get-Content`/`Set-Content` 改源码（PowerShell 5.1 会按 GBK 破坏中文并双编码）。编辑用 read/edit 工具或 Python 显式 `encoding='utf-8'` |

### 硬件

| 设备 | 标识 | 说明 |
|---|---|---|
| 5 块 EoRa-HUB-400TB | A `90:da:72:48:a4:f8` / B `…a5:cc` / C `…a4:e0` / D `…a5:20` / E `…a6:98` | ESP32-S3 + LR1121，CH340 USB（VID 0x1a86 / PID 0x7523），串口 460800 |
| 八通道网关 | RisingHF **RHF2S008**，EUI `b827ebFFFE32e2c1` | CM3 + RHF0M301-470（SX1301 + 2×SX1255），`192.168.137.200/24`，仅 22/tcp |

网关登录：`ssh rxhf@192.168.137.200`，口令 `risinghf`（sudo 同口令）。**此口令仅用于本机实验台，不要写入远程仓库或提交。**

---

## 三、已经完成的（按提交）

### `9f6ab23` 网关参数实测提取
- 活动配置 `global_conf.json` → `global_conf_cn470_ch00_07.json`，8 信道为
  470.3 / 470.5 / 470.7 / 470.9 / 471.1 / 471.3 / 471.5 / 471.7 MHz，BW125，多 SF 并行。
- `lorawan_public=true`（公有 sync 0x34）；原来只转发 CRC 有效帧。
- 证据：`simulation/results/20261113-H019-gateway-inventory/`。

### `8e21f6d` 打通网关接收 LRN1
- 网关侧**只改** `local_conf.json`（原文件备份 `local_conf_localhost_1680.json.orig`）：
  `server_address=192.168.137.10`、`forward_crc_error=true`、`forward_crc_disabled=true`。
- 节点侧：5 板 `frequency_hz 470.0→470.5 MHz`、`sync_word 18→52`（匹配网关 ch5 与公有 sync）。
- 实测：`LRN1` 帧 128 B、`stat=1`、RSSI −43…−58 dBm、SNR 8.8…11 dB、CRC32 全对。
- 新增 `tools/mid_baseline/gateway_probe/eora_rx.py`（网关侧只读接收器，必须回 PUSH/PULL ACK，否则转发器 autoquit）与 `topology_server.py`（UDP 1680 → 解码 LRN1 → HTTP 8780 的 `lora.topology.v1`）。
- 证据：`simulation/results/20261113-H019-gateway-eora-link/`。

### `e93f1b8` 前端数据源校验修复
- 根因：`view.js` 硬编码 `data.source==='lora_received_snapshot'`，网关源返回 `gateway_udp_lrn1` 被判"格式不匹配"，页面显示"来源暂时不可读取"。
- 改为 `LORA_SOURCES=['lora_received_snapshot','gateway_udp_lrn1']`；`lora-model.js` 标签表允许 EUI-64。

### `c6ab91d` A 板恢复普通节点
- A 原为 `role=rx`（无网关时顶替接收端），改 `role=tx`；现在 5 板全部上报，`reports=5`。

### `8ac529f` 网关画进拓扑 + 彻底移除串口旁路
- `lora-model.js`：`receiver.gateway_id` 作为独立顶点，每上报节点一条 `kind='lora_uplink'` 边（青色点线）；新增 `uplink` 状态。
- `studio-model.js`：`isMAC` 接受 16 位 EUI-64（原先只认 MAC，网关被布局函数过滤，图上消失）。
- `studio.py`：`/api/v1/lora/topology` **只走网关**，不可达时返回 `state=unavailable`，不再回落串口。
- `lora_reader.py` 标注 DEPRECATED。
- 无头渲染验证：6 节点（A–E + EUI）、15 条边（10 ESP-NOW + 5 上行）。

### `c03027c` LRN1 组帧越界修复（**已构建，未烧录**）
- 问题：`runtime.c` 组帧遍历全部 `ND_PEERS` 无行数上限，缓冲区仅 208 B（44+20/行+4 CRC=8 行）。
  9 邻居即越界写 `len/seq/generation`；30 节点平均度 14 时越界 116 B。
- 新增可移植模块 `lrn1_frame.{c,h}`：
  - 按缓冲区容量算行数上限，超限拒绝；
  - 行选择：非双向邻居优先（拓扑变化），其余轮转游标，保证 N>容量时每邻居在 `ceil(N/8)` 帧内出现；
  - `visible_rows`（偏移 34）记录截断前合格数；
  - `lrn1_set_delay()` 写时延并重算 CRC。
- `runtime.c` 的 `capture()` 改为薄封装，删两个未用静态函数；`CMakeLists.txt` 加入新文件。
- 测试 `firmware/mid_baseline/field_agent/test_lrn1.c`：**17 项全过**（含 12 邻居金丝雀字节不被写）。
- 构建：0 warning / 0 error，`build_id mid-lora-ref-v1-cd389e57767d43250a149a23b069ada250a2dd192f5b634471f52839f5b34783`，镜像 953,520 B，sha256 `493eabfa…`。
- 归档：`BUILD-20261113-lrn1-cap/`。

---

## 四、当前状态：实验台是冷的

2026-11-14 实测：

```
CH340 端口：无            ← 5 块板全部不在线（PresentOnly 无 VID_1A86）
ping 192.168.137.200：FAIL ← 网关离线
UDP 1680：无监听           ← topology_server 未运行
8794：不可达               ← Studio 未运行
git：clean @ c03027c
```

所以**接手后第一步不是写代码，而是把台子恢复起来**。

### 恢复清单（按序）

1. **板子上电/插 USB**，确认 `CH340 端口` 出现 5 个（`python -c` 用上面那个解释器）。
2. **网关上电并接网线**，`ping 192.168.137.200` 通。
3. 网关上确认转发器：`ssh rxhf@192.168.137.200 "systemctl is-active pktfwd"` → `active`；
   并确认 `local_conf.json` 仍是 `server_address=192.168.137.10`。
4. PC 起拓扑服务（前台或后台 job）：
   ```
   python -X utf8 -m tools.mid_baseline.gateway_probe.topology_server --udp-port 1680 --port 8780 --labels <labels.json>
   ```
   `labels.json` 形如 `{"90:da:72:48:a4:f8":"A", ...,"b827ebfffe32e2c1":"RHF2S008"}`。
5. PC 起 Studio：`python -X utf8 -m tools.mobile_gateway.launch_studio` → http://127.0.0.1:8794/
6. 校验：`curl http://127.0.0.1:8780/api/v1/lora/topology` 应见 `reports=5`、`state=receiving`。

---

## 五、下一步待办（按优先级，含验收）

### P0 烧录并验证 LRN1 修复（不要跳过）

- 烧 **D 单独**做金丝雀：`esptool --chip esp32s3 --port <COM> --baud 460800 write_flash --flash_mode dio --flash_freq 40m --flash_size 4MB 0x10000 BUILD-20261113-lrn1-cap/images/mid_edge.bin`
- 验收：`identify()` 的 `build_id` 尾部为 `…f52839f5b34783`；网关侧 D 仍上报、4 行邻居、CRC32 正确；其余 4 块不受影响。
- 通过后再烧 A/B/C/E。
- **回滚**：`BUILD-20261113-4MB-notxblock/images/mid_edge.bin`（build_id `2267bc60…`），同样 app-only。

### P1 多信道分发（八通道真正用起来）

- 目标：5 块板分散到网关 ch0–ch4（470.3/470.5/470.7/470.9/471.1），避免同频抢道。
- 落地方式二选一：
  - 纯设备配置：逐板 `lora_ref_config frequency_hz=…`（最快，可回退）；
  - 固件特性：新增"按 MAC 哈希自选信道"模式（`channel_mode`），需同步 host 测试与 `lora_ref_status` 回显。
- 验收：同一周期下，5 板均可上报且 **单帧 `chan` 字段分布覆盖 5 个不同信道**；对比"同频 vs 分频"的 30 分钟送达率与 AoI。
- 注意：网关 ch 映射见 `docs/LORA_GATEWAY_PARAMETERS.md` §2.1。

### P2 待发窗口随跳数自适应

- 现状：`SR_QUEUE_MS` 固定 250 ms，长链 PDR 0.22–0.28 的瓶颈是"发现时延 > 窗口"。
- 目标：按已知路径长度或上一跳时延放大到 600–1000 ms，短链保持 250 ms。
- 验收：30 节点仿真中长链（≥5 跳）PDR 提升且短链不退化；实机 5 板链路无回归。

### P3 ETX 选路

- 现有 `tx_link_ok/fail` 计数可直接算每邻居投递率；RREP 候选从"最短"改为"最低 ETX"。
- 验收：等距链路质量差异场景下 PDR 提升；不得复现历史负结果（见第七节）。

### P4 上报策略

- 自适应周期 `T=clamp(k·m·τ/ρ, 10s, 120s)`；增量上报（仅变化行）+ 周期性全量；事件触发（邻居新增/失效、路由断裂立即发一帧）。
- 需要 `topology_server.py` 与 `lora-model.js` 同步支持"增量语义"。

### P5 更长期

- 逐跳路由替代源路由（>6 跳时头部线性膨胀）；
- 分簇/骨干降低泛洪半径；
- LET（`mobility.c` 已实现但**未被链接**，`nm` 无 `mob_*` 符号）接入为"避免选即将断的下一跳"；
- 时间同步 → 网关 TDMA 调度（LRN2/LRC1 仅设计未实现）。

---

## 六、已知问题与陷阱

| 问题 | 说明 |
|---|---|
| E 板周期性 input overflow | 每 60 s 约 +80，`uart_tx_drops=0`、`send_callback_timeouts=9`，根因未定（疑似帧类型分布） |
| ESP-NOW peer 上限 | `ESP_NOW_MAX_TOTAL_PEER_NUM=20`，与 `ND_PEERS=32` 冲突，>20 节点必须治理 |
| 同信道干扰 | 470.5 上有**另一台设备**每 5 s 发 `HELLO_0xx`（9 B ASCII），前端按 `LRN1` 魔数过滤 |
| 转发器 autoquit | 无服务器 ACK 时 `lora_pkt_fwd` 会在 5 次未确认 PULL_DATA 后退出；`eora_rx.py`/`topology_server.py` 必须回 ACK |
| 端口漂移 | CH340 的 COM 号会变（同一 Hub 不同口也会变），不要硬编码；用 `list_ports` + `info` 握手识别 |
| build_id 一致性 | `CMakeLists.txt` 里的 SOURCES 参与 build_id 哈希；**必须用全新构建目录 configure**，否则复用旧哈希 |
| PowerShell 引号 | 含 `/`、`-` 开头的多行字符串别直接传给 git/Python（会被当参数/截断）；写临时文件再 `-F`/`-c file` |
| 无头渲染可查页面 | `msedge --headless=new --dump-dom http://127.0.0.1:8794/` 是验证前端最有效的手段 |

---

## 七、已被实验否证的方案（不要重做）

| 方案 | 结果 |
|---|---|
| 固定 RREQ 转发上限 8 帧 | PDR 0.909 → 0.642 |
| 沿途 gratuitous RREP | PDR 0.911 → 0.836 |
| 广播重传解决长链 | 0.054 → 0.062（无意义） |
| 单纯放大 TTL（4→32） | 长链 0.224 → 0.280，代价大收益小 |
| 单纯加大队列/缓存 | 只推迟溢出 |

另：仿真器**没有 Wi-Fi CSMA/冲突模型**，所有 PDR 都是乐观上界，不能当作实测。

---

## 八、工程约束（硬性）

1. **失败即停**（fail-closed）：任何校验不通过就不写、不烧、不上报。
2. **证据只追加**：新运行写入 `simulation/outputs/<任务ID>/<run-id>/`；采纳后另建 `simulation/results/<日期>-<任务ID>-<主题>/`，含 `SOURCE.json`。
3. **不臆造**：未实测的标"未验证"，不把历史数据写成本机通过，不编造日志/MAC/哈希。
4. **设备身份**：只用实测 MAC/EUI；不猜默认口令；网关口令不提交。
5. **烧录纪律**：先读 manifest 校验 sha256 与 build_id 再写；app-only 写 `0x10000`；分区表未变就不要全片擦除（NVS 里有板子配置）。
6. **单一写入者**：同一文件同时只有一个窗口写。
7. **文档同步**：改动后同步 `docs/PROJECT_STATUS.md`、`docs/IMPLEMENTATION_STATUS.md`、`CHANGELOG.md`。
8. **前端改动必须用无头渲染验证**，不能只看接口返回。

---

## 九、关键命令速查

```powershell
# 板子识别（MAC ↔ COM）
python -X utf8 -c "from serial.tools import list_ports; print([(p.device,p.location) for p in list_ports.comports() if p.vid==6790])"

# 主机测试（LRN1 组帧）
gcc -std=gnu11 -Wall -Wextra -O2 -I firmware\mid_baseline -I firmware\mid_baseline\field_agent `
  firmware\mid_baseline\field_agent\test_lrn1.c firmware\mid_baseline\field_agent\lrn1_frame.c `
  firmware\mid_baseline\field_agent\neighbors.c firmware\mid_baseline\field_agent\telemetry.c `
  firmware\mid_baseline\mid.c -o test_lrn1.exe ; .\test_lrn1.exe

# 固件构建（必须先按 environment.json 设置 IDF 环境变量，且用全新 -B 目录）
idf.py -B <新目录> -D SDKCONFIG=<新目录>\sdkconfig `
  -D SDKCONFIG_DEFAULTS=<repo>\firmware\mid_baseline\field_agent\idf\sdkconfig.defaults build

# 拓扑服务 / Studio
python -X utf8 -m tools.mid_baseline.gateway_probe.topology_server --udp-port 1680 --port 8780 --labels <labels.json>
python -X utf8 -m tools.mobile_gateway.launch_studio
```

---

## 十、接手后的第一件事

1. 按第四节恢复台子（板子 + 网关 + 两个服务）。
2. 确认 `reports=5`。
3. 执行 P0（烧 D 金丝雀），**不要**在未验证 LRN1 修复前推进 P1 之后的内容。
4. 每完成一项，更新 `docs/PROJECT_STATUS.md` 与任务卡，并在提交信息里写明证据路径。
