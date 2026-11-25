# 近期文献、强对照与可推进的问题

核查日期：2026-10-25。负责人：D；任务：[D-003](../../../coordination/tasks/D-003.md)。本文件为[科研与实验框架](../RESEARCH_EXPERIMENT_CHAIN.md)提供文献依据；具体实验设计见[实验方案](EXPERIMENT_DESIGN.md)。本轮仅核查原文与整理研究设计，没有新增实验。

## 1. 当前研究位置

“状态越新越好”已经不是相关工作的共同前提。近期方法已经研究按决策价值更新、查询与任务控制共享预算、异步缓存、发送错相及通信代价。因此，本项目应从这些机制及其结果出发，考察**更新生成、排队与消息服务如何共同影响信息到达后的任务收益**。改进可以发生在相同任务和假设下：更准确或更便宜的价值估计、更好的调度解、可证明的稳定性，以及更好的任务性能—通信成本折中，均值得研究。

本文件将“原文陈述”和“拟研究动作”分开。下面各项能力来自所列版本；只有 MOCHA/AutoCast 的指定组件具有本项目本机执行证据，其余论文在本项目尚未复现。原论文结果不用于替代我们的实验数据，也不跨任务排列优劣。

| 对照层次 | 优先对象 | 它回答的问题 | 在本项目中的用途 |
|---|---|---|---|
| 低成本基础机制 | 周期同步、事件触发、latest-state、合理队列/限速、错相周期发送 | 收益是否来自简单的缓存和时间安排？ | 所有统一任务实验的基础对照；同步周期不能是唯一周期参照 |
| 直接机器人协议 | MOCHA；AC-DMTA、CBBA-ETC、CC-OPI 的通信机制 | 怎样维护可执行的协作信息，避免无效同步？ | MOCHA 先推进原组件和接口；后三者先验证原任务适用性，再做具名适配 |
| 联合决策与通信 | CommHG、CoSMO、Asking for Information、Planned synchronization | 什么信息值得获取，获取和协调的成本如何进入决策？ | 作为强方法与理论起点；原生联合策略和冻结执行器下的适配分别报告 |
| 任务消息调度 | AutoCast、最新版 Reoptimized MGF、C-MASS | 哪条消息或消息集合值得占用服务？ | 分别用于协同感知、远程推理、互补感知；任务语义匹配后引入 |
| 跨层接口 | ARMA、CORA | 任务期限如何映射到无线与计算服务预算？ | 保持 MAC、PHY、路由和跨层联合优化开放，不要求首轮部署完整蜂窝系统 |

## 2. 近期直接工作：已有能力与具体比较

### 2.1 CommHG：共享预算下的查询与任务协作

**版本与定位。** *Communication-Aware Heterogeneous Graph Learning for Decentralized Multi-Human Multi-Robot Task Allocation*，[arXiv:2609.32935v1](https://arxiv.org/html/2609.32935v1)，2026-09-26。重点为 §III-A–D、§IV-A 与 Table I。

**原文事实。** 接收者本地图使用可得观测与已送达记录，保留时间戳、age 和 knownness；训练 critic 可用全局状态，执行策略不能。机器人同时选择任务、广播门控和操作员查询。查询占用遥测上行预算，回复与优先级更高的控制命令竞争下行；链路包含延迟、丢失、过期和控制租约。公开任务属性与操作站共享证据仍属于其信息假设。Small/Medium/Large 同时改变机器人、地图、任务、时限和无线范围，最大配置为 16 机器人、6 人、112 任务。

**拟研究动作。** 将其列为直接强对照，先核查可运行代码和原任务。原生比较保留人机监督语义；把查询/门控思想接到冻结 HeteroMRTA 时，称“CommHG 启发的机制适配”，不称复现原策略。可在相同预算模型下比较低成本价值估计与学习式决策的任务收益、训练成本和执行开销；再控制地图、任务负载和服务资源，分解规模曲线。增加共享无线服务时，需要说明替换了哪项原预算规则。

### 2.2 AC-DMTA：分配稳定性证书与定向更新

**版本与定位。** *Assignment-Consistent Dynamic Multi-UAV Task Allocation: Communication-Efficient Dynamic Multi-Unmanned Aerial Vehicle Task Allocation Under Stale and Asymmetric Information*，[Drones 10(7), 523](https://www.mdpi.com/2504-446x/10/7/523)，2026-07-09；[版本记录](https://www.mdpi.com/2504-446X/10/7/523/notes)列 HTML 于 07-10 更新。重点为 §3.1–3.3、§4、§5.1–5.3、§6.4。

**原文事实。** 局部过时信息形成不确定性集合；区间出价用于检查 winner、bundle 与可行性是否稳定。证书失败后，按预期分配边际改善/字节定向查询，使用 recency/version 消解冲突，并限制重试。保证只覆盖所建模的候选、交换邻域和不确定性范围。其 fresh-replay 诊断区分“证书通过但新信息改变决策”与实际任务损失；主要残余不一致来自未覆盖的局部交换。原实验包含共同种子、延迟/丢包和记录字节计费，并已测试扩展规模。

**拟研究动作。** “按任务决策变化触发”应与该机制直接比较。先在其原假设下复现证书和定向查询，再比较证书计算成本、保守程度与任务损失；同一候选集合下可研究更便宜的近似证书。对排队后的消息，比较发送时边际收益和预计到达时边际收益的排序。记录决策变化、任务后果和字节三者，不把每次决策变化都记为有害失配。能力组队的 HeteroMRTA 需要重新定义证书，不能直接照搬单任务 winner 判据。

### 2.3 Don’t Fire Together：简单错相发送是必要对照

**版本与定位。** *Don’t Fire Together: Desynchronised Communication Scheduling for Bandwidth-Limited Multi-Robot Exploration*，[Sensors 26(15), 4778](https://www.mdpi.com/1424-8220/26/15/4778)，2026-07-27；[版本记录](https://www.mdpi.com/1424-8220/26/15/4778/notes)列 HTML 于 09-04 更新。重点为 §3.1–3.4、§4.4 与实机实验。

**原文事实。** 冻结探索策略后改变广播相位；位姿与特征都经消息传递，静默时读取缓存。对称全互扰条件下，均匀错相改善峰值团队过时度；更一般的激活策略还考虑异构资源。实验显示任务收益依赖规划器是否使用共享信念。比较主要固定每节点名义发送率，任务轨迹变化可使全程总字节不同，不能称严格等总通信量。四机器人 WiFi 实验验证了发送时序到过时度这一段机制。

**拟研究动作。** 加入充分调参的 staggered-periodic，与同步周期、随机相位、事件触发同场比较。报告实际字节、服务占用、平均及峰值过时度。联合方法需优于这个便宜的机制；若只改善平均 AoI 却没有任务收益，应回查策略对共享状态的敏感性。异构链路下比较均匀错相与服务时间加权错相，后者是待验证设计。

### 2.4 CoSMO：已存在任务效用驱动更新与真实网络仿真

**版本与定位。** *Update for Decisions, Not Freshness: Goal-Oriented Status Updating and Selective Offloading at the Network Edge*，[arXiv:2609.01082v1](https://arxiv.org/html/2609.01082v1)，2026-09-01。重点为 §III-B–D、§IV、§V-A1。

**原文事实。** SN 学习语义状态表示、发送/不发送和下一决策间隔；EN 根据本地状态与收到的远端缓存选择本地执行、卸载或拒绝，以实际任务效用协调两个异步决策过程。状态、任务及结果共用传输资源；实验使用 ns-3.42/ns3-gym，包含排队和转发，配置为 4 UE、1 EN、1 relay、1 SN。因此其基线不能简写为“理想无队列信息链路”。

**拟研究动作。** 先在相同拓扑、负载和任务控制下比较原策略与更低成本的更新价值估计，报告任务收益、更新字节、计算与学习代价。多节点共享服务可作为后续扩展，但改进不以新增拓扑为前提。适配到 HeteroMRTA 时先冻结任务执行策略，明确只保留更新动作与训练目标的哪些部分；联合重训练另外列组。

### 2.5 CC-OPI：在线协商与执行状态必须保持一致

**版本与定位。** *CC-OPI: Online Distributed Task Allocation for UAV Swarms under Communication Constraints*，[arXiv:2609.19208v1](https://arxiv.org/html/2609.19208v1)，2026-09-16。重点为事件驱动执行/协商机制、§VI-A Table II 与补充 Table S4。

**原文事实。** 在线物理执行与协商并行；拓扑、任务完成、心跳和新任务触发协商，并使用执行锁、版本化完成状态和断连恢复。原设置中初始任务全局已知，新增任务全局公告，时钟同步；按应用层广播及字节计费，并未把 MAC 争用、重传建成同一无线服务过程。其鲁棒执行能力和通信支出需要同时评价。

**拟研究动作。** 先保持执行锁与完成语义，检查何种状态交换可合并或延后；再将既有广播接到统一服务模型，测量任务状态迟达是否导致重分配、重复执行或等待。将公告从全局可得到实际送达是另一个实验条件，不能暗中只对某一方法施加。原任务分配算法和冻结执行器下的通信适配分别命名。

### 2.6 两类有代价的信息获取规划

| 工作及锁定版本 | 已核查的能力与条件 | 本项目的比较或借鉴 |
|---|---|---|
| *Asking for Information by Evaluating the Communication and Coordination Trade-Off in Multi-Agent POMDPs*，[IEEE RA-L，DOI 10.1109/LRA.2026.3703246](https://doi.org/10.1109/LRA.2026.3703246)，2026-06-12 在线；11(8):9144–9150；§II–IV | 根据通信引起的预期协调收益决定是否询问信息，允许局部决策不完全一致。其通信假设为可用、即时、可靠但有成本；离线联合规划支持分散执行。 | 同模型下可以改进查询计算复杂度或信息选择；加入有延迟的请求—回复时，应比较信息到达后收益和等待成本，而非只比较状态差异。 |
| *Planned synchronization for multi-robot systems with active observations*，[Autonomous Robots 50:5，DOI 10.1007/s10514-025-10225-4](https://link.springer.com/article/10.1007/s10514-025-10225-4)，2025-12-24 在线，2026 卷；§3.2 Definition 1、§3.3、§4.3.1、§5 | MDPANS 已显式计入执行、观测、协商下次观测计划的成本；通过联合状态规划获得执行/同步成本的 Pareto 折中，并有机器人实验。 | 参考其成本分解，研究异步部分送达和共享队列如何改变下一次同步的价值；也可保持原模型改善求解复杂度。不能把“协调本身有成本”写成无人处理的新发现。 |

## 3. 现有首轮基线与条件性对照

### 3.1 MOCHA 与 AutoCast：论文机制、作者默认路径、本机组件证据

| 对象 | 版本与原文定位 | 应保留的已实现能力 | 本项目下一比较 |
|---|---|---|---|
| **MOCHA** | *Enabling Large-scale Heterogeneous Collaboration with Opportunistic Communications*；[2023 作者稿](https://arxiv.org/html/2309.15975)，ICRA 2024；§III、§IV。作者代码固定 `bfbde0d186d77278085b25a365bf735d5acdc6bd`，[KumarRobotics/MOCHA](https://github.com/KumarRobotics/MOCHA/tree/bfbde0d186d77278085b25a365bf735d5acdc6bd) | 时间戳/头部协商、最新信息请求、机会接触转发及主题优先级。原系统有接触同步实验；同步交互成功率的分母不能替换为全部任务需求。 | 在共同缓存/传输接口下比较固定主题优先级与任务价值优先级；将头部、请求、转发均计费。原 ROS2 协议运行继续单独验收。 |
| **AutoCast** | *AutoCast: Scalable Infrastructure-less Cooperative Perception for Distributed Collaborative Driving*；[作者稿](https://arxiv.org/html/2112.14947)，MobiSys 2022；§3、§5.6。[作者入口](https://github.com/hangqiu/AutoCast/tree/5a69701081dcda9741106ad749270dc27b647ee9)固定 `5a69701081dcda9741106ad749270dc27b647ee9`，子仓库 AutoCastSim 固定 `10837c2a942e92312ea1a53697bc4513d9325454` | 基于接收相关性、可见性、对象大小及饥饿补偿的 Greedy Max-Weight；控制元数据支持分布式发送计划，缺失控制信息可外推。论文以可互闻的单跳调度域为基础。 | 先保持原协同感知任务测量元数据及对象服务成本，再比较到达时价值与发送时价值；HeteroMRTA 尚无等价原生点云任务，不直接移植其任务效用。 |

本机 [D-002 报告](../NETWORK_BASELINE_RUNTIME.md)及[采纳结果](../../../simulation/results/2026-10-23-D-002-network-components/)只支持原组件级判断：14 项探针记录了固定源码、AST 提取、依赖替身、输入及原输出。它们没有运行完整 ROS2/CARLA 协议，也没有测量真实无线容量或时延。

其中 AutoCast 作者仓库默认 `EmulationMode=False`、`DistributedMode=False`，默认共享缓存与直接数据写入路径需与可配置的 distributed 路径分别审计；不能把论文的分布式设计直接视为该默认配置已执行的结果。探针观察到的 100 ms 检查跨界来自 `TX_Data` 的控制流与负载公式，旧帧覆盖来自特定 `LockBuffer` 输入，均保持组件层限定。这些现象用于确定接入接口和边界测试，不作为本项目算法获益的证据。

### 3.2 MGF、C-MASS、ARMA、CORA

| 工作与已读版本 | 原文能力、假设及定位 | 具体研究动作 |
|---|---|---|
| **Co-scheduling / MGF**：[v1](https://arxiv.org/html/2501.04231v1)，2025-01-08，*Computation and Communication Co-scheduling for Timely Multi-Task Inference at the Wireless Edge*；[v2](https://arxiv.org/html/2501.04231v2)，2025-08-22，*Computation and Communication Co-scheduling for Multi-Task Remote Inference* | §II-C 使用调度后下一槽无错到达；v1 §V-B Definition 2 的渐近扩展同时增加任务和计算/通信资源。v2 §V-A 为 **Reoptimized MGF**，§V-C 提出简化版本，更新了乘子求解方案。 | 历史 v1 复现可保留，最强对照应核查 v2。分别测试资源同比扩展和总服务资源固定；同原模型比较重优化、固定乘子和低成本近似的解质量/计算开销，再研究延迟到达适配。 |
| **C-MASS**：*Combinatorial Mobility-Aware Sensor Scheduling for Collaborative Perception with Second-Order Topology Approximation*，[arXiv:2407.00412v1](https://arxiv.org/html/2407.00412v1)，2024-06-29 | §III–V 已含移动候选集、CAM 信道测量和时变预算；二阶拓扑描述互补感知，Hybrid Greedy 配合探索/利用。§V-A2 Theorem 1 在等成本条件下给保证，并依赖协作度。这里使用已读 v1，期刊全文等价性尚待核对。 | 先在原感知模型比较其近似与小规模精确解、估计开销及过时拓扑影响。HeteroMRTA 的能力组队不自动等同于二阶感知互补；仅在构造了真实集合效用时引入该对照。 |
| **ARMA**：*Towards End-to-End Latency Guarantee in MEC Live Video Analytics with App-RAN Mutual Awareness*，[作者全文](https://daehyeok.kim/assets/papers/arma-mobisys25.pdf)，MobiSys 2025，DOI 10.1145/3711875.3729139 | §5–7 联合帧/推理配置、端到端期限和无线资源调度；§8.3.3、§9.2 给实现与代价。已有 App–RAN 互感知及控制字节统计，80 UE 的调度计算测试与空口原型规模需分开。 | 参考信息接口和期限分配，记录本项目接口成本与更新时间；先验证期限—服务预算映射是否改善收益，再决定深入 MAC/PHY。 |
| **CORA**：*End-to-End Coordination of RAN and Edge Server for Latency-Critical Inference Serving over Cellular Networks*，[作者机构摘要](https://experts.colorado.edu/display/pubid_504668)，PACMNET/CoNEXT 2025，DOI 10.1145/3768987 | 当前证据为书目与机构摘要：协调上行、计算、下行的延迟预算及调度，已有无线原型。ACM 全文未取得，具体算法和控制开销未核实。 | 用作分阶段预算的架构参考。取得全文并核对信息来源/接口开销之后，才能决定是否复现具体调度器。 |

### 3.3 本轮补充的相邻直接工作

| 新来源 | 已核实范围 | 对计划的作用 |
|---|---|---|
| *Event-Triggered Adaptive Consensus for Multi-Robot Task Allocation*（CBBA-ETC），[arXiv:2604.06813v1](https://arxiv.org/html/2604.06813v1)，2026-04-08 | §4.3–4.5 的事件触发、自适应共识间隔与执行结构；§5 基线比较。此处按作者稿记录，不据二手索引推定期刊版本内容。 | 形成比固定周期 CBBA 更强的事件触发对照；与 AC-DMTA 区分“状态/出价变化”和“分配稳定性”两类触发依据。 |
| *Wireless communication empowers online scheduling of partially-observable transportation multi-robot systems in a smart factory*，[arXiv:2603.23967v1](https://arxiv.org/html/2603.23967v1)，2026-03-25 | §3 调度/路径，§4 无线资源与多链路传输，§5 理想和现实无线条件；论文首部保留模板出版字段，本文只采用 arXiv 日期。 | 任务调度、路径与无线资源联合处理已有直接先例。可沿具体耦合项改进，不把“跨层联合”单独当作贡献。 |
| *Bundle Length Tradeoffs in Decentralized Multi-Robot Task Allocation Under Degraded Communications*，[arXiv:2609.06273v1](https://arxiv.org/abs/2609.06273)，2026-09-05 | 本轮只核查官方摘要：配对场景比较 bundle 长度与丢包条件，理想通信下的调参结论不必保持。全文算法和实验细节未核实。 | 支持对通信条件分别调参，并报告训练/调参资源一致性；进入强基线清单前继续读全文。 |

## 4. 从文献机制到可检验的研究动作

以下是研究假设与设计，尚无本项目结果。各项先在原方法假设下分析和改进；需要改变场景或无线服务时，再增加明确标注的扩展组。

| 机制问题 | 最贴近的既有起点 | 可实现的比较 | 支持判断所需证据 |
|---|---|---|---|
| 更新在源端值得发送，到达时是否仍有用？ | AC-DMTA 的边际/字节、AutoCast 的价值/大小、CoSMO 的累计任务效用 | 原排序；加预计等待/服务时间；过期替换；全知信息离线诊断参考。只有在明确的松弛模型中求得精确最优值，或取得方向正确的求解器界时，才作界限；未来信息不供在线策略读取 | 到达时有效性、因迟达失去用途的字节、任务后果、估计误差及估计开销 |
| 更积极的触发是否挤占任务消息？ | CommHG 的预算竞争、CoSMO 的共享资源、Planned synchronization 的成本分解 | 固定发送器只改触发；固定触发只改服务；二者联合；统一请求、回复、确认和数据计费 | 逐类队列/服务、控制占比、尾时延、每完成任务成本和联合收益；观察负收益区间 |
| 简单时间安排能解释多少收益？ | Don’t Fire Together、周期/事件触发 | 相同资源下的同步、错相、随机、事件和联合调度；共同 latest-state/合理限速底座 | 实际流量、平均/峰值过时度、队列峰值与任务性能；收益是否依赖执行策略 |
| 价值估计太贵或依据过时，是否抵消收益？ | AC-DMTA 证书、Reoptimized MGF、C-MASS 拓扑估计、CommHG 学习决策 | 原估计；低成本近似；精确小规模参照；相同调参预算；估计周期与精度消融 | 计算时间、额外探测字节、排序后悔、性能—总成本曲线；若推导界限则列明模型条件 |
| 扩展曲线到底由什么改变？ | CommHG 的复合规模配置、MGF 的同比资源扩展、CC-OPI 动态执行 | 固定区域加密/固定密度扩区分别做；固定总任务/固定每节点任务分别做；动态强度单独扫；再比较固定总资源与同比扩展 | 同一任务策略和规模的即时信息参照；完成率/失败、makespan、每任务成本、尾时延及置信区间 |

首轮统一实验仍使用 HeteroMRTA 的任务策略和作者 Greedy 分别冻结，沿用 makespan，并报告完成比例、失败/超时。能力需求允许必须组队；即时信息参照也是同一团队任务，不用“单机器人独立完成全部任务”替代。远端观测、动作 mask 和信息价值估计须遵守同一实际送达条件。

HeteroMRTA 原任务首先适合分析协作状态维护。对于对象、地图或推理结果等任务消息，应先在 AutoCast 等兼容任务中研究其发送价值，再接入有明确因果用途的救灾观测依赖；不能仅添加无消费方的数据流来制造竞争。后续若联合重训任务与通信策略，需与冻结策略实验分组，以区分网络机制收益与策略适应收益。

## 5. 版本修正、证据状态与下一步

1. **直接对照已更新。** CommHG、AC-DMTA、错相发送和两类有代价信息规划已经覆盖本项目问题的一部分。研究判断据机制和比较结果作出，不以泛化的“前人未考虑状态/协调成本”立题。
2. **最新 MGF 需使用 v2。** 旧表锁定 v1 有历史意义；v2 标题与算法均已更新，不能只比较旧 MGF 后称优于当前工作。
3. **CoSMO 已做网络仿真。** 它有真实排队传输的 ns-3 实验；多节点扩展是可选路线，相同拓扑中的更好方法也可以形成贡献。
4. **原系统与本机组件分开。** D-002 提供接口和原组件证据；完整 MOCHA/AutoCast 任务协议尚未本机复现。源代码默认路径也不自动等同于论文实验配置。
5. **版本未取得就保留未决项。** C-MASS 的期刊全文与作者稿差异、CORA 全文细节尚待核查；这不意味着论文不存在。上述相邻工作中只读摘要的条目不承载具体算法结论。

本轮检索沿“multi-robot/task allocation + event-triggered/communication scheduling/stale information/value of information”，并逐项检查既有论文的 arXiv 版本历史与官方出版页。主要证据来自 arXiv 原文、出版社原文/版本记录及作者机构页面。MDPI 部分直接打开返回 429，但官方域名检索返回了上述章节正文；没有以第三方概括代替已列方法机制。ARMA 本轮作者 PDF 读取有超时，方法细节承接仓库已记录的全文核查；CORA 保持摘要级范围。检索截止日期是证据快照，并非穷尽所有同期论文的声明。

下一实施次序为：完成实际送达缓存与零延迟等价检查；在原条件下推进 MOCHA/AutoCast 并补齐近期强方法的代码/参数来源；验证基础错相和合理队列；在少量受控实例上比较更新与发送的独立、联合效果。若简单方法已经解释主要收益，则继续查具体损失和成本，不预设复杂联合算法必然更优。
