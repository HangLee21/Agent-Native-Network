# 系统性文献综述与核心证据

最新补查：2026-10-23沿用户新增综述核查任务感知网络调度，见[本文补查表](#survey-network-screen)与[核心问题分析](RESEARCH_GAPS.md#scalability-core)。下文原P编号体系保留；本次候选单列，不改变已登记38篇的主表计数。

检索截止 2026-10-20。编号、原始链接及完整作者见 [PAPERS.csv](PAPERS.csv)，检索限制见 [EVIDENCE_LOG.md](EVIDENCE_LOG.md)。本报告是有明确筛选规则的初始系统性检索，不是已穷尽数据库的系统综述或元分析。

## 问题审查补充（P23–P27）

本轮转向问题存在性，补充两个 SubT 团队现场报告、无线 ROS 2 实验、HAFS 端侧 Agent 通信和语言驱动空地协作。其问题证据和反证统一维护于 [RESEARCH_GAPS.md §0](RESEARCH_GAPS.md)，不将“尚未组合所有特性”作为创新动机。

HAFS [P26] 改变了初始“没有确认端侧 Agent 网络实现”的样本结论：现在已有直接实测，但采用 AP/SFU 与上下文传输负载。空地协作 [P27] 则将紧凑语义图与机会通信接入语言任务，同时仍依赖 GPT-4o API。两者分别约束端侧部署的新颖性和“语义业务必然大流量”的推断。后文十篇核心阅读保留初始核查范围，新增五篇不冒充同样深度的逐项复现审计。

第二轮沿 P27 追溯 MOCHA [P28] 和 ACHORD [P29]。它们已实现最新状态同步、分类可靠交付、速率控制或通信状态驱动移动；新的 Agent 方案必须说明超出这些已有能力的必要性。详细因果边界和带版本的代码链接见 [RESEARCH_GAPS.md §0.6–0.7](RESEARCH_GAPS.md)。目前不足以证明现有机制之后还有显著的 Agent 特有损失。

应用审查新增 P30–P32：铁钛钒矿床空地多传感调查、自适应光谱采样、机器狗团队科学勘查。分别提供观测互补、反馈影响观测选择和实体平台可行性的依据，不能合并推导为一个已经验证的实时空地 Agent 网络系统。P30 当前只到机构摘要；P31 原文为数据驱动仿真，Results/Table 1 与结论指出自适应重规划相对良好静态计划的额外收益较小，故不能用它直接证明强实时共享需求；P32 控制室人工延迟与机间链路必须区分。完整判断见 RESEARCH_GAPS §0.8。

## 1. 从端侧推理到网络业务

端侧执行能力、独立智能体逻辑和无线协议贡献是三个独立维度。CLONE [P20] 为端侧推理的时延与能耗测量提供背景；Petals [P18] 是单模型分布式执行对照。两者均不能直接证明多个设备各自独立模型的协作网络成立。边缘智能体综述 [P19] 的部署、交互与异构性分类可作为阅读框架；EC2-Bench [P12] 提供长轨迹边云协作对照，其云调用决策不等于多跳 D2D 协议。

CoELA、RoCo、LLM2Swarm [P08–P10] 证明自然语言通信可以成为智能体行为的一部分，但通信动作成本、仿真机器人和实际射频资源竞争之间仍有层级差异。RoboTalk [P06] 的独立上下文通过共享推理服务实现；DuoMind [P03] 将推理与动作模型分层。这些系统适合提取通信负载，不能直接作为多设备端侧性能的实验证据。

## 2. 通信需求从预设消息流转为运行时产生

多机器人系统需要交流局部观察、计划和执行反馈。CoMuRoS [P07] 的事件触发重规划表明，执行中的异常会改变后续消息和任务状态；CoELA [P08] 则联合选择沟通与行动。由此可提出本项目的业务假设：消息流可能受接收结果反向影响。不过，“动态消息”不自动构成新的网络问题，必须测量其取消率、依赖阻塞和突发程度，并与普通 RPC、控制遥测和固定 DAG 负载比较。

AgentPrune [P13] 及 G-Designer [P14] 已分别处理冗余消息和任务相关逻辑图。物理路由仍需考虑下一跳可达性、排队、干扰和转发成本。逻辑图上的一条边不能直接视为无线链路；删减 token 也不必然减少相同比例的信道占用，因为协议头、ACK、重传及竞争等待仍存在。

## 3. 从语义通信到推理—网络共同控制

AgentComm [P02] 直接连接语言消息处理与编码传输，是需要正面对比的通信机制工作。Reasoning-Native [P04] 将通信触发扩展到推理状态协调。联合设计论文 [P01] 进一步把交互选择与无线资源联系起来。Agent-Native Wireless Communications [P05] 已覆盖版本、有效期和 Agent-loop 接口，因此不能主张“首次给消息加推理标签”。

无线上下文工程 [P11] 将选择、压缩和状态老化纳入上下文生命周期；其波束预测案例和本项目的多设备自主推理业务不同。它仍削弱了泛泛的“网络状态反馈模型”创新表述。

## 4. 去中心化与多跳机制的继承关系

AoI [P15]、AoII [P17] 和 gossip 时效分析 [P16] 已研究时间、新旧程度及接收端错误状态，Backpressure [P21] 则提供队列驱动的多跳资源控制基础。版本失效机制必须与这些方法比较，尤其不能只比较 FIFO 后声称“推理信息有价值”。本项目新增的候选信息是非时间单调的依赖有效性：较新的消息也可能对应已撤销的分支，而较旧的静态地图消息仍可用。这是待测量的业务属性。

AgenticDTN [P22] 的官方摘要报告真实 802.11s Mesh 上的路由与信道优化。它提示“LLM 控制多跳无线网络”已有系统基础。本轮尚未取得完整实现证据，不能确认每个无线节点是否运行独立模型。它与本项目的区别应落在业务闭环和部署证据，而非单纯“多跳 + LLM”。

## 5. 十篇核心原文核查

下表每行对应用户提出的十个问题中的一个维度。除明确标记外，结论来自所链接原文；“未见”仅表示所读范围没有足够证据。各篇摘要保持紧凑，详细书目和实现字段不重复展开。

### P01：Joint Agent–Network Design

原文：[arXiv 2609.37094](https://arxiv.org/html/2609.37094)，重点 §II–IV、Fig.3–4。

| 核查项 | 结论 |
|---|---|
| 问题 | 推理交互与无线资源相互制约 |
| 模型功能 | 观察解释、请求和协调 |
| 执行位置 | 架构设车载 Agent 与 RSU；实测模型部署未核实 |
| 消息路径 | 车辆经 RSU，固定 V2I；明确无 D2D |
| 网络真实性 | 带宽和 RSU 资源约束的示例仿真 |
| 机制 | 联合交互、消息与资源决策；提出 credit 等设计方向 |
| 平台 | §IV 未给可确认的多端本地推理硬件证据 |
| 基线 | Agent-only、wireless-only |
| 遗留 | 多跳竞争、分区和分布式执行未获验证 |
| 本项目关系 | 最直接概念先例；研究差异需由协议与实验证明 |

### P02：AgentComm

原文：[arXiv 2604.13558](https://arxiv.org/html/2604.13558)，§II–IV、式(2)–(5)、Fig.3–4、§IV-A。

| 核查项 | 结论 |
|---|---|
| 问题 | 降低具身消息传输开销 |
| 模型功能 | 消息压缩、关键项提取、知识更新 |
| 执行位置 | 逻辑 BS/机器人；实验 Claude-Sonnet-4.5、GPT-4o，实体端侧未证实 |
| 消息路径 | BS—机器人上下行 |
| 网络真实性 | OFDM、4-QAM、LDPC 与语义编码仿真 |
| 机制 | 压缩及重要性差异保护 |
| 平台 | 仓储检查、家庭清理生成场景；真实无线设备未核实 |
| 基线 | Direct、LC、LC+SC 及消融 |
| 遗留 | 多跳排队、MAC 竞争、移动断连 |
| 本项目关系 | 可借鉴消息分级；不等价于去中心化调度 |

### P03：DuoMind

原文：[arXiv 2610.02161](https://arxiv.org/html/2610.02161)，§2–4、§4.1–4.4、附录 D。

| 核查项 | 结论 |
|---|---|
| 问题 | 多机器人长程操作协作 |
| 模型功能 | Qwen3-VL-4B 编排，π0.5 动作控制 |
| 执行位置 | §4：训练及评估使用 4 张 A100，属于 P2 证据 |
| 消息路径 | 意图、子目标、信念、不确定性等结构化语义 |
| 网络真实性 | 应用层交换；射频与传输实现未核实 |
| 机制 | 分层推理与语义协作 |
| 平台 | ManiSkill3/RoboPoly、RoboTwin |
| 基线 | 动作模型与通信消融，具体配置见 §4 |
| 遗留 | 时延、丢包、多跳、MAC 资源未验证 |
| 本项目关系 | 可作为依赖型负载；逻辑分布式不能推出 P1 |

### P04：Reasoning-Native Agentic Communication

原文：[arXiv 2602.17738](https://arxiv.org/html/2602.17738)，§III–V、Fig.3–4；IEEE Network DOI 见 CSV。

| 核查项 | 结论 |
|---|---|
| 问题 | 语义一致仍可能产生行为分歧 |
| 模型功能 | 估计对方信念与通信影响 |
| 执行位置 | 具体模型及多端硬件未核实 |
| 消息路径 | 意图 token、同步信号 |
| 网络真实性 | §V-B 声称仿真；复现配置不充分 |
| 机制 | MAR、协调面、信念差异触发 |
| 平台 | 人形协作/交通案例；具体仿真器未核实 |
| 基线 | Classical、Semantic、Agentic |
| 遗留 | 可测状态、时延预算及分布式协议细节 |
| 本项目关系 | 推理感知通信先例；不将其报告数字当作实测保证 |

### P05：Agent-Native Wireless Communications

原文：[arXiv 2605.15873](https://arxiv.org/html/2605.15873)，§II–IV、§IV-B/C、§V。

| 核查项 | 结论 |
|---|---|
| 问题 | 网络支撑与运行 Agent 闭环 |
| 模型功能 | 推理、网络操作、反馈验证 |
| 执行位置 | 设备/边缘/云的架构选择，非具体 P1 验证 |
| 消息路径 | 带 loop、version、validity 的状态交换 |
| 网络真实性 | O-RAN 等架构论述 |
| 机制 | 可编程接口与 loop-aware 资源控制方向 |
| 平台 | 未见本论文可复现跨层测试床 |
| 基线 | 不适用：架构展望文 |
| 遗留 | 去中心化协调、时序与接口实现 |
| 本项目关系 | 直接覆盖版本接口概念；高创新重合风险 |

### P06：RoboTalk

原文：[arXiv 2609.23997](https://arxiv.org/html/2609.23997)，§IV–V、Table II/IV、Training and Evaluation Setup。

| 核查项 | 结论 |
|---|---|
| 问题 | 小 VLM 学习通信与动作协同 |
| 模型功能 | Qwen3-VL-8B 生成工具调用 |
| 执行位置 | 共享 vLLM 服务、每 Agent 独立上下文，P2 |
| 消息路径 | communicate 与 wait-release；leader-follower |
| 网络真实性 | 仿真通信工具，无确认无线竞争模型 |
| 机制 | 数据生成、协调协议、微调 |
| 平台 | 闭环厨房任务仿真；四 GPU 训练，具体型号未核实 |
| 基线 | 无通信到完整指导、未调优/微调、rationale 消融 |
| 遗留 | 网络时延与丢包下同步行为 |
| 本项目关系 | 适合测试释放消息丢失和依赖阻塞 |

### P07：CoMuRoS

原文：[arXiv 2511.22354](https://arxiv.org/html/2511.22354)，§III–IV、Fig.4–13；[作者项目](https://comuros.github.io/)。

| 核查项 | 结论 |
|---|---|
| 问题 | 异构机器人事件重规划 |
| 模型功能 | 任务分配、局部执行、事件判断 |
| 执行位置 | API/本地后端均有评估；每设备本地模型驻留未核实 |
| 消息路径 | 中央 Task Manager 与局部 Agent，ROS 2 |
| 网络真实性 | 有机器人实验；无线协议细节未核实 |
| 机制 | 分层协作与事件处理 |
| 平台 | Go2、Turtlebot、OpenManipulator-X；Gazebo |
| 基线 | 多 LLM 后端、提示变化及重规划测试 |
| 遗留 | 中央节点失效、网络分区、射频控制 |
| 本项目关系 | 取消与事件业务来源；不能因“local LLM”字样归为 P1 |

### P08：CoELA

原文：[arXiv 2307.02485](https://arxiv.org/html/2307.02485)，§3–5、Fig.2、§5.1–5.2。

| 核查项 | 结论 |
|---|---|
| 问题 | 部分观察下有代价协作 |
| 模型功能 | 沟通和规划；记忆与感知模块辅助 |
| 执行位置 | 主实验 GPT-4 API；另测开源模型 |
| 消息路径 | 两 Agent 自然语言广播 |
| 网络真实性 | §3 明确无噪声；通信动作有成本 |
| 机制 | 先形成消息再选择沟通或行动 |
| 平台 | TDW-MAT、C-WAH；实体无线端点未证实 |
| 基线 | MHP、RHP、MAT |
| 遗留 | 广播冲突、拥塞、传播和重传 |
| 本项目关系 | 适合业务测量；通信动作成本不等于无线 airtime |

### P09：RoCo

原文：[arXiv 2307.04738](https://arxiv.org/html/2307.04738)，§3–5、Table 1、§5.1；[作者项目](https://project-roco.github.io/)。

| 核查项 | 结论 |
|---|---|
| 问题 | 多臂协作与路径规划 |
| 模型功能 | GPT-4 对话、子任务、路点 |
| 执行位置 | GPT-4 服务，非实体端侧独立模型证明 |
| 消息路径 | Agent 对话，后接集中多臂规划器 |
| 网络真实性 | 应用层交互，无确认无线模型 |
| 机制 | 对话结合环境反馈及运动规划 |
| 平台 | 六任务 RoCoBench；UR5 人机演示 |
| 基线 | Central Plan、去历史、去反馈 |
| 遗留 | 网络分区及异步传输 |
| 本项目关系 | 提供顺序/并行依赖；有中央规划成分 |

### P10：LLM2Swarm

原文：[arXiv 2410.11387](https://arxiv.org/html/2410.11387)，§3.2–3.3、§4；[作者代码](https://github.com/Pold87/LLM2Swarm)。

| 核查项 | 结论 |
|---|---|
| 问题 | 群体机器人推理与交互 |
| 模型功能 | 控制器生成及运行时协作 |
| 执行位置 | §3.2 明示模拟本地执行；展示使用外部 GPT-4o |
| 消息路径 | ARGoS 中机器人消息进入各自上下文 |
| 网络真实性 | 机器人仿真；射频协议栈未证实 |
| 机制 | direct/indirect integration |
| 平台 | Pi-puck 仿真、普通 PC；代码支持 API/Ollama |
| 基线 | 概念 showcases，缺少严格无线基线 |
| 遗留 | 实体模型驻留与真实竞争 |
| 本项目关系 | 目标接近，但摘要中的 locally 不可替代实验检查 |

## 6. 研究判断

目前可确认的是：业务侧已有动态沟通与逻辑独立推理，网络侧已有语义保护、状态时效和资源控制，而完整系统需要把它们接成可测量、可恢复且有开销预算的协议。八条件逐篇矩阵见 [RESEARCH_GAPS.md](RESEARCH_GAPS.md)。没有全部确认的工作是检索结论，不是新颖性证明；尤其需继续核查 P22 全文及近两年的网络会议论文。

## 反馈机制补查（2026-10-21）

新增P33–P35：现场自主光谱调查摘要（E1）、GP/log-GP自适应条件（E2）、非短视空地观测规划（E2，方法核查arXiv v1）。当前集合35篇。来源、核查范围及局限见 [反馈机制审查](FEEDBACK_MECHANISM_REVIEW.md)；不改变严格A类结论。软件教程作为实现线索单列，不计为论文。

<a id="survey-network-screen"></a>

## 新增综述的定向补查（2026-10-23）

来源为[用户提供的综述PDF](../../任务感知网络调度_新版文献综述_论文原图版.pdf)（19页）。围绕具身网络扩展性重点核查以下7篇：6篇方法原文，CORA为作者机构摘要。表中全名、版本和章节用于后续复现，正式出版版本与已读作者稿分别记录。此前MOCHA/ACHORD另外复核，继续使用P28/P29编号。

| 论文与来源 | 本轮阅读范围 | 已有动态机制 | 对本项目最重要的接口条件 |
|---|---|---|---|
| **ARMA** — *Towards End-to-End Latency Guarantee in MEC Live Video Analytics with App-RAN Mutual Awareness*；MobiSys 2025，[作者全文](https://daehyeok.kim/assets/papers/arma-mobisys25.pdf)，DOI 10.1145/3711875.3729139 | §5–7、§8.3.3、§9.2 | 帧配置、端到端期限拆分、按信道和紧迫性分配RB；处理信道与计算负载变化 | App–RAN快速互感知接口；论文已统计控制字节。共置DU的EdgeRIC与动态mesh中的远端状态维护具有不同通信路径 |
| **CORA** — *End-to-End Coordination of RAN and Edge Server for Latency-Critical Inference Serving over Cellular Networks*；PACMNET/CoNEXT 2025，[作者机构摘要](https://experts.colorado.edu/display/pubid_504668)，DOI 10.1145/3768987 | 书目、摘要；ACM全文入口403 | 动态分配上行/计算/下行时延预算，协调RAN与服务器调度，已有空口原型 | 作为阶段预算与服务接口参考；具体算法公式和控制开销待取得全文后复核 |
| **Co-Scheduling** — *Computation and Communication Co-scheduling for Timely Multi-Task Inference at the Wireless Edge*；[arXiv:2501.04231v1](https://arxiv.org/html/2501.04231v1)，综述对应INFOCOM 2025 | §II–V，重点II-C、III-A、V-B Definition 2 | 按AoI对应的推理误差联合选择计算/发送，拉格朗日松弛得到MGF | 已知各任务AoI及误差函数；调度后下一槽无错到达；渐近结论同比扩展任务与计算/通信资源。复现锁定v1；[v2](https://arxiv.org/abs/2501.04231v2)已改标题并调整算法 |
| **AutoCast** — *AutoCast: Scalable Infrastructure-less Cooperative Perception for Distributed Collaborative Driving*；MobiSys 2022，[作者稿](https://arxiv.org/html/2112.14947)，DOI 10.1145/3498361.3538925 | §3、§5.6；[作者仓库入口](https://github.com/hangqiu/AutoCast) | 接收者相关性、可见性、数据大小与饥饿补偿驱动Greedy Max-Weight；控制消息缺失时外推 | 单跳可互闻调度域，用共同控制消息分别计算发送计划；跨域分频道。优先审计元数据交换与调度模块 |
| **C-MASS** — *C-MASS: Combinatorial Mobility-Aware Sensor Scheduling for Collaborative Perception with Second-Order Topology Approximation*；[arXiv:2407.00412v1](https://arxiv.org/html/2407.00412v1)，2024作者稿；综述列TVT 2026 | §III–V；正式期刊全文未取得 | 移动候选集、CAM信道测量、时变带宽；二阶感知拓扑、Hybrid Greedy和探索/利用 | 单个接收者取得预算W_t后选参与者。保证在等成本特例推导，并随互补度增大而变弱；计算/存储复杂度不能直接转记为通信量 |
| **CoSMO** — *Update for Decisions, Not Freshness: Goal-Oriented Status Updating and Selective Offloading at the Network Edge*；[arXiv:2609.01082v1](https://arxiv.org/html/2609.01082v1) | §III、IV、V-A1、VI | 局部观测与过时远端缓存，联合学习状态表示、更新触发/间隔和卸载；按后续任务效用协调 | EN–SN回传共载任务、结果、状态；ns-3.42/ns3-gym含排队传输。配置为4UE、1EN、1relay、1SN；多EN/SN干扰耦合是扩展方向 |
| **CC-OPI** — *CC-OPI: Online Distributed Task Allocation for UAV Swarms under Communication Constraints*；[arXiv:2609.19208v1](https://arxiv.org/html/2609.19208v1) | §V-B、VI-A Table II、补充材料Table S4 | 拓扑/任务事件触发协商，执行锁、版本同步与断连容错 | 初始任务及新增任务公告全局可得；应用层广播计费，空口争用/重传未建模。可将其状态交换接到共享无线服务模型 |

这组方法已经分别覆盖动态资源、任务价值、互补信息、部分可观测状态和机会协商。当前研究沿“这些调度依据如何经由同一个网络取得、各局部服务预算如何在共享竞争中形成”继续推进。

对综述需保留两项阅读修正：第14/17页对CoSMO的抽象控制分类应同时注明已有ns-3网络仿真；第7页的Co-Scheduling渐近最优应注明资源同比扩展条件。C-MASS的W_t也可时变。ARMA的80UE结果是单独的调度计算开销测试，不能与其空口原型规模合并。

综述其余条目中，Don't Fire Together的错峰通信可作时序对照；Hybrid TDMA–NOMA、UAV语义频谱、JAB-TORA、PACE、RACI保留为后续资源控制线索，本轮核心判断不依赖其未复核的细节。新候选尚未加入PAPERS.csv/references.bib，正式登记时再统一作者、版本与证据字段。
