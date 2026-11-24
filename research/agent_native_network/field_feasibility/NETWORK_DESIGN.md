# D-045 网络内核：抽象模型与接口

状态：可供 E1-035 合成联调。仅抽象、可复现的离散事件直连网络；不是实机链路、MAC 规范、空口干扰模型、无线测量或多跳路由。文件 `simulation/field_feasibility/network.py` 不读取场数据，场景 RF RSSI 绝不输入链路。

## 接口与时间契约

```python
from simulation.field_feasibility.network import Network, NetworkConfig, serialize_message
net = Network(NetworkConfig(range_m=100, bandwidth_bps=1_000_000,
                            propagation_delay_s=0.05, loss_probability=0.0,
                            distance_loss_probability=0.0,
                            max_queue_delay_s=None), seed=123)
net.update(0, {1: (0, 0, 10), 2: (50, 0, 10)})
mid = net.send(0, 1, "TASK_INTENT",
               {"region_id": "cell-7", "utility": 0.4, "eta": 12}, 2)
assert net.poll(2, 0) == []
received = net.poll(2, 1.0)   # 只有真实交付的消息；读取会消费该节点信箱
metrics = net.metrics(1.0)
topology = net.topology()     # positions/online/edges/degree/connected，可用于绘图
```

- `Network(config=None, seed=0)`：`config` 为 `NetworkConfig` 或同字段字典。随机数为独立 `random.Random(seed)`，不能共用采样噪声流。参数是实验抽象值，不是设备实测。`range_m`、`bandwidth_bps` 均正；基础时延非负；丢包率各在 [0,1]；队列等待期限可为空。
- `update(t, positions, online=None)`：全量 `{node_id: (x_m,y_m,h_m)}`，node ID 为整数或非空字符串；首次固定节点全集，后续不删节点，用全量 `{node_id: bool}` 标记离线；`online=None` 表示全部在线。状态在下一次 update 前零阶保持。先结算严格早于 `t` 的事件，再应用新拓扑并处理恰好等于 `t` 的事件。
- `send(t, source, kind, payload, destination=None)`：单播目的为其他已登记节点；`None` 为广播，收件候选是入队瞬间的直接在线邻居快照。无邻居广播是 1 个接受排队帧、0 个收件机会。返回帧 ID；排队等待超过 `max_queue_delay_s` 返回 `None`，单列拒绝数。`send` 不等于送达，源或目的不在线也不代表创建成功后的送达。
- `drain(t)`：推进到 `t`，返回自上次 drain 起已经完成的逐目的 `delivered`/`dropped` 结果；中间由 `update`、`poll`、`metrics` 推进产生的结果不会丢失。它是评价日志，不应作为节点共享全局信息。`poll(node,t)` 才是各节点可消费的真实送达收件箱，返回 `message_id/source/destination/kind/broadcast/created_at/completed_at/latency_s/bytes/status/reason/payload`，同一节点读取后移除；不访问其他节点信箱。所有方法的时间必须有限且不倒退；同一时刻可以多次调用。
- E1 的 `mission.py` 暂用 `transport.send(now, positions, outgoing)` 封装契约，与这里的单包 API 不同，需由 E1 在自身范围写 adapter：每个时刻先 `update`、逐节点 `poll`，本地决策后逐包调用 `send`；不得用 `drain` 结果代替节点投递。入队的 `SAMPLE` 为已采事实，`TASK_INTENT` 需用实际目标及评分/ETA 映射到下述字段，禁止构造虚假的观测或未来场值。没有及时到达则保留本机策略与无消息反事实。

## 编码与消息

`serialize_message(source, destination, kind, payload, created_at, message_id)` 将完整信封（id、source、destination、kind、created_at、payload）排序键、紧凑 JSON、UTF-8 编码，`bytes = len(wire)`；广播只有一份无线帧，但每个目标各有接收机会。使用真实内容与 UTF-8 字节，不用常量估计；该格式为本模拟的软件字节数，不含物理层前导、帧校验或 MAC/重传开销。额外字段若能被 JSON 序列化可保留；禁止 NaN/无穷和非 JSON 对象。

| kind | payload 必填键 | 说明 |
|---|---|---|
| NODE_STATE | node_id, position, velocity, timestamp | 位置/速度及采样时间，单位由任务统一 m、m/s、模拟秒 |
| MAP_SUMMARY | region_id, mean, variance, sample_count | 实际本地推断所得，方差不是实测信道可靠性 |
| TASK_INTENT | region_id, utility, eta | 本机可行候选、价值及 ETA；可附上过期时间等 |
| TASK_UPDATE | region_id, owner, status, expires_at | 归属、状态、过期；到期的忽略/冲突消解由上层策略负责 |
| SAMPLE | sample_id, node_id, step, x_m, y_m, h_m, t_s, value_dbm | 为 B/D 传实测值或观测回放准备的附加类型；只允许当前已采样值 |

内核只检查必需键及可编码性，语义、单位、有效期、节点身份和上层去重由调用方检查。消息构造完成后复制，修改调用方 payload 不会更改在途包。

## 模型、统计与限制

- 几何无向图：在线节点欧氏距离 `<= range_m` 为结构邻居；未建模障碍、天线方向、不同传播条件或独立频道。图随 `update` 变化，不会把真实轨迹间隙中的运动线性插值，调用方要以足够细的模拟步长更新位置。
- 全网一个 FIFO、无碰撞的共享串行媒质近似竞争/有限带宽：帧耗时 `8 × 编码字节/bandwidth_bps`，再加常数传播延迟。源离线、排队至发送时断链、期间断链（即使到达前恢复）或按距离计算的随机丢包都会失败。广播向每个目标独立抽签；`min(1, loss_probability + distance_loss_probability × distance/range_m)` 不是经测量验证的物理规律。无多跳、拥塞退避、重传、确认、捕获效应和真实干扰。发生多个链路变化时必须按实际模拟时间调用 update；相同时间处理顺序以接口契约为准。
- `metrics(t)` 含 `total`、`by_class`（unicast/broadcast）、`by_node`、`connectivity_ratio`、`partition_duration_s`、`average_node_degree` 和 observation_duration。接收机会=接受入队的各收件目的数；完成成功=该目的的真实收件；完成失败=不可达/中途断链/随机丢包；在途另计 pending；PDR=`delivered/(delivered+dropped)`，只对已决机会计数，未完成不能当作丢包，最终截止时需同时报告 pending。队列拒绝帧及其目标数单列，不进入 PDR；要比较端到端提交成功需把拒绝和 pending 作为独立结果报告。无已决机会 PDR=null，无实际收件平均时延=null。时延含队列、帧传输和传播，只有已送达才计。
- `enqueued_frames/bytes` 是入队数和字节；`tx_frames/bytes` 是已开始发射的帧与字节（源离线不能计发射）。广播发射字节只记一次，`rx_bytes` 对实际送达的每个目的累加。节点指标的发射、PDR按 source，`received_messages/bytes` 按 receiver。纯抽象字节不等于真实空口成本。
- 结构连通率按时间积分，要求**全部登记节点**在线且同属一个分量；单节点在线时连通，节点离线计入网络分区。分区时间为总体不全连通时长；平均度是所有登记节点（离线度为 0）的时间均值。首次 update 前不计，零观察时间连通率及平均度=null。网络可结构连通而实际传输失败，两者分别报告。
- E1 应保留每次消息收件机会/完成状态、已到达时间及本机决策日志，避免只报告聚合 PDR；有未到期在途消息时统计不等于最终交付率。间断网络不保证过期包有效，调用者需用各自任务有效期过滤。

## 验证边界

`python -X utf8 -B -m unittest simulation.field_feasibility.test_network -v` 使用合成位置、消息和时间；检查四类必需格式及 SAMPLE、实际送达/信箱隔离、广播分母、字节编码、排队/限额拒绝、距离断链、离线/重连、在途断开再恢复、相同时间更新、连通时间积分、随机流复现、无消息 N/A。结果仅说明代码在所列测试条件下满足离散事件契约，不说明真实无线质量、任务收益或 V2 数据可用。E2-044 正在下载/审计 V2，确认 `data_ready.json` 之前不做场数据试验。


## C-051-01 修复及历史运行版本（2026-11-24）

等待发送的帧到达发送时刻而源节点离线时，不占媒质；后续已入队帧按 FIFO 在已使用媒质之后重新排程，旧预约事件以 generation 失效。已经依据当时已知排队长度拒绝的帧不事后恢复；取消后的新提交按释放时隙判断。切换后网络源码 SHA-256 `f7cf9b3b1b33307415c78f24cc2e20fe22fffbb26675b1c2462d109916c60741`，合成 18 项测试证据在 `simulation/outputs/D-045/20261124-06-network-switched/`。

E1-035 四档正式主运行与 E2-045 四高度等预算正式运行均已完成，各自运行清单保存的网络源码 SHA-256 为历史冻结版 `23ffdc6bc3d4bef88e5dea01c9f4818f5e6ffb7e1dfe829f05283a5dc48323fc`，不是修复候选。E1 主运行的已保存拓扑和 outcome 经 C 核查均未触发 `source_offline`；E2 等预算运行源码中未传节点离线计划，依其运行路径各节点亦保持在线。两批的距离断链/随机丢包并非发端离线，不等于验证了离线故障恢复。旧运行数据和源码快照保留，未用新内核重跑。
