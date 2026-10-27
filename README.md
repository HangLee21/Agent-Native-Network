# Agent-Native Network

**Scalable and Adaptive Networking for Distributed Embodied Edge Intelligence**

面向分布式具身边缘智能的动态可扩展无线网络。更新：2026-10-27。

本机多窗口协作从[START_HERE](START_HERE.md)进入；实际执行范围与验收以[CURRENT](coordination/CURRENT.md)和主任务卡为准。

## 当前研究方向

研究具备独立端侧推理能力的设备，如何通过移动、多跳、局部连接和间歇连接无线网络持续协作。模型根据收到的证据产生、追加、改选或终止信息请求；网络发现、路由、竞争排队和分区重构影响证据服务，反过来改变后续推理需求。研究主体是网络系统，核心评价是同资源下的服务连续性、有效goodput、控制成本与达标运行域。

当前以[研究方向修订总报告](research/agent_native_network/RESEARCH_REORIENTATION_20261027.md)为研究总入口。同步/版本恢复保留为控制面模块，HeteroMRTA保留为传统业务和功能回归；近期同时准备真实模型负载与成熟动态无线验证，再选择具体机制。接口和双图用于表达与执行，贡献由可实现机制及同条件结果建立。

## 当前阅读入口

| 内容 | 文档 |
|---|---|
| 偏差根因、五个问题、完整框架、三个候选及近期优先级 | [方向修订总报告](research/agent_native_network/RESEARCH_REORIENTATION_20261027.md) |
| 12篇核心资料：部署、动态性、规模、控制深度及强机制 | [近期文献核查](research/agent_native_network/reorientation_20261027/LITERATURE_REVIEW.md) |
| 动态图、请求接口、队列/干扰与跨层控制权限 | [架构与模型](research/agent_native_network/reorientation_20261027/ARCHITECTURE_AND_MODEL.md) |
| A真实模型、B动态无线、C机制归因的有限实验方案 | [验证计划](research/agent_native_network/reorientation_20261027/VALIDATION_PLAN.md) |
| 唯一当前推进顺序与历史计划定位 | [NEXT_STEPS](research/agent_native_network/NEXT_STEPS.md) |
| 研究文档和历史证据目录 | [研究目录](research/agent_native_network/README.md) |

## 证据状态与历史成果

本次交付为文献、模型与实验规划；新的真实模型、动态多跳和跨层控制实验待后续任务执行。P1多实体本地模型、P2共享硬件独立上下文、P3远端API、P4单模型切分分别记录。规划中的B2扩到64个无线节点时仍固定4个模型端点，其余为中继；模型数量扩展另行验证。

旧成果保留原数据与结论，五类定位见[总报告§8](research/agent_native_network/RESEARCH_REORIENTATION_20261027.md)。主要入口如下：

| 历史证据 | 适用范围 |
|---|---|
| [前期调研与问题报告](research/agent_native_network/RESEARCH_PROGRESS_AND_PROBLEM_STATEMENT.md) | 纠偏前状态维护与任务执行研究快照，正文保留；其中推进顺序已由新路线接续 |
| [009无线执行](research/agent_native_network/WIRELESS_EXECUTION_STAGE.md) | 60次固定业务回放、18任务回合；简化单竞争域，平均busy低于0.3%，没有容量饱和证据 |
| [008需求执行](research/agent_native_network/DEMAND_EXECUTION_STAGE.md)、[需求账本](research/agent_native_network/DEMAND_CENSUS.md) | 因果任务业务与9/18/36任务规模；不替代动态多跳网络扩展 |
| [HeteroMRTA复现](research/agent_native_network/HETEROMRTA_REPRODUCTION.md)、[MOCHA原协议运行](research/agent_native_network/MOCHA_RUNTIME_ENTRY.md) | 原方法运行与协议语义，沿原条件解释 |
| [来源导航](research/agent_native_network/RESEARCH_PROVENANCE_INDEX.md)、[simulation](simulation/README.md) | 历史源码、原结果与证据等级；文档中的旧待办不自动激活 |

[旧需求驱动链条](research/agent_native_network/DEMAND_DRIVEN_RESEARCH_CHAIN.md)、[此前扩展分析](research/agent_native_network/SCALABILITY_COMPREHENSIVE_ANALYSIS.md)及[首版实验链条](research/agent_native_network/RESEARCH_EXPERIMENT_CHAIN.md)作为阶段资料保留。当前路线和执行顺序以上述新入口为准。
