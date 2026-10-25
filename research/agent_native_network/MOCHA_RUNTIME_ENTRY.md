# MOCHA 原同步协议最小运行记录

2026-10-25，D-004，起始提交 `7b6b09c23333609ee428cd45e4e24fc77a08fc24`。本轮运行了 **MOCHA 原同步状态机、原 SMACH 执行器及原 ZeroMQ TCP 收发路径的双进程回环**。第二次运行 18 项检查通过，两个进程及其状态机、服务端线程正常退出。ROS 适配部分明确隔离，ROS/DDS、无线接触与任务性能尚未验证。

入口：[mocha_runtime_probe.py](../../simulation/mocha_runtime_probe.py)。本轮只新增该入口与 D-004 证据，没有修改上游、旧组件探针、已有结果或环境。

## 固定源码与运行边界

| 部分 | 实际使用的版本/路径 | 执行范围 |
|---|---|---|
| MOCHA | [KumarRobotics/MOCHA，bfbde0d186d77278085b25a365bf735d5acdc6bd](https://github.com/KumarRobotics/MOCHA/tree/bfbde0d186d77278085b25a365bf735d5acdc6bd)；沿用 D-002 的 42 文件清单 | 完整导入 `hash_comm.py`、`database.py`、`database_utils.py`、`synchronize_channel.py`、`zmq_comm_node.py`，没有 AST 提取或修改函数体 |
| SMACH | [ros/executive_smach 3.0.3，f14c51a949519a6532125cc1fa5d026e07e210a0](https://github.com/ros/executive_smach/tree/f14c51a949519a6532125cc1fa5d026e07e210a0/smach) | 原 StateMachine、State、UserData、Remapper 等库；下载 12 个固定文件，共 80,836 字节。此处明确固定依赖版本，不声称等于作者全部历史实验的依赖 |
| 实际传输 | 系统 Python 3.11.5；pyzmq 26.0.3；libzmq 4.3.5 | 两个 Python 子进程，各有独立 DB；原 REQ/REP socket，客户端连接 `127.0.0.1`，端口写入配置。原服务端绑定 `tcp://*:port` 的行为保留，实验只使用本机客户端 |
| ROS 时间/日志/发布器 | 入口内的显式适配器 | 整数纳秒时间和比较；高分辨率 `perf_counter_ns`；本地 JSONL 日志。状态/完成/统计“发布”仅写日志，没有 DDS、ROS executor 或 ROS service |
| ROS 生成消息 | Time、SMState、ClientStats 的轻量字段容器 | 仅承载协议状态和诊断遥测；没有当作真实 ROS 消息传输 |
| CDR 与 LZ4 | 导入占位；一旦调用立即报错 | 本轮 payload 是预先给定的不透明字节；`serialize_message`、`deserialize_message`、`compress`、`decompress` 均未调用 |
| 触发与消费 | 显式调用原 `trigger_sync()`；检查接收 DB | RSSI/Rajant 触发、translator、database service、topic publisher 与任务执行器不在本次运行内；“已入接收 DB”不能替换为“任务已消费” |

每次正式运行前，父进程和子进程均验证 42 份 MOCHA 文件及 12 份 SMACH 文件的 SHA256/Git blob。子进程记录实际导入模块绝对路径。Python 使用 `-B`，不在上游树生成字节码。SMACH 的下载文件带原 BSD 许可头，固定清单与下载地址写入 `sources.json`。

`InstrumentedChannel` 只在原 client/server callback 前后追加日志并调用 `super()`；原状态执行、转换表、DB 过滤、打包、解包和 socket 均不被替代。父子进程 stdin/stdout 用于发起插入、触发、快照及停止命令；机器人之间的记录传递经过原 TCP 路径，没有通过该控制接口复制接收 DB。

## 已执行路径与结果

成功输出：[20261025-02](../../simulation/outputs/D-004/20261025-02/)。`result.json` 保存 18 项检查及前后快照，两个 `*_events.jsonl` 共 342 条事件保留状态转换、请求/回复、正文到达和入库。`config.json`、`environment.json`、`sources.json` 与脚本快照提供恢复依据。

第二次运行脚本 SHA256：`7b524d3555c56eeba28e292faf9299c6b3d1d28f855783ab2b121fb0c6f0af44`。实际运行 4.563 秒，配置总上限 45 秒；本轮最多 3 次、每次 60 秒的额度已使用 2 次，未使用第三次。

| 阶段 | 输入与预期 | 实际结果 |
|---|---|---|
| 首次同步 | A 有本地状态与 B 的旧缓存；B 同一 topic 有旧高优先级版本 `(ts=10, priority=3)`、新低优先级版本 `(20,1)`，另一 topic 为 `(15,2)` | 原 `GHEAD → GDATA → GDATA → DENDT` 完成。先请求另一 topic，再请求新版本；旧高优先级版本不请求。A 的旧缓存仍在历史 DB，最新视图变为收到的新记录 |
| 无变化重同步 | A 再次请求 B | 只有 `GHEAD → DENDT`；无 `GDATA`，A 的 DB 不变 |
| 更新后的同步 | B 增加 `ts=30` 的 `newest-state`，先检查 A，再触发 A | 触发前 A 仍是 `new-state`；随后原 `GHEAD → GDATA → DENDT`，正文到达并解包后 A 才得到新版本 |
| 反向同步 | 触发 B 请求 A | B 收到 A 的 `local-A`；双方最新视图一致。比较的是最新视图，历史记录集合不要求相同 |
| 对端退出 | 正常停止 B，再触发 A；客户端 timeout 为 0.4 秒 | A 从 RequestHash 超时回到 Idle；无新增完成通知、无 DB 改动。原状态层还有轮询等待，所以不会把 0.4 秒直接解释为整个同步失败时延 |

状态路径由原 `execute()` 产生：首轮依次经过 Idle、RequestHash、RequestHashReply、GetData、GetDataReply（两次正文）和 TransmissionEnd；无变化时跳过 GetData；失联时从 RequestHash 回 Idle。原文定位：`synchronize_channel.py:44–234,332–375,388–436,445–483`；原 DB 选择/入库在 `database.py:103–163,194–219`，打包/解包在 `database_utils.py:98–140`，实际 TCP 收发在 `zmq_comm_node.py:89–232`。

### 字节口径

以下是**服务端确实收到并返回回复的成功交换**，从原 callback 的 payload 长度加上原传输的 6 字节请求 ID 计算，逐事件可复核。它不是链路字节或空口成本。

| 阶段 | 请求类型 | 请求应用包字节 | 回复应用包字节 | 合计 |
|---|---|---:|---:|---:|
| 首次同步 | GHEAD、GDATA、GDATA、DENDT | 63 | 65 | 128 |
| 无变化重同步 | GHEAD、DENDT | 29 | 27 | 56 |
| 更新同步 | GHEAD、GDATA、DENDT | 46 | 47 | 93 |
| 反向同步 | GHEAD、GDATA、DENDT | 46 | 48 | 94 |
| 成功交换合计 | 12 个请求及其回复 | 184 | 187 | 371 |

对端退出后的 `GHEAD` 另有 11 字节提交到原 ZeroMQ `send()`，没有服务端接收/回复，因此不包含在上表。这个提交记录也不能证明该帧已离开本机 socket。表中没有 ZMTP/TCP/IP 头、连接建立、ACK、重传或无线开销；RTT 和原带宽统计仅保留为诊断，不报告为无线吞吐性能。

## 首次失败与收尾

[20261025-01](../../simulation/outputs/D-004/20261025-01/)保留首次运行的脚本快照、配置、异常栈和原始事件。已开始原 GHEAD/GDATA 交换，但适配器使用的 Windows `time.monotonic_ns()` 来自 `GetTickCount64()`，记录分辨率为 15.625 ms；短回环内 start/stop 相同使原 `zmq_comm_node.py:155` 带宽统计除零。此项定位为本次时钟适配选择问题，没有据此声称真实 ROS 环境存在同样故障。

修正只发生在新增适配器：改用 `QueryPerformanceCounter()` 支持的 `perf_counter_ns()`，本机记录分辨率 100 ns。第二次使用的上游文件哈希不变。

首轮运行 6.687 秒：A 的状态线程异常后，原服务端线程仍存活；父进程最终强制结束 A（PID 18548），B（9120）正常退出。第二轮 A（23060）和 B（40324）均 `exit_code=0`，无强制终止，日志中状态机和服务端线程均已停止。收尾后再次查询四个 PID，均不存在。没有后台运行或无线服务遗留。

## 恢复与下一步

新 clone 先按 [D-002 恢复说明](NETWORK_BASELINE_RUNTIME.md#已执行探针与恢复)从跟踪的 `simulation/results/2026-10-23-D-002-network-components/sources.json` 恢复 MOCHA 快照和其 `manifest.json`。该既有恢复入口会同时运行旧组件检查；它与下面的新协议运行是两种证据。

本机已存在 pyzmq；这次没有安装包。新环境应先确认 `python` 指向所需解释器、`import zmq` 可用，再执行：

```powershell
python -X utf8 -B simulation/mocha_runtime_probe.py --prepare-smach
python -X utf8 -B simulation/mocha_runtime_probe.py --output simulation/outputs/D-004/<new-run-id> --max-seconds 45
```

`--prepare-smach` 仅补齐固定源文件，并验证内嵌 Git blob；已有文件不匹配则失败。每次正式运行必须使用不存在的新输出目录，入口保存独立脚本快照和源码清单。子进程没有再派生子进程；父进程设置截止计时器，正常停止后等待退出，故障时终止其持有的子进程。运行只用本机回环，仍可能需要执行环境允许 socket。

完整 ROS2 恢复的明确阻碍是本机缺 `rclpy`、ROS 生成消息、DDS/ROS 运行时及 LZ4。原仓库 CI 使用 Humble/Jazzy、colcon、rosdep、SMACH、zmq、lz4；入口见固定提交的 [build.yaml](https://github.com/KumarRobotics/MOCHA/blob/bfbde0d186d77278085b25a365bf735d5acdc6bd/.github/workflows/build.yaml) 与 `mocha_core/test/test_synchronize_channel.py`。完整固定仓库还需消息定义与构建文件，不是 D-002 的 42 文件局部快照。在已有兼容 ROS2 工作区取得完整固定提交后，按原 CI 的 `colcon build`、`colcon test` 恢复，再运行原两节点同步测试；这条 ROS 恢复路径本机未执行，本轮没有安装系统软件或拉镜像。

本轮已提供 S1 的最小原协议同步入口。下一步可把完整请求/正文/结束事件映射到共同网络接口，保持实际入库时刻作为远端状态更新点；ROS topic 发布、序列化后真实消息大小、无线竞争和任务消费继续作为后续独立验收项。C 对本次原代码、两次结果与哈希进行只读独立审查，最终采纳/归档由 M 处理。
