# 动态具身边缘智能网络：近期文献与强机制核查

检索与核查日期：2026-10-27（Asia/Shanghai）。D-009第一阶段交付。围绕 **Scalable and Adaptive Networking for Distributed Embodied Edge Intelligence** 重新选择比较对象；12篇核心资料按架构、方法及评价章节定向深读，另核查Mesh实证摘要、网络控制方法和协议规范。本轮不运行模型、代码或网络仿真，全文阅读不等于本机复现。

## 1. 对研究定位的直接影响

当前研究对象应是承载独立模型设备交互的动态无线网络：节点加入退出、移动链路、干扰、多跳路径、分区重连与控制面收敛都会改变业务可用性；模型收到证据后又会改变交互对象、内容及后续请求。需要证明网络机制怎样在这些变化下持续提供服务，并解释其控制和计算成本。

近期文献已覆盖相当多的总体构想。MEAN提出具身任务与网络协同框架；Joint Agent–Network Design明确联合交互、消息、逻辑/物理拓扑及资源；Agent-Native Wireless讨论接口、时间尺度和Agent-loop；Agentic MAC两类工作直接让LLM参与信令与资源控制。双图、接口、任务标签或“跨层”四个字都不能单独承担贡献。

已有系统也不能降格为弱对照。MOCHA有机会接触、存储转发及通信感知移动；ACHORD有真实多跳、分类可靠交付、网络反馈与自主中继部署；HAFS有真实端侧模型及传输协调。值得验证的差别应落在可执行机制与同条件结果，例如动态多跳交互的服务连续性、拥塞反馈如何改变实际推理请求、慢速模型决策与快速协议执行怎样协调。以下“待核问题”是本项目要做的比较，不表示相应领域无人研究。

## 2. 检索方法、范围与未完成项

优先时间范围为2024—2026；MOCHA（2023）和ACHORD（2022）作为指定的直接协议/系统先例保留。先从用户指定工作和仓库原文链接进入，再按关键词、会议/期刊和引用线索扩展，只用作者原文、作者代码/机构、出版社、会议官网和RFC/实现官方文档支持结论。搜索中的聚合站只作发现线索。

实际检索主题分组如下，组合查询包含年份和同义词；这是一轮有界定向调研，不是逐年全部论文的系统综述。

| 主题组 | 本次查询包含的词与范围 |
|---|---|
| 具身与Agent网络 | Agent-Native Wireless Networking；Scalable Multi-Agent Edge Intelligence；Dynamic Networking for Embodied AI；Mobile and Decentralized Edge Agents；MEAN |
| 分布式模型与交互 | Distributed LLM/VLM Agents over Wireless Networks；Dynamic Agent Communication Graphs；AgentComm；Joint Agent–Network Design |
| 动态底层与跨层 | Agent-Aware Multi-Hop Routing；Network Scalability for Intelligent Robot Swarms；Cross-Layer Networking for Autonomous Edge Devices；Inference-Aware MAC / Wireless Resource Control |
| 会议定向 | MobiCom、MobiSys、SIGCOMM、NSDI、SenSys、INFOCOM，配合2024/2025/2026、agent/LLM/robot/wireless等关键词；另查相关机器人与arXiv原文 |
| 期刊定向 | TMC、TWC、IoT-J的出版社域名与题名组合检索；发现Agentic MAC的TMC记录和VLM-DC等近邻 |

会议官方页面另检查了[NSDI’26](https://www.usenix.org/conference/nsdi26/technical-sessions)、[MobiSys’26接收列表](https://www.sigmobile.org/mobisys/2026/accepted_papers/)、[SenSys’26海报列表](https://sensys.acm.org/2026/accepted_posters.html)、[SIGCOMM’25研讨会论文页](https://conferences.sigcomm.org/sigcomm/2025/workshop/papers-workshop-info/)。海报、研讨会、接收列表、预印本和正式论文分别标注，不能互相代换。未对这些场所完成所有年度目录的逐篇筛查；尤其TWC/INFOCOM的本轮结果不足以支持“没有直接相关工作”的判断。

选择核心资料的依据是：能直接约束总体构想、真实部署、模型/网络反馈、动态协议或规模评价中的至少一项，并有方法/评价原文可核对。传统MRTA、固定DAG与一般MEC卸载不再占主体；CoSMO因用户指定及其目标导向更新机制保留为模块级强对照。

访问限制与版本处理：NetLLM作者PDF的两个入口本轮超时，改读arXiv早期稿和官方仓库；部分IEEE页面直接打开返回418，采用出版社搜索返回的书目/摘要并用固定arXiv版本核方法。未取得的全文、设备部署和源码细节保留未知。所有列入2026的记录均已在2026-10-27前有官方原文或出版社记录；不以第三方宣称的未来卷期推定已完成出版或实验。

## 3. 核查口径

部署采用四种口径：P1为多实体设备各自执行模型；P2为共享硬件上的独立逻辑模型实例/上下文；P3为依赖远端模型API；P4为一个模型跨设备切分执行。它们可以混合，单有多节点或多策略角色不证明有多个独立模型进程。没有LLM/VLM运行的传统协议记“不适用”；综述中的部署选项记“设计”，不填成实测。

反馈按证据区分：架构提出的双向作用；仿真中网络/任务变化与策略相互作用；真实设备测得的控制效果。多跳也区分物理包转发、跨接触存储携带、固定两跳链路和多个LLM逻辑轮次。规模必须说明是无线节点、模型实例、接收者还是并发流。

## 4. 十二篇核心资料与版本

下表固定本轮所读版本，R编号仅用于本文导航，不改仓库既有P编号或BibTeX。

| ID | 一手原文与所读版本 | 核查定位 |
|---|---|---|
| R01 | Zhang等，[Mobile Embodied Agent Network (MEAN): Integrated Framework, Enabling Technologies, and Task-Driven Deployment](https://arxiv.org/html/2610.26297v1)，v1，2026-10-19 | §I–V、VII；框架、部署方式、指标及开放问题；综述 |
| R02 | Hu等，[LLM-Based Multi-Agent Systems over Wireless Networks: A Joint Agent–Network Design Perspective](https://arxiv.org/html/2609.37094v1)，v1，2026-09-29 | §II–IV、Fig.3–5；联合设计与V2X算例 |
| R03 | Jiang等，[AgentComm: Semantic Communication for Embodied Agents](https://arxiv.org/html/2604.13558v1)，v1，2026-04-15 | §II–IV，尤其IV-A与编码/消融；不同于R04 |
| R04 | Bansal、Gangwani，[AgentComm-Bench: Stress-Testing Cooperative Embodied AI Under Latency, Packet Loss, and Bandwidth Collapse](https://arxiv.org/html/2603.20285v1)，v1，2026-03-18 | §3–6、A.1/A.2；被测策略、CommChannel、规模与限制 |
| R05 | Liu等，[Agent-Native Wireless Communications: Architecture, Opportunities, and the Road Ahead](https://arxiv.org/html/2605.15873v1)，v1，2026-05-15 | §II–V；开放接口、RAN控制时间尺度、Agent-loop |
| R06 | Lee等，[Coordinated Networking for On-Device Agent-Augmented Real-Time Communication](https://arxiv.org/html/2607.22854v1)（HAFS），v1，2026-07-24 | §3–8，特别§7、8.1–8.3、Table1；真机与轨迹模拟分开 |
| R07 | Cladera等，[Air-Ground Collaboration for Language-Specified Missions in Unknown Environments](https://arxiv.org/html/2505.09108v1)，v1，2025-05-14 | §3.3、4、5、7.3及平台附录；实体系统和API依赖 |
| R08 | Qi等，[Update for Decisions, Not Freshness: Goal-Oriented Status Updating and Selective Offloading at the Network Edge](https://arxiv.org/html/2609.01082v1)（CoSMO），v1，2026-09-01 | §III–V-A1、实验指标；目标驱动更新及ns-3拓扑 |
| R09 | Tan等，[LLM-Empowered Agentic MAC Protocols: A Dynamic Stackelberg Game Approach](https://arxiv.org/html/2510.10895v1)，v1，2025-10-13 | §II–V、PAG、TableIII/IV、Fig.8；另见[2026 TMC记录](https://ieeexplore.ieee.org/abstract/document/11603302)，DOI 10.1109/TMC.2026.3712258 |
| R10 | Kim等，[Resilient LLM-Empowered Semantic MAC Protocols via Zero-Shot Adaptation and Knowledge Distillation](https://arxiv.org/html/2505.21518v1)，v1，2025-05-22 | §II–VI；控制信道假设、TPM/T2NPM/T3NPM、UE变化与切换 |
| R11 | Cladera等，[Enabling Large-scale Heterogeneous Collaboration with Opportunistic Communications](https://arxiv.org/html/2309.15975v1)（MOCHA），v1，2023-09-27 | §III–IV、TableI；原同步、真机无线选择及仿真规模 |
| R12 | Saboia等，[ACHORD: Communication-Aware Multi-Robot Coordination with Intermittent Connectivity](https://arxiv.org/html/2206.02245v1)，v1，2022-06-05 | §III–V、TableI、Fig.8；多层系统、实地Mesh及反馈行为 |

R09的TMC页面显示2026-07-13在线发表、卷期标为2026年11月；本轮方法和数值范围锁定2025 v1，未逐条比对期刊全文，不混用两个版本的收益百分数。R06按2026预印本引用，不据未复核的后续会议信息改变版本。R01明确是综述，其引用的第三方系统不是该文自己完成的统一测试床。

## 5. 部署、物理动态性与规模矩阵

“未知”表示所读材料没有足够证据；它不等于没有实现。表中的范围是本轮能准确定位的实验范围，不自动解释成系统上限。

| ID | 模型/设备部署 | 物理拓扑与控制组织 | 实际评价规模/载荷单位 |
|---|---|---|---|
| R01 | 设计讨论端—边—云、独立Agent及模型切分；无该文P1实例证明 | 综合讨论移动、分布式协作及资源编排 | 综述；无自身统一设备数/扩展曲线 |
| R02 | 架构中车辆Agent及RSU协调者；算例未给可确认的多端LLM执行记录 | 算例固定V2I星形，明确无V2V/D2D；联合拓扑在设计节提出 | Fig.3为V1–V3与RSU；不是移动多跳规模实测 |
| R03 | BS用Claude-Sonnet-4.5、机器人用GPT-4o；P3型闭源模型，调用/驻留细节未充分披露 | BS—机器人通信与多轮消息；编码链路仿真 | 仓储/清洁两个生成场景；OFDM、4-QAM、LDPC；非实体机器人群规模 |
| R04 | 被测实现为one-hot/argmax导航与网格融合，未提供LLM/VLM推理记录；P1–P4不适用 | 4个逻辑Agent、协调者、可配置损伤信道；不是物理路由仿真 | 20×20网格，3任务族、每损伤11档、每条件30回合 |
| R05 | 架构讨论多种部署，不能记作已实测P1 | O-RAN及开放控制接口、多层Agent-loop；非已验证MANET系统 | 架构论文；未给自身端侧设备/移动Mesh扩展实验 |
| R06 | P1端侧llama.cpp；交换KV支持远端预填充/本地后续推理，不等于只有一个拆分模型 | 5GHz Wi-Fi AP加SFU，RTP/SCTP协调；不是去中心化Mesh | Jetson Orin Nano、M3 Pro、Galaxy S25，逐次设备配对；另3–9并发上下文流，非3–9台设备 |
| R07 | 机载视觉/自治栈加GPT-4o API，P3混合部署，不能记成全端侧LLM | Rajant通信、MOCHA机会交换与携带；另有API中继 | 空地实体平台、7类语言规格、公里级任务；不是大规模模型节点曲线 |
| R08 | EN/SN学习策略；非LLM/VLM具身模型负载 | 4UE移动接入、1EN、1中继、1SN；固定EN–SN两跳点到点回传 | ns-3.42/ns3-gym；不能把两跳回传当动态多跳MANET |
| R09 | Llama3-1B协议actor/critic，服务器8×A800；逻辑BS/UE，独立端侧实例未证实 | BS领导/UE跟随，用户数及信道动态；单小区资源组控制 | 主配置3/4/5UE；Fig.8扩至2–10UE；不是2–10台LLM设备 |
| R10 | SOLAR-10.7B参与协议生成及蒸馏；实体驻留/独立模型进程未给出 | 单BS共享上行，独立控制信道；UE数变化 | 主要环境变化为2→3UE；分组到达与擦除模型，不是具身请求轨迹 |
| R11 | 自主机器人栈，非LLM；P1–P4不用于证明大模型部署 | 移动机会接触/存储转发；真机明确只做单跳交换，不能冒充Rajant多跳试验 | 真机1UAV+3UGV；TableI仿真1/2UAV×3/5/10UGV、不同通信半径 |
| R12 | 机器人本地自治，非LLM；真实设备网络证据强 | Silvus/Rajant类商用MANET，多跳、中继投放、失联与回报 | 实地最多6探索机器人；一次场测13个投放无线节点；无线节点不等于模型Agent |

## 6. 控制深度、反馈实证与需要比较的问题

本表区分论文实际提出的控制机制和反馈证据。剩余问题应通过相同信息、硬件与资源条件下的实验建立，不由“未同时填满所有列”推出创新。

| ID | 已覆盖的网络机制 | 反馈实证及本项目必须尊重的能力 | 后续比较所需的具体问题 |
|---|---|---|---|
| R01 | 任务编排、信息交换、无线资源与部署协同框架 | 感知—通信—决策—行动反馈已是框架中心；非统一系统实证 | 在框架之下定义一个可执行协议及动态服务指标 |
| R02 | 交互/资源、消息/传输、逻辑/物理拓扑、工作量/资源联合 | 固定拓扑算例比较agent-only、wireless-only、joint；不可说它只给概念无任何实验 | 在真实模型请求与移动多跳上验证局部可用信息、分布式控制成本和恢复 |
| R03 | 语义压缩、重要性保护、任务知识更新 | 信道失真可改变交互轮次及任务表现；已有应用—PHY耦合 | 把内容适配作为强构件；新增转发/竞争不应把其原收益冒充本项目收益 |
| R04 | 损伤注入、冗余发送、过时融合；未实现MAC/路由控制 | 已有系统化鲁棒性协议；实现不等于LLM生成真实通信需求 | 可借鉴损伤诊断，主网络失效应由物理/业务执行产生 |
| R05 | 控制权限、执行反馈、RAN时间尺度、状态版本/有效性接口 | 接口与双向作用已有直接先例；不能以新接口命名构成贡献 | 选定可实际执行的动作及协调时间尺度，测控制反应与额外开销 |
| R06 | 反馈引导的多流速率、上下文传输顺序与推理流水协调 | 真机/轨迹模拟均测端到端效果；应用引导传输并非空白 | 多跳动态与控制范围不同；比较时保留其合理多流协调和本地prefill替代 |
| R07 | 紧凑语义地图、RSSI触发交换、UAV通信携带/移动 | 取得新地图会改变任务规划；无需全量感知正文也可完成语言任务 | 真实模型产生什么请求必须实测，不能为压网强制传原始大模态或KV |
| R08 | 目标效用驱动更新/卸载、异步远端缓存、排队 | 已有ns-3和闭环学习，不能说它只做AoI或理想链路 | 原EN/SN角色与业务适用时可作模块对照；不是整套具身网络的默认任务 |
| R09 | PAG约束协议输出，PPO协调BS/UE，RBG动作与信道/MCS映射 | 已验证变UE数、信道、资源量和模型开销；不能只说“尚无人Agentic MAC” | 移动多跳与端侧执行另验证；推理周期、控制报文与资源语义须保留 |
| R10 | LLM协议适应、蒸馏、早期TPM到T2NPM切换，meta-resilience | 已将变化后的适应速度和计算折中作为目标；控制信道假定无错 | 不确定/有成本控制信道及多域环境下的有效性；不把混合快慢控制本身当首次 |
| R11 | 最新版本头交换、优先级请求、缓存转发及通信感知移动 | 接触和任务移动反馈已有真机；仿真也改变团队和半径 | 精确分开机会携带、路由多跳及真实竞争；以其原生能力作对照 |
| R12 | 分层传输、流控、网络指标上送、回连和自主投放中继 | 实地网络状态驱动行为，已有跨层与拓扑控制；Fig.8不同日期非严格配对 | 与合理中继/回连方案比较业务连续性、控制/运动代价及适应范围 |

两项需要防止误读的实现细节：R04 §5.1明确采用one-hot航点和argmax，导航/搜索中部分压缩、事件触发方法因此产生相同结果；这限制其对现代模型推理负载的代表性。R09 TableIII与§V-A的训练epochs记录分别为2000/3000，TableIV列GPU开销及模型比较；本轮不拼成可复现参数，不从5ms仿真TTI推定实体端侧LLM能在5ms完成在线控制。R09已有计算开销讨论，后续应核定端到端调度时限，而非声称它完全忽略推理开销。

## 7. 补充实证与强网络基线

### 7.1 重要补充资料的已核范围

**AgenticDTN**：[出版社摘要与书目](https://ieeexplore.ieee.org/abstract/document/11726473)，DOI 10.1109/RADIOELEKTRONIKA71189.2026.11726473，会议日期2026-09-02至04、上线2026-10-13。摘要报告16节点、双射频802.11s、3条并发UDP流；多LLM Agent经数字孪生验证后调整信道/路由，消除同信道竞争。它是实网Agent控制Mesh的直接先例。仅摘要核查，全文算法、每节点模型部署、移动/加入退出和扩展统计尚未知，不归入12篇方法深读，也不能因未知而弱化其真实网络控制证据。

**NetLLM**：[SIGCOMM’24作者官方仓库](https://github.com/duowuyms/NetLLM)与[arXiv:2402.02338v1](https://arxiv.org/html/2402.02338v1)。v1题名是 *Large Language Model Adaptation for Networking*，正式题名为 *NetLLM: Adapting Large Language Models for Networking*，DOI 10.1145/3651890.3672268。已核多模态编码、networking head、低秩适配及VP/ABR/作业调度用例；这是“用模型控制网络”的方法对照，不是多实体具身Agent组网实证。后续若做模型驱动控制，应与已有小模型/规则/学习控制比较，不能只换成LLM。

**其他检索近邻**：[MobiSys’26 Agent-X出版记录](https://doi.org/10.1145/3745756.3809195)可支持端侧Agent管线已有系统研究；本轮只定位，未深读其全部实现。[VLM-DC出版社摘要](https://ieeexplore.ieee.org/abstract/document/11668766)区分云边Agent与视觉编码器/云解码器切分，不能把P4带宽节省转记为独立P1组网。二者不作为已核动态多跳性能依据。

### 7.2 传统机制必须进入共同网络条件

| 问题 | 强机制与一手规范/实现入口 | 对照时必须保留的能力和费用 |
|---|---|---|
| 动态MANET可达性 | [AODV，RFC3561](https://www.rfc-editor.org/rfc/rfc3561.html)；[OLSRv2，RFC7181](https://www.rfc-editor.org/rfc/rfc7181.html) | 按需路由发现/局部修复与主动链路状态分别比较，计HELLO、拓扑扩散、RREQ/RREP、修复和队列中断；AODV为Experimental，OLSRv2为Standards Track |
| Mesh路由与拓扑维护 | [Babel，RFC8966](https://www.rfc-editor.org/rfc/rfc8966.html)；[Linux batman-adv](https://docs.kernel.org/networking/batman-adv.html) | 既有环路避免、邻居/路径维护不能省略；batman文档已明确更短维护间隔以开销换移动响应。固定实现和参数再比较，不能把静态最短路当唯一强对照 |
| 分区/间歇连接 | [BPv7，RFC9171](https://www.rfc-editor.org/rfc/rfc9171.html)及[PRoPHET，RFC6693](https://www.rfc-editor.org/rfc/rfc6693.html) | BPv7是存储转发协议规范，不是路由算法；PRoPHET是具体概率路由。后续比较复制/接触交换和缓存费用，分清规范与算法；本轮未恢复其运行栈 |
| MAC/PHY资源与干扰 | [ns-3 Wi-Fi官方设计](https://www.nsnam.org/docs/models/html/wifi-design.html) | 有DCF/EDCA、ACK/BlockAck、速率控制、传播/误码及OFDMA模型；采用成熟模型，不用“节点多就人为加延迟”代替竞争 |
| Agentic接入与变化适应 | R09、R10，以及普通规则/学习MAC | 保留信令、队列、信道、模型开销和非Agent基线；单小区原生复现与多跳机制适配分列 |
| 业务反馈与机会协作 | R06、R11、R12 | 保留流量调节、缓存/恢复、通信感知移动；不能通过关闭已有能力制造新方法优势 |

ns-3文档的OFDMA路径依赖AP侧MultiUserScheduler及相应帧交换，不意味着普通ad-hoc Mesh节点自动拥有等价的RU控制权限。仿真、COTS原型和SDR应分别声明控制面；正式执行前冻结ns-3版本、支持模块和网卡/驱动接口。本轮仅查官方文档，未验证本机已安装或可执行。具体选哪些基线由后续实验规划按架构定，不预先将所有协议机械叠加。

## 8. 文献支持的机制方向及证伪要求

以下是供架构/验证稿整合的研究约束，尚非最终算法方案。

**动态交互的网络服务连续性。** 区分Agent更换协作者、链路失效、路由重构及分区携带，观察交互什么时候还能继续、什么时候应改选可达来源或终止过期请求。需要把推理依赖映射到实际路径/转发服务，并与Babel/OLSR类维护、DTN和MOCHA/ACHORD比较。接口或双图只是记录工具，增益须来自具体的修复、缓存、源选择或控制扩散机制。

**需求—拥塞反馈和跨层资源控制。** 模型可请求补充视角、不同粒度结果或终止交互；网络根据局部队列、路径可达性和测得服务给出可用预算。要比较反馈是否减少无效交互与尾延迟，或只把工作转成额外推理。R02已提出联合设计，R03已有内容/PHY保护，R06已有流控，因此新的贡献需在真实模型交互、共享多跳竞争与控制信息付费后检验。

**多时间尺度的网络重构。** 慢层模型可以解释任务阶段/能力变化、提出路由或中继角色策略；快层必须用有界、可执行协议处理接入、MCS和转发。R09/R10已研究模型协议及变化适应，ACHORD已做移动中继反馈；候选必须明确新增协调规则、反馈时效与执行约束，不能把一个LLM放在多个既有算法上方就称统一系统。

这三类方向可以共享测量接口，但不要求同时实现。先证明真实模型通信是否呈现现有协议难以有效服务的特征，再选主要损失对应的机制。若传统强方案已经满足目标，应报告其达标区域，并依据成本、连续性或实现复杂度重新选问题，不能强制放大正文或压低带宽制造失效。

验证至少分开无线节点数N、运行模型设备/实例数N_A、区域/密度、路径长度、拓扑变化速度、请求强度和模态载荷。固定N_A扩转发节点只测无线规模；固定区域加密与固定密度扩区域分列。请求轨迹回放可隔离网络作用，模型闭环则检查网络反馈是否真的改变推理和业务；两者不能互代。具体模型、硬件、预算、变量和消融待E1-009/E2-010冻结稿整合，不在本阶段自行启动。

## 9. 尚未解决的证据缺口与交接

目前未验证：各候选在本机的代码/权重可用性；真实多端模型主动产生请求的负载；设备退出、失效与分区重连下完整网络的服务曲线；商用网卡的低层控制权限；算法在相同信息和控制费用下的净收益。文献的单域、单BS、固定拓扑、模拟Agent或API依赖分别记录，不把它们合并成笼统的“现有方法都不动态”。

需要后续补核的具体资料是：AgenticDTN完整方法/模型位置和移动实验；R09期刊版与v1的参数差异；R06后续正式出版及可复用代码；选定网络栈的路由/MAC版本与现实接口。TWC/INFOCOM/SenSys等场所本轮定向命中不等于穷尽，后续候选收敛后再补查对应机制，而不无限扩充泛综述。

本阶段将旧报告中的“同步恢复唯一优先路线”降回控制面模块；旧状态任务继续承担协议语义与历史回归。结合架构与验证交付形成的[总体方向修订](../RESEARCH_REORIENTATION_20261027.md)，统一给出完整模型、三个系统候选、强对照及A/B/C验证安排；[NEXT_STEPS](../NEXT_STEPS.md)维护当前计划。本文的R编号和固定版本保留，不改写原P编号或历史文献计数。
