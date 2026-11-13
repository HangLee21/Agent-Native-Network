# 现场观测网关

在仓库根目录执行：

```powershell
python -X utf8 -m tools.mobile_gateway.live --open
```

也可以双击同目录的 `START_LIVE_GATEWAY.cmd`。Linux 用 `sh deploy/mobile_gateway/START_LIVE_GATEWAY.sh`。默认地址为 <http://127.0.0.1:8790/>，终端会打印实际地址和本轮日志目录；按 Ctrl+C 停止。默认首次启动为空图，实际报告到了才出现节点。它不枚举串口，不启动无线，也不填固定身份、数量、位置或路线。

需要 Python 3.11 或更高版本和本仓库代码。网关及 HTTP 报告程序使用标准库；已有串口所有者使用项目原来的 pyserial 环境。每次运行生成新的 `simulation/outputs/H-016/live-.../`，已有目录不覆盖。8790 已占用时启动失败并保留原服务，可换 `--port 8791`；`--port 0` 会选择临时端口。

## 接入现场节点

每台车保留自己的 Edge 串口所有者。在该车或 Pi 上单独运行报告程序：

```sh
python3 -m tools.mobile_node node --edge-port 8780 --gateway http://PC_IP:8790 --state /tmp/mobile-node-NEW --gps none
```

`PC_IP` 换成网关电脑在同一局域网的 IPv4 地址。`--gps none` 将定位留空；有 GPS 时按 [节点说明](../mobile_node/README.md) 选择 gpsd 或外部提供器。需要演示假定位时显式加 `--gps fake`，页面始终标为模拟。定位不决定无线连接。

同一电脑已经有本地 Edge 服务时，也可在网关命令后加入 `--attach-edge 8780`，可重复指定任意多个本地端口。它只连接已有服务，不启动第二个串口所有者；身份由服务实时返回。默认定位未知，附加 `--gps fake` 才生成模拟位置。停止这个便捷入口会关闭它启动的报告进程，已有 Edge 和板上无线继续运行。

随机业务由每台车独立启动，和观测网关分开停止：

```sh
python3 -m tools.mobile_node agent --edge-port 8780 --state /tmp/mobile-agent-NEW --interval-min 2 --interval-max 5
```

默认从本板实际邻居中选择其他目的；可重复加 `--dest MAC` 指定目的候选。每轮重新随机等待、选择目的和生成可读英文，字节数不超过160；目的应用持续接收。失败或交付未知不会重发原包。网关没有业务发送、路径安装或载荷转发接口。要限时检查，可给 node/agent 加 `--duration 30`，正式现场默认持续运行到主动停止。

H 的 `owned_edge`、`probe_bound` 和 `capture_real` 是带身份与租约检查的硬件验收工具，供已获硬件操作授权的 H 使用。现场默认入口不调用这些工具。串口换号必须重新核实际 MAC，不能照抄历史 COM 号。

## 局域网和热点

网关电脑执行 `python -m tools.mobile_gateway.live --host 0.0.0.0 --port 8790`，其他设备打开 `http://PC_IP:8790/`，节点向同一地址上报。电脑与 Pi 可用现成普通局域网；如果使用 Windows 移动热点，先由用户开启并让 Pi 接入，再确认双方能访问这个地址。需要允许该网络访问网关的 TCP 端口。

热点承载普通 IP 遥测。ESP32 板间业务继续使用 ESP-NOW；Windows 无线网卡不承担 ESP-NOW 收发。M 的系统检查只确认热点能力可用，本轮没有开启热点，也没有验证 Pi 接入、局域网距离或真实 GPS。

## 数据接口

| 方法与路径 | 用途 |
| --- | --- |
| `POST /api/v1/reports` | M-030 JSON v1 节点报告，最大262144字节 |
| `GET /api/v1/state` | 当前报告节点、有向观测和年龄 |
| `GET /api/v1/timeline?after=CURSOR` | 最多8192条保留事件，含游标和截断标志 |
| `GET /health` | 实例标识和 observation_only 角色 |

`node_id` 是报告板的规范小写 MAC，`boot_id` 是板启动 ID，`session_id` 是报告进程实例，`seq` 在该实例内递增。网关按到达时间记录；同实例重复/乱序报告不刷新当前快照，已知退役会话不能覆盖新会话。同 session 改 boot 被拒绝。陌生 session 首次到达视为新会话；没有额外可信进程世代信息时，无法判断从未见过的 session 是否比当前会话更旧。每板最多保留256个退役会话，超出后拒绝新增会话并要求另开采集。

`report_age_ms` 表示客户端队列中已有年龄，叠加到位置、邻居和报告年龄；重连不会把旧缓存变成新测量。不使用不同设备的单调时钟相减。RSSI 是 `peer_id → 报告节点` 的接收样本。没有 RSSI 保留 null/unavailable；单向确认、双向互证、无线 lost 和报告 offline 分别保留。默认报告超过30秒标失联，测量超过30秒标过期，可用底层网关参数 `--offline-ms`、`--stale-ms` 调整。

根目录静态文件来自 `research/agent_native_network/mobile_gateway/`，可用底层网关 `--static-dir` 指定其他目录。页面同源读取状态和时间线，现场页自动持续观测，暂停或离开页面后释放读取。无定位节点单列。沿途提交不算目的交付，目的收件保留原始身份与字节。`reports.jsonl` 仅保存实际接受的报告，原始信息保留；`--resume` 只用于恢复同一网关采集目录，保持原到达时间。默认现场命令不恢复历史，启动为空。

## 本机实际结果

`20261109-08-real-live-capture` 实际接入4块正在自主模式运行的 ESP32，运行四个独立串口所有者、四个报告进程和四个随机业务进程。没有刷写、复位或配置无线。GPIO/GPS 没有实测；这轮显式使用模拟 GPS，旧固件不提供 RSSI，页面留空。

随机业务104条接纳中，103条在目的板 UART 找到同原身份及字节，100条同时出现在独立目的应用日志；1条交付未确认，3条只有 UART 证据。另有1条67字节新业务在网关进程退出后输入，目的应用在网关恢复前收到相同字节。停网关约16.8秒内，随机业务仍有22次新发送尝试、23条应用收件。原始日志、逐包核对、浏览器前后截图和结果在H-016对应新目录；不能把应用接纳当交付。

本轮为一台 Windows 电脑连接四块真实 RF 板。第五个设备只在邻居报告出现，其 USB 口有驱动错误，未作为报告端。结束时所有本轮进程/串口关闭、租约释放，四板原有 boot/build/group/无线 active 状态保留。节点上游文件在采集期间有更新，输入 hash 和原始日志保留；这轮不是完整冻结源码的复现实验。真实 Pi、GPS、RSSI、热点和自然 RF 隔断尚未验证。

## 隔离开发夹具

显式执行 `python -m tools.mobile_gateway.demo --port 0 --duration 70` 才运行固定接入顺序和故障剧情。它使用 E2 的真实软件模块，传输则是独立进程中的 host_model/BFS，GPS 和无线质量均标模拟。它不连接板子，不作为现场默认入口。`analyze_demo` 与 `analyze_real` 只读原始记录并写新的分析目录，不重发业务。
