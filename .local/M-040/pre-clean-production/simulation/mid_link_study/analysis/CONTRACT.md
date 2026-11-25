# M-021最小事件/指标合同（E2，v1）

所有输出 evidence_kind=software_simulation，不使用真实RF/串口/boot字样冒充测量。按M-021固定3场景×5种子×fixed/adaptive两臂、每场60模拟秒，A→B/B→A各2pps、32B，240源计划/场。E1/H实际字段名可做薄映射，不因命名重跑已运行数据；映射必须记录路径/原始行。

## 每场来源

context/manifest至少含run_id、pair_id=(scenario_id,seed)、arm、scenario版本/path/hash、engine与planner版本/hash、seed、起止模拟秒、业务生成计划、初表hash、延迟/信道/容量/排队/TTL/控制传播模型及单位。配对两臂相同外生计划/初表/观察时序规则/信道随机数索引；允许策略导致不同路径，不能按调用顺序抽随机数。主机求解墙时、模拟计算延迟和缓存命中分列，不互相替代。缺项标unknown不猜填。

## 逐包事件

JSONL或JSON数组均可，至少t_s（模拟时间）、event、run_id。源generate/created记录packet_id（同pair两臂相同）、src、dst、seq或slot、payload_bytes=32；推荐payload_tag。identity为(run_id,src,dst,packet_id)，配对对齐去掉run_id后按src/dst/packet_id；模拟身份不能当设备boot。

最小链为generate、tx_attempt/forward（node,next_hop,route_version，若建模链路抽样给draw/key/probability/outcome）、rx/relay、destination_rx（node==dst、同身份及payload_tag若跟踪内容）；drop/expire/queue_drop保留原因、pending保持未决。最终delivery仅取目的事件，不用源send/链路成功或计划路径代替。TTL、队列/服务速率和失败处理必须声明，不能在分析器补模拟机制。

控制事件记录observed_state/detection/replan_request/solve_start/solve_end/config_publish/control_tx/control_rx/config_install，给update_id/version/node及父更新引用。未建模项显式null。安装时刻由实际模拟事件给，不能把publish等同于全体install。控制字节注明应用载荷或按边发送层级；未模拟空口不报PHY airtime。

## 图真值与解释

H给独立真值接口或时间段图：每条有向边(t_begin,t_end,src,dst,service_bps,p_success,available等实际参数)。正服务率且正成功概率为乐观可达边，退出节点不得通行。真值只供事后分析，不输入策略。按方向计算A→B/B→A可达区间及见证路径，分区阴影不能把有向图误画成双向断连。

分别给包生成时、尝试时、终止时的快照可达性；交叉统计原始失败原因、所用表版本/安装时刻。存在路径不代表容量/概率足够，也不能把“有路但丢包”都称旧路由。完全无静态路径的时段只称快照分区，除非模型另证无时变路径，不推任何存储转发算法都不可能交付。旧版本/断边下一跳只是暴露证据，因果收益由同输入配对结果支持，不从单包反推。

## 指标固定

每场按源计划保留全部240身份；计划、生成、尝试、目的唯一收到、重复、未决、明确丢弃分列。目的首收落[0,60)的每秒[second,second+1)窗给unique_delivered、payload_bits/goodput_bps；零窗保留，事件缺失/运行中断为null，晚于60另列，不塞最后一秒。每秒亦给生成数、尝试数、队列丢弃/TTL、控制发布/安装/字节（仅确有模型时）。

恢复：事前10个完整1秒窗平均吞吐，阈值80%，干预后连续3个完整窗达标，确认时刻为第3窗末；无下降记no_interruption，基线0/不足窗不可评价，未恢复right_censored，中断覆盖unknown。H/context显式给impact_start_s和recovery_anchor_s：渐弱/退出默认从干预生效；完全分区主要从实际图重连时刻计算，同时保留从分区开始的总经历时间，不混不可达时段与路由恢复。未给锚点则unknown，不看结果选有利起点。

配对逐场列出两臂、同条件匹配状态、交付差值、事后有效载荷面积差、恢复状态/删失、控制发布/安装/字节差。5个预定种子全部展示，给中位/IQR/min/max，不删除无优势/失败/不可行样本，不把删失恢复时间当观测均值。不从软件仿真外推实板性能。

## D交付

E2输出DATASET.json及每场packets/seconds/annotations/topology_truth/directions、配对pairs与场景summary，路径/hash/映射/限制随数据。第一对就可交D出可打开回放，之后追加批次，不覆盖首对。实际模拟forward轨迹与计划权重分开；可达性真值阴影、每节点安装时刻、两臂吞吐叠图和每条运行来源可直接取数。

本卡只离线读取H/E1新结果，核身份/模型及因果边界；不运行E1整批、不占设备或重跑M-019/020，不后台轮询。

H-008 v1接入：IDS=gradual_link/relay_exit/partition_restore，seeds=11/23/37/53/71；调用scenarios.load/state_at只在分析端。impact_start_s统一20；gradual_link/relay_exit的recovery_anchor_s=20，partition_restore的recovery_anchor_s=40。恢复只在确实出现首次低阈窗后找连续3个达标窗，避免渐弱开始后暂时仍稳定就提前宣布恢复。图半秒快照与输入来源供D先接在E2-019/20261107-03-topology-interface/topology.json，明确environment_truth_only，尚不含E1逐包实验结果。
