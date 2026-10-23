# MOCHA / AutoCast 源码与通信接口实测

2026-10-23，D-002。工作分支 `codex/baseline-reproduction-20261023`，接手提交 `e724f7a557cf322280f252d394cb8533c8663fc7`。本轮固定作者源码，运行 14 项原函数组件探针，全部符合所列预期。任务完成率、空口吞吐和端到端协议性能尚未运行；下面的结果用于确定复现入口和公平比较的接口。

## 固定版本与运行入口

| 资料 | 固定版本 | 本机取得范围与原运行入口 |
|---|---|---|
| [MOCHA](https://github.com/KumarRobotics/MOCHA/tree/bfbde0d186d77278085b25a365bf735d5acdc6bd) | `bfbde0d186d77278085b25a365bf735d5acdc6bd` | 42 个源码/配置/说明文件。这是 ROS2 版本；`.github/workflows/build.yaml:17–40` 使用 Humble/Jazzy、colcon、smach、zmq、lz4。`mocha_launch/launch/jackal.launch.py:52–92` 启动数据库、翻译/发布节点和 Rajant 接口。完整运行还需 ROS 消息/服务生成与无线接口配置。 |
| [AutoCast](https://github.com/hangqiu/AutoCast/tree/5a69701081dcda9741106ad749270dc27b647ee9) | `5a69701081dcda9741106ad749270dc27b647ee9` | 14 个入口/说明文件。`README.md:30–49` 指定 Ubuntu20.04、CUDA11、Torch1.7.1、CARLA0.9.11、MinkowskiEngine、Mosquitto。原场景入口为 `run_carla.sh` 与 `run_test.sh`；场景运行器使用 AutoCastSim。 |
| [AutoCastSim](https://github.com/hangqiu/AutoCastSim/tree/10837c2a942e92312ea1a53697bc4513d9325454) | `10837c2a942e92312ea1a53697bc4513d9325454` | AutoCast 上述提交的 gitlink 固定版本，30 个 AVR Python/说明文件。调度在 `AVR/Sched.py`，通信在 `AVR/Comm.py`，场景接入在 `AVR/Collaborator.py`。未执行上游 README 的 `git submodule update --remote`，以保持版本一致。 |

下载文件在忽略目录 `data/network_baselines/<名称>/source/`。每个 `manifest.json` 记录 URL、SHA256、Git blob SHA1 和字节数；探针逐文件核对两种哈希。上游源码未修改、未复制到跟踪目录。MOCHA 根 LICENSE 为 BSD 3-Clause；AutoCast/AutoCastSim 固定树未见覆盖整个项目的根 LICENSE，AutoCast 仅发现第三方 mqtt-c 的许可文件。后续分发适配源码前需核实授权范围。

本机实测：Windows、Python3.11.5、NumPy1.26.4；原函数探针使用现有系统 Python，不占用 E1 环境。完整 ROS2/CARLA/MQTT 场景没有启动，也没有安装其依赖。下载经过授权的网络执行；首次受限执行报 WinError10013 后未产生来源文件，提升网络权限后取得快照。

## MOCHA：更新、同步与消费

以下路径相对 MOCHA 固定源码根目录，可从上表提交链接核对。

| 接口 | 代码与行为 | 接入共同网络时的处理 |
|---|---|---|
| 本地状态产生 | `mocha_core/mocha_core/translator.py:60–82` 在本地 topic 回调中序列化、打时间戳并调用数据库服务。 | 本地观测立即可得；远端观测必须从实际收到的正文建立。 |
| 同步触发 | `mocha.py:150–161,182–191` 用 RSSI 阈值触发；`synchronize_channel.py:432–436` 设置同步标志。源码也允许以其他触发器替换 RSSI 回调。 | 接触、定时和任务触发分别配置，不能把应用发布频率当作网络同步频率。 |
| 头部与优先级 | `hash_comm.py:6,57–102` 的 TsHeader 为6字节：机器人ID、topic ID各1字节，秒与毫秒各2字节。`database.py:121–163` 先逐机器人/topic选最新，再按优先级、时间、头部降序排序。 | 头部也占空口。1字节ID、毫秒精度及秒字段回绕是当前编码边界，扩规模时需显式配置/检查。 |
| 请求与队列 | `synchronize_channel.py:109–122,140–162,445–470` 返回最新头列表、过滤本地已有版本、按排序逐条请求正文；每步有客户端超时。`zmq_comm_node.py:104–139,181–198` 为 ZeroMQ REQ/REP over TCP。 | 分列头列表、正文请求、正文、结束报文与底层重传成本；一次头部出现不代表正文已交付。 |
| 消费可见性 | `synchronize_channel.py:184–190` 收到正文后解包、入库；`topic_publisher.py:61–93,190–196` 由头部通知取数据库正文，再发布 ROS topic。 | 任务执行器读接收端已发布缓存。可靠任务事件需要独立保留语义，不能直接照搬 LAST_MESSAGE。 |

示例配置 `mocha_core/config/topic_configs.yaml:1–27` 已区分 HIGH/MEDIUM/NO_PRIORITY，并使用 LAST_MESSAGE。当前组件探针验证了最新选择优先于历史高优先级：输入同topic旧记录 `(prio=9,ts=10)` 与新记录 `(prio=1,ts=20)`，列表保留新记录；其他topic的 `(prio=5,ts=15)` 排在其前。这个行为可作为统一任务状态缓存的强基础对照。

## AutoCast：论文机制、默认代码与实际可见性

论文的接收者相关性、分布式发送计划和控制信息外推继续按 [RELATED_WORK](RELATED_WORK.md#survey-network-screen) 记录。以下结论来自固定 AutoCastSim 快照；后续复现应分别记录默认配置与分布式配置。

| 项目 | 固定代码行为与定位 |
|---|---|
| 默认模式 | `AVR/__init__.py:28–30`：`EmulationMode=False`、`DistributedMode=False`。`Collaborator.py:320–342` 默认读 `agent_wrapper` 的共享 beacon 列表；分布式模式读本节点控制缓存，且仅接受 `FrameId` 等于当前帧的消息。 |
| 更新入口 | `Collaborator.py:180–240,540–581` 在回调流程构建并发送 beacon，同时写共享 beacon 列表。`BeaconList.py:15–36` 的 `tick` 将本帧列表切换成消费缓存。 |
| 控制内容 | `Comm.py:24–50` 的 Beacon 包含位姿、尺寸、速度、检测对象列表、大小和触发标记；`DetectedObject.py:23–34` 的 `get_obj_for_comm` 直接赋入 `point_cloud_list`。按 `Comm.py:179–182` 的 JSON 表达式序列化时，这些点也进入控制负载。应测真实字节，不能按“仅元数据”估计。 |
| 原排序器 | `Sched.py:218–255` 的 `mckp_greedy_scheduling_algorithm` 对正收益对象按收益/点数排序，加入与ID有关的小扰动破同分。零大小对象保留但指标置0。收益由接收者遮挡关系累计，`Sched.py:85–155` 还使用 hero actor 作为簇中心。 |
| 补偿/外推配置 | `Sched.py:163–174` 的公平补偿、`Collaborator.py:294–315` 的相关函数处于注释状态；`AVR/__init__.py:93` 默认 `Extrapolation=False`。因此不能仅凭论文机制认定该默认配置已启用这些功能。 |
| 队列与传送 | `Comm.py:151–165,179–185,226–247,288–292` 用 MQTT QoS2、接收队列、距离检查和接收缓存。`Collaborator.py:613–632` 在默认非仿真无线模式下直接向各协作者 DataChannel 缓存写数据；该路径绕过 `Comm.processMsgs` 的距离检查。 |
| 缓存与消费 | `Comm.py:83–97` 对 Beacon 直接替换，不比较帧号；对 Data 丢旧帧、同帧合并。`Collaborator.py:645–655` 消费端还要求 peer 出现在控制列表，并检查数据帧龄。默认共享控制列表与直接缓存写入不能作为“消息经过竞争无线链路”的证据。 |
| 预算边界 | `Collaborator.py:516–533` 发送/计入对象后才检查累计时间是否达到100ms。`AVR/__init__.py:269–270` 按点数×3×8×8/速率估计时间，未在这条式子中加入 JSON、控制和链路开销。 |

原代码的有界诊断结果：3个对象各2250点，速率7.2Mbps，单对象原公式为60ms。`TX_Data` 先安排第1个（起点0ms），再安排第2个（起点60ms），随后退出，返回索引1；累计120ms。这个结果说明调度循环允许最后对象越过100ms边界；它不测实际无线传输时间。

Beacon点数诊断：相同其他字段、每点 `[1.0,2.0,3.0]`，10点序列化为653字节，1000点为17483字节，增加16830字节。原函数还确认：先收到Frame12后再收到Frame11的Beacon时，缓存回退为11；Data同样输入会保留12。Beacon回退是LockBuffer条件行为，默认共享beacon路径是否实际遇到此乱序尚未验证。这些是具体输入下的组件行为，下一步可据此设置乱序与控制成本实验。

## 已执行探针与恢复

入口：[network_baseline_probe.py](../../simulation/network_baseline_probe.py)。输出：`simulation/outputs/D-002/20261023-03/` 中的 `probe_results.json`、`sources.json`；早期12项版本保留于 `20261023-01/`；14项首次记录在 `20261023-02/`，最终03增加脚本SHA256、Python可执行文件和NumPy路径。最终14项包括MOCHA头部往返/非法长度、最新与机器人筛选，以及AutoCast收益排序/破同分/零大小、Beacon乱序、Data旧帧与合并、控制载荷、帧切换、100ms边界。

脚本按 AST 提取原始函数/类节点，不改函数体，原文件哈希在每次执行前验证。替代依赖只有报告逐项列出的测试夹具：MOCHA查询用整数时间戳和返回0的epoch工厂；AutoCast用简单消息/速度对象；TX回调只记录起点并返回原时间公式。ROS Time转换、ROS服务、MQTT收发、遮挡收益构造、CARLA驾驶和无线竞争未执行。`probe_results.json` 保存每个节点的源行号、输入、预期和实际输出，并记录脚本SHA256与依赖路径。

本次命令（第二个命令也验证已存在文件的恢复/哈希路径，不重新下载）：

```powershell
python simulation/network_baseline_probe.py --source-root data/network_baselines --output simulation/outputs/D-002/20261023-01
python simulation/network_baseline_probe.py --source-root data/network_baselines --fetch-manifest simulation/outputs/D-002/20261023-01/sources.json --output simulation/outputs/D-002/20261023-02
```

新clone恢复时，先使用M验收归档的 `sources.json`，将其路径传给 `--fetch-manifest`；脚本仅从固定仓库/提交的raw URL补下载缺失文件，并在写入前核验SHA256和Git blob，不覆盖已有不匹配文件。输出目录必须全新。下载清单用于组件复核，完整ROS/CARLA运行需另外取得整个固定仓库。

## 下一阶段可以直接执行的工作

1. MOCHA先在ROS2环境运行原数据库/同步测试，再以两个节点记录请求、正文入库和topic发布时间；建立头部/正文/控制开销与任务可见状态的对应关系。
2. AutoCast先固定默认场景完成原驾驶评估；分开记录 `DistributedMode` 和 `EmulationMode`，把实际控制内容、预算末项和数据缓存路径写入配置。需要严格预算时保留原行为对照，修正版本另名记录。
3. 共同网络接口用 `on_local_update → enqueue_control_or_data → on_delivered → publish_remote_cache`；同一任务策略只读送达缓存。控制与数据进入共同服务预算，逐消息记录产生、入队、发送、到达、消费时间与字节数。先做小规模/信息延迟归因，再做节点数和动态强度变化。

最终记录另存于 `simulation/outputs/D-002/20261023-03/`。验收后归档入口：`simulation/results/2026-10-23-D-002-network-components/`；新clone可用该目录的 `sources.json` 配合 `--fetch-manifest` 恢复。

进程已结束，无后台队列。D-002交C复核后由M决定采纳和提交；本报告未据组件结果宣称系统性能改进。
