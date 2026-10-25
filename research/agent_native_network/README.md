# Agent-Native 去中心化无线网络研究

**研究题目：** Agent-Native Decentralized Wireless Networking for Collaborative Edge Intelligence  
**版本：** V2.0，2026-10-25（Asia/Shanghai）

**状态：** 当前以[动态网络可扩展性全面分析](SCALABILITY_COMPREHENSIVE_ANALYSIS.md)为总入口，研究规模—负载—实际网络服务—任务反馈，目标是在相同资源下扩大有效协作的达标运行域。[本轮证据与模型](scalability_20261025/)承接用户对可靠服务假设与扩展性的矫正；[首版科研链条](RESEARCH_EXPERIMENT_CHAIN.md)及其[详细资料](framework_20261025/)保留为实施基础。

最新：[核心问题分析与最小模型](RESEARCH_GAPS.md#scalability-core)、[综述原文核查](RELATED_WORK.md#survey-network-screen)、[网络baseline角色](AGENT_COLLAB_BASELINES.md)。[任务调度筛查](TASK_SCHEDULING_SCREEN.md)中的HeteroMRTA仍作为首个学习任务执行器，已完成源码固定、原权重与作者Greedy小实例配对评估；AutoCast、MGF、C-MASS、CoSMO等提供网络侧对照。此前[自建模型](AGENT_COLLAB_MODEL.md)和[8640次机制实验](../../simulation/results/2026-10-22-agent-collab-v1/INTERPRETATION.md)保留为辅助工具。

当前应用入口为救灾空地协作，实际任务证据见[现场部署与观测协作](RESCUE_OPERATIONAL_EVIDENCE.md)。实验室已有无人机/机器狗平台，载荷、通信链路及协作流程仍可按研究需要确定。

本轮输入：[任务感知网络调度综述原件](../../任务感知网络调度_新版文献综述_论文原图版.pdf)。对其中论文的版本、方法和实验条件核查维护于[补查表](RELATED_WORK.md#survey-network-screen)。

## 研究定位

面向无人机、机器狗、手机和工业节点各自运行模型的系统，研究自主通信需求与无线网络控制之间的闭环。最终目标保留控制面、传输、路由、MAC/PHY及移动拓扑的完整系统范围。任务规划和模型训练用于产生业务负载，不作为当前主要创新。

**研究原则（2026-10-23按用户纠正更新）：** 已有研究为问题、方法和性能提供参照；“已有方法”不等于问题已被充分解决。创新可以发生在相同问题、相同假设下，例如更好的算法/协议、更强理论结果、更优性能—成本折中、更低复杂度或更强动态适应能力。研究按“原方法如何工作、在哪些条件下做到什么程度、限制来自什么机制、我们的改变带来什么可验证改善”推进。协议层是当前实验入口，MAC、PHY、路由及跨层联合优化保持开放；具体贡献由模型、机制和实验逐步确定。

部署严格分为 P1 多实体设备本地推理、P2 共享硬件上的独立上下文/逻辑实例、P3 云端模型 API、P4 单模型跨设备切分。P2 可用于功能验证，不能替代 P1 的设备性能证据；共享权重和独立上下文也不必然意味着多个独立推理进程。

## 当前证据与实现状态

主表已登记 **38篇**，引用与证据等级对应P01–P38。本轮另定向核查综述中的7篇候选：6篇方法原文、CORA为作者机构摘要；任务调度另有7组筛查结果，两部分尚未合并主表。HAFS P26是已确认的严格A类实例，其部署特征和其他系统差异见文献矩阵。矩阵用于描述系统，具体研究贡献通过方法与结果比较。

[HeteroMRTA原权重与作者Greedy评估](HETEROMRTA_REPRODUCTION.md)已完成9机器人、15/20任务各5种子，共20次正常运行全部成功，另记录单行Greedy诊断失败。[HeteroMRTA送达缓存](HETEROMRTA_NETWORK_INTERFACE.md)完成10实例384个决策点零延迟等价，并测得0.5/2模拟时间延迟分别改变138/215次影子动作。[MOCHA原协议运行](MOCHA_RUNTIME_ENTRY.md)通过18项双进程回环检查，原状态机、SMACH、DB与ZeroMQ路径均实际执行。此前[MOCHA/AutoCast组件核查](NETWORK_BASELINE_RUNTIME.md)的14项探针保留。当前闭环通信任务性能、完整ROS/CARLA与无线效果仍待测量；CoSMO、MGF、C-MASS按任务兼容条件接入。下一实验入口见[阶段判断](../../coordination/reviews/M-004-interpretation.md)。

**问题与改进依据：** 野外机器人断续连接、大消息无线交付退化，以及特定端侧Agent上下文流与实时业务竞争，有原始研究支持。本地自治、紧凑语义图、机会通信和DDS配置优化提供了已有能力。继续复现这些方法，测量其任务性能、通信成本和规模边界，围绕更优的收益—成本折中、稳定性、可扩展性及理论保证开展改进。

当前问题、baseline与改进方向集中见[RESEARCH_GAPS §0.9与§2](RESEARCH_GAPS.md#scalability-core)。联合优化、语义压缩、状态同步等已有方向均可继续研究；评价具体机制、性能、成本和理论贡献。

## 历史阶段

| 阶段 | 已有成果与入口 |
|---|---|
| 找矿观测与共享 | [Cuprite观测初查](../../simulation/results/2026-10-20-cuprite-observation-v1/INTERPRETATION.md)、[反馈审查](FEEDBACK_MECHANISM_REVIEW.md)；当前覆盖策略分支暂停 |
| 救灾发现回报 | [任务筛查](RESCUE_TASK_SCREENING.md)、[公开拓扑结果](../../simulation/results/2026-10-21-rescue-graph-v1/INTERPRETATION.md) |
| 4节点协作通信执行器 | [V0模型](AGENT_COLLAB_MODEL.md)、[8640次机制实验](../../simulation/results/2026-10-22-agent-collab-v1/INTERPRETATION.md) |

历史任务、参数和结果保留原记录；当前研究优先级由本页及NEXT_STEPS维护。

## 文件导航

| 文件 | 内容与维护入口 |
|---|---|
| [RELATED_WORK.md](RELATED_WORK.md) | 初始核心阅读、后续补查及新增综述核验 |
| [AGENT_COLLAB_BASELINES.md](AGENT_COLLAB_BASELINES.md#first-study) | 当前baseline分工、优化层次、指标与比较口径 |
| [TASK_SCHEDULING_SCREEN.md](TASK_SCHEDULING_SCREEN.md) | 7组任务调度候选、代码入口及复现状态 |
| [PAPERS.csv](PAPERS.csv) | 38 篇已登记文献；本轮定向补查候选见RELATED_WORK |
| [references.bib](references.bib) | 与 paper_id 一一对应的引用；未核实 DOI 不填入 BibTeX |
| [RESEARCH_GAPS.md](RESEARCH_GAPS.md) | 问题存在性审查、反证、八条件矩阵及待验证假设 |
| [ARCHITECTURE_MODEL.md](ARCHITECTURE_MODEL.md) | 三类架构图、消息协议、V0 数学模型及可控性 |
| [TASK_DEFINITION.md](TASK_DEFINITION.md) | 历史找矿任务与先导实验定义 |
| [RESCUE_TASK_DEFINITION.md](RESCUE_TASK_DEFINITION.md) | 救灾发现回报先导任务及阶段结论 |
| [FEEDBACK_MECHANISM_REVIEW.md](FEEDBACK_MECHANISM_REVIEW.md) | 反馈来源、因果审计、空间混合及停止判定 |
| [NEXT_STEPS.md](NEXT_STEPS.md) | 当前推进顺序与暂缓采用的技术备选 |
| [EVIDENCE_LOG.md](EVIDENCE_LOG.md) | 检索策略、版本冲突、来源链接、访问限制和核查结果 |
| [simulation](../../simulation/README.md) | 可运行任务级原型、测试及合成场景结果 |

## 证据与更新规则

E1 表示书目/摘要核实；E2 表示方法和实验原文核查；E3 表示额外核对作者公开代码或配置。E3 不表示执行过代码。所有“未核实”保持未知，不能转成“是”或“否”。分类 A/B/C/D 描述相关性，证据等级描述读到了什么，两者独立。

引用使用 `[P01]` 等稳定标识，对应 CSV 和 BibTeX 的同名 key。CSV 的 year 是实际引用版本年份，first_year 保留首次预印本年份。正式发表未核实的记录引用已核实预印本，publication_status 明示此限制，不能将它解释为确认尚未发表。

后续更新顺序：先核对官方版本及部署证据，再更新 CSV/BibTeX，最后更新综述、矩阵和数量。八条件用于描述部署与系统覆盖范围；新论文出现时更新相应baseline、已有能力及改善空间，不以是否填满八条件判断问题已解决或创新成立。各文献证据等级按实际核查范围维护。

## 仓库检查

开始时当前目录为空，无可复用文档及本地 AGENTS.md；父级两处 AGENTS.md 亦未发现。Git 根目录实际为 `D:/`，触发 dubious ownership。使用一次性 `git -c safe.directory=D:/` 完成范围限定的只读检查，未更改全局配置、初始化仓库或提交。检查范围内起始工作区无变更。未触碰其他目录的实验结果。

上述为首次检查的历史记录。随后按用户要求在当前目录建立独立仓库并关联 `HangLee21/Agent-Native-Network`；后续文件维护均在该独立仓库内。
