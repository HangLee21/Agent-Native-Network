# Agent-Native Network

**Agent-Native Decentralized Wireless Networking for Collaborative Edge Intelligence**

面向自主推理边缘设备的去中心化无线网络研究。更新：2026-10-23。

## 当前研究问题

面向无人机、机器狗等具身设备组成的动态集群，研究协作状态维护与任务消息传输如何共享有限无线资源，使团队扩展仍能保持有效协作。救灾空地协作为当前应用入口。

已有工作提供问题依据与baseline。研究关注同一问题中的机制、算法、理论、性能和成本改进。首轮从状态更新与消息发送联合控制开展实验，保留MAC、PHY、路由及跨层优化空间。

## 阅读入口

| 内容 | 文档 |
|---|---|
| 核心问题、文献依据、最小数学模型 | [研究问题分析](research/agent_native_network/RESEARCH_GAPS.md#scalability-core) |
| 立足点、baseline、优化层次与评价指标 | [首轮研究方案](research/agent_native_network/AGENT_COLLAB_BASELINES.md#first-study) |
| 新增综述涉及的7篇重点文献核查 | [文献补查表](research/agent_native_network/RELATED_WORK.md#survey-network-screen) |
| 任务调度方法与原始复现状态 | [任务baseline筛查](research/agent_native_network/TASK_SCHEDULING_SCREEN.md) |
| 下一阶段执行顺序 | [研究计划](research/agent_native_network/NEXT_STEPS.md) |
| 用户提供的综述原件 | [任务感知网络调度综述 PDF](任务感知网络调度_新版文献综述_论文原图版.pdf) |
| 文献表、证据规则与历史阶段导航 | [研究目录](research/agent_native_network/README.md) |
| 已有仿真代码与结果入口 | [simulation](simulation/README.md) |

## 当前进度

- 已完成核心问题分析、网络baseline分工和评价口径；新方案处于建模与复现准备阶段。
- HeteroMRTA已固定源码、审计观测构造并通过环境初始化；预训练策略评估待开展。
- MOCHA作为直接通信协议对照，AutoCast作为任务价值发送对照；任务执行器与通信机制分别比较。
- 主文献表已登记38篇；新增综述的7篇定向核查及7组任务调度候选分别记录，尚未合并主表。
- 早期找矿、救灾回报与4节点通信实验保留原结果，详情见研究目录和证据日志。

研究记录按“原方法如何工作—表现和代价—机制限制—改进方法—对照结果”维护。原论文复现、机制适配和本项目新实验分别记录。
