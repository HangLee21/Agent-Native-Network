# 分布式具身边缘智能的动态可扩展无线网络

**Scalable and Adaptive Networking for Distributed Embodied Edge Intelligence**。当前研究入口更新：2026-10-27。

## 当前定位与阅读顺序

研究由独立模型设备组成的动态无线网络：模型按证据改变请求、来源及后续交互，网络通过发现、路由、传输、MAC/PHY及慢速拓扑控制承载这些变化。核心是服务连续性、控制成本与多维扩展边界；HeteroMRTA和同步恢复分别保留为传统业务、控制面模块。

1. [方向修订总报告](RESEARCH_REORIENTATION_20261027.md)：偏差根因、五个科学问题、架构模型、三个系统候选、强对照及优先任务。
2. [近期文献核查](reorientation_20261027/LITERATURE_REVIEW.md)：12篇核心资料的固定版本、P1/P2/P3/P4、拓扑、规模、控制深度和反馈；补充MANET/Mesh/DTN与Agentic MAC。
3. [架构与模型](reorientation_20261027/ARCHITECTURE_AND_MODEL.md)：请求生命周期、候选/已选/交付图投影、干扰约束、目的端吸收及多时间尺度执行。
4. [验证方案](reorientation_20261027/VALIDATION_PLAN.md)：A真实模型行为、B动态多跳无线、C固定回放与2×2闭环归因；模型、数据、资源和统计边界。
5. [NEXT_STEPS](NEXT_STEPS.md)：唯一当前推进顺序。具体执行与验收以[CURRENT](../../coordination/CURRENT.md)和主任务卡为准。

三个候选分别针对需求修订后的发现—路径—传输协调、服务反馈下的请求节奏与资源预算、协作者/中继角色重构。先同时测量真实请求与动态网络损失，再选择主要机制。普通RPC截止/取消、信息匹配依赖服务、成熟路由/流控及机器人机会网络是强对照。

## 当前证据状态

本次新增内容为文献、架构、建模与实验规划，未启动模型推理或网络实验。独立实体本地模型P1、共享硬件独立上下文P2、远端API P3和单模型切分P4分开记录。规划的N=8/16/32/64是无线节点，B2固定模型端点N_A=4；后续模型实例扩展另设实验。有效到达与实际消费分别用bit/s报告；首条路径与持续服务恢复分列。

[旧总体报告](RESEARCH_PROGRESS_AND_PROBLEM_STATEMENT.md)保留纠偏前正文；其中同步优先路线与推进顺序作为历史阶段阅读。已有009无线实验平均busy低于0.3%，没有容量饱和证据；下一阶段寻找实际业务与网络损失，而不预设现有系统已经拥塞。

## 历史成果与可复用模块

| 文件 | 原证据与新体系中的用途 |
|---|---|
| [WIRELESS_EXECUTION_STAGE](WIRELESS_EXECUTION_STAGE.md) | 60固定回放、18任务回合，状态维护成本和局部无线/行为诊断；单竞争域原条件保留 |
| [DEMAND_EXECUTION_STAGE](DEMAND_EXECUTION_STAGE.md)、[DEMAND_CENSUS](DEMAND_CENSUS.md) | 信息来源/决策/行动账本与9/18/36任务规模；作传统负载及追踪实现参考 |
| [CAUSAL_SERVICE_STAGE](CAUSAL_SERVICE_STAGE.md) | 缓存信息真正控制任务执行的因果适配；保留已测失败和反馈现象 |
| [HETEROMRTA_REPRODUCTION](HETEROMRTA_REPRODUCTION.md)、[HETEROMRTA_NETWORK_INTERFACE](HETEROMRTA_NETWORK_INTERFACE.md) | 原权重/Greedy与零延迟等价、影子动作诊断；传统业务与功能回归 |
| [MOCHA_RUNTIME_ENTRY](MOCHA_RUNTIME_ENTRY.md)、[NETWORK_BASELINE_RUNTIME](NETWORK_BASELINE_RUNTIME.md) | 原状态机回环、作者组件核查；完整部署与组件检查分开 |
| [RESEARCH_PROVENANCE_INDEX](RESEARCH_PROVENANCE_INDEX.md) | 保存源码、运行、合同、manifest及证据来源定位 |
| [simulation](../../simulation/README.md) | 历史代码与结果入口；旧运行/测试不写作本轮通过 |

五类证据在[总报告§8](RESEARCH_REORIENTATION_20261027.md)明确分开：已测状态维护/执行；待测真实模型行为；待建动态多跳；待做无线与模型规模扩展；待验证跨层净收益。历史结果、manifest和原始数据保持原记录。

M-002至M-009的历史执行与C角色审查来自M聊天内子代理，不能视为既有独立角色聊天；独立C窗口历史复核见[C-010](../../coordination/tasks/C-010.md)。最新角色、范围和验收从协调入口读取。

## 其他研究资料

| 入口 | 定位 |
|---|---|
| [RELATED_WORK](RELATED_WORK.md) | 当前定向核查入口及历史文献体系；新R编号不改旧P编号 |
| [PAPERS.csv](PAPERS.csv)、[references.bib](references.bib) | 已登记38篇，当前新核查单列，未机械改计数或合并版本 |
| [EVIDENCE_LOG](EVIDENCE_LOG.md) | 历史检索、访问限制和来源规则 |
| [RESCUE_OPERATIONAL_EVIDENCE](RESCUE_OPERATIONAL_EVIDENCE.md)、[应用合同](demand_20261026/WORKLOAD_CONTRACT.json) | 应用来源、现场事实与拟议适配，按原边界使用 |
| [DEMAND_DRIVEN_RESEARCH_CHAIN](DEMAND_DRIVEN_RESEARCH_CHAIN.md)、[SCALABILITY_COMPREHENSIVE_ANALYSIS](SCALABILITY_COMPREHENSIVE_ANALYSIS.md) | 纠偏前需求/扩展分析，历史候选与实现基础 |
| [RESEARCH_EXPERIMENT_CHAIN](RESEARCH_EXPERIMENT_CHAIN.md)、[framework资料](framework_20261025/) | 首版实验路线与早期模型，旧阶段待办不自动执行 |
| [RESEARCH_GAPS](RESEARCH_GAPS.md)、[AGENT_COLLAB_BASELINES](AGENT_COLLAB_BASELINES.md)、[TASK_SCHEDULING_SCREEN](TASK_SCHEDULING_SCREEN.md) | 历史问题审查、baseline角色与任务策略筛查 |
| [AGENT_COLLAB_MODEL](AGENT_COLLAB_MODEL.md)、[早期机制结果](../../simulation/results/2026-10-22-agent-collab-v1/INTERPRETATION.md) | 自建任务级模型与8640次机制实验，保留辅助用途 |
| [救灾先导](RESCUE_TASK_SCREENING.md)、[找矿反馈审查](FEEDBACK_MECHANISM_REVIEW.md) | 早期场景筛选与分支判断 |

## 引用与证据规则

E1为书目/摘要核实，E2为方法和实验原文核查，E3为另核作者代码/配置；E3不表示执行。部署、来源定位、文件取得、环境运行和结果复现分别记录。当前新文献R01–R12在近期核查稿固定版本，旧P01–P38继续对应CSV/BibTeX；未取得全文和未核设备保持未知。

后续文献更新先核原始版本、部署与方法，再修改书目和计数。比较已有方法在相同信息、权限和成本下的机制与结果，原论文复现、适配和新实验分别标识。
