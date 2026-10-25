# Agent-Native Network

**Agent-Native Decentralized Wireless Networking for Collaborative Edge Intelligence**

面向自主推理边缘设备的去中心化无线网络研究。更新：2026-10-26。

本机多窗口协作从 [START_HERE.md](START_HERE.md) 进入：角色分工、任务卡、目录归属和新窗口交接见该入口。

## 当前研究问题

面向无人机、机器狗等具身设备组成的动态集群，研究规模、协作关系与数据负载增长怎样改变无线网络的实际服务，以及如何联合维护协作信息和调度任务消息，在相同资源下扩大有效协作的运行范围。救灾空地协作为当前应用入口。

已有工作提供问题依据与baseline。研究关注同一问题中的机制、算法、理论、性能和成本改进。首轮从状态更新与消息发送联合控制开展实验，保留MAC、PHY、路由及跨层优化空间。

## 阅读入口

| 内容 | 文档 |
|---|---|
| 当前全面分析：扩展性、内生网络服务、创新位置、模型和实验 | [可扩展性全面分析](research/agent_native_network/SCALABILITY_COMPREHENSIVE_ANALYSIS.md) |
| 首版完整科研链条与详细实施基础 | [科研与实验框架](research/agent_native_network/RESEARCH_EXPERIMENT_CHAIN.md) |
| 核心问题、文献依据、最小数学模型 | [研究问题分析](research/agent_native_network/RESEARCH_GAPS.md#scalability-core) |
| 立足点、baseline、优化层次与评价指标 | [首轮研究方案](research/agent_native_network/AGENT_COLLAB_BASELINES.md#first-study) |
| 新增综述涉及的7篇重点文献核查 | [文献补查表](research/agent_native_network/RELATED_WORK.md#survey-network-screen) |
| 任务调度方法与原始复现状态 | [任务baseline筛查](research/agent_native_network/TASK_SCHEDULING_SCREEN.md) |
| 下一阶段执行顺序 | [研究计划](research/agent_native_network/NEXT_STEPS.md) |
| 用户提供的综述原件 | [任务感知网络调度综述 PDF](任务感知网络调度_新版文献综述_论文原图版.pdf) |
| 文献表、证据规则与历史阶段导航 | [研究目录](research/agent_native_network/README.md) |
| 已有仿真代码与结果入口 | [simulation](simulation/README.md) |

## 当前进度

- 已完成[因果闭环与共享服务诊断](research/agent_native_network/CAUSAL_SERVICE_STAGE.md)：58任务回合、6固定回放，实际执行各节点缓存动作；10项因果测试和10项服务测试通过。识别初始并发分派/恢复失配，以及服务改变行动后增加维护负载两条机制。下一步先建立共同错相/恢复强对照，再比较更新与发送机制。
- 已完成[扩展性主线全面分析](research/agent_native_network/SCALABILITY_COMPREHENSIVE_ANALYSIS.md)：主目标为同资源下扩大达标运行域。005阶段的分析及S1接口结果保留，后续006实测见上述新报告。
- [HeteroMRTA通信接口](research/agent_native_network/HETEROMRTA_NETWORK_INTERFACE.md)：S1保留10实例、384决策点零延迟等价，以及延迟改变影子动作的诊断；E1-004另建上述因果执行入口，原结果不改写。
- [MOCHA原协议运行](research/agent_native_network/MOCHA_RUNTIME_ENTRY.md)：原状态机、SMACH与ZeroMQ双进程回环18项检查通过。阶段判断与下一实验入口见[M-004](coordination/reviews/M-004-interpretation.md)。
- [HeteroMRTA原权重与作者Greedy](research/agent_native_network/HETEROMRTA_REPRODUCTION.md)：9机器人、15/20任务各5种子，20次正常运行全部完成并返回驻地；另保留Greedy单行修改失败诊断。
- [MOCHA/AutoCast](research/agent_native_network/NETWORK_BASELINE_RUNTIME.md)：固定源码，14项原函数组件探针通过；完整ROS2/CARLA协议与任务运行尚待开展。
- 主文献表已登记38篇；新增综述的7篇定向核查及7组任务调度候选分别记录，尚未合并主表。
- 早期找矿、救灾回报与4节点通信实验保留原结果，详情见研究目录和证据日志。

研究记录按“原方法如何工作—表现和代价—机制限制—改进方法—对照结果”维护。原论文复现、机制适配和本项目新实验分别记录。
