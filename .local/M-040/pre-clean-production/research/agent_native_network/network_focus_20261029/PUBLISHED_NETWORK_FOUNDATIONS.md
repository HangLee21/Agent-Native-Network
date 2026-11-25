# 动态多跳网络研究的已发表论文依据

核查日期：2026-10-29。研究对象是移动、间歇连接和竞争无线信道中的多跳网络服务。端侧模型、推理资源和消息生成策略作为固定业务条件；研究变量是邻居与路径维护、逐跳转发、排队服务及控制消息。计算卸载、模型选择、推理加速和KV缓存不作为本轮贡献。

下面六篇提供协议与评价骨架，涵盖链路度量、路由修复、拥塞转发、广播维护和机器人机会通信。已有工作可以在相同问题上继续改进；可检验的性能、控制成本、复杂度或理论增量比“是否使用LLM”更有意义。各项“改进问题”都是本项目待研究的假设，不是对领域空白的断言，也不是已经实现的算法。

## 1. 发表身份与原文核查范围

| 编号与论文 | 正式身份的一手依据 | 本次核读文本与范围 | 可据此采用的角色 |
|---|---|---|---|
| F01，De Couto、Aguayo、Bicket、Morris，A High-Throughput Path Metric for Multi-Hop Wireless Routing | MobiCom 2003；[作者PDF](https://pdos.csail.mit.edu/~decouto/my-papers/mobicom03.pdf)首页会议/版权信息；[MIT作者组出版目录](https://pdos.csail.mit.edu/archive/_moved_to_git/pubs.html) | 作者提供的final-submitted版本；摘要、§3/§3.1度量与探测、实验概述、结论。不是2004博士论文；未逐图复核全部实验 | 路径代价、链路损失与逐跳费用基线 |
| F02，Gnawali、Fonseca、Jamieson、Moss、Levis，Collection Tree Protocol | SenSys 2009；[作者PDF](https://sing.stanford.edu/site/assets/publications/sensys09gnawali.pdf)首页；[作者论文条目](https://www2.cs.uh.edu/~gnawali/papers/ctpsensys2009-abstract.html) | 摘要、单/少汇聚点模型、§4控制面，尤其§4.1–4.3路由滞回与信标重置；未逐项复核全部测试床实验 | 数据面验证、自适应维护、稳定性/修复代价 |
| F03，Moeller、Sridharan、Krishnamachari、Gnawali，Routing Without Routes: The Backpressure Collection Protocol | IPSN 2010；[作者PDF](https://anrg.usc.edu/www/papers/IPSN10_Moeller_Sridharan_Krishnamachari_Gnawali.pdf)首页及[IPSN 2010程序](https://ipsn.acm.org/2010/program.html) | 摘要、§2权重与分布式近似、LIFO/floating queue说明、§5.2时延/规模结果及附录的已交付包口径；未独立重证定理 | 队列差驱动下一跳、拥塞感知与有限队列对照 |
| F04，Levis、Patel、Culler、Shenker，Trickle: A Self-Regulating Algorithm for Code Propagation and Maintenance in Wireless Sensor Networks | NSDI 2004；[USENIX正式条目](https://www.usenix.org/conference/nsdi-04/trickle-self-regulating-algorithm-code-propagation-and-maintenance-wireless)及[会议PDF](https://www.usenix.org/publications/library/proceedings/nsdi04/tech/levisTrickle/levisTrickle.pdf) | [作者HTML](https://csl.stanford.edu/~pal/pubs/trickle-nsdi04/)摘要、§4维护/冗余抑制/监听期及动态间隔说明；未核全部实验数字 | 一致时减少冗余，变化时加快传播的维护基线 |
| F05，Saboia等，ACHORD: Communication-Aware Multi-Robot Coordination With Intermittent Connectivity | IEEE Robotics and Automation Letters，7(4):10184–10191，2022；DOI [10.1109/LRA.2022.3193240](https://doi.org/10.1109/LRA.2022.3193240)；[IEEE条目](https://xplorestaging.ieee.org/document/9837416)与[作者机构库](https://publications.polymtl.ca/51257/) | [作者v1](https://arxiv.org/html/2206.02245v1)，2022-06-05，§II–V：Mesh、分类传输/流控、网络反馈、中继部署与地下实测。正式出版元数据已核，未逐字比对v1与正式版 | 真实机器人网络服务与通信感知行动的强系统邻近 |
| F06，Cladera等，Enabling Large-scale Heterogeneous Collaboration with Opportunistic Communications（MOCHA） | ICRA 2024，2610–2616；[作者官方仓库Citation](https://github.com/KumarRobotics/MOCHA)给出DOI [10.1109/ICRA57147.2024.10611469](https://doi.org/10.1109/ICRA57147.2024.10611469)与会议；IEEE网页要求脚本验证，未取得正式全文 | [作者v1](https://arxiv.org/html/2309.15975v1)，2023-09-27，§III同步与存储转发、§IV实机和仿真，尤其IV-C竞争模型；未逐字比对正式版 | 断连后的机会交换、信息积压与机器人规模评价 |

上述PDF/HTML均通过公开网页读取；本轮没有安装论文代码、运行环境或复现实验。网页可读不等于本地已保存论文文件。ACHORD与MOCHA的正式身份和作者稿机制分别核查，不把预印本年份当正式发表年份。BCP作者摘要网页的“IPSN 2011”与其年份字段冲突，采用论文页脚和2010官网程序，记为IPSN 2010。

## 2. 网络机制与可改进问题

### F01：将路径质量落实为逐跳传输成本

ETX以正反向交付率估算一次成功交换所需尝试数，链路代价为`1/(d_f d_r)`，路径代价求和；原文采用29节点802.11b测试床。原设计明确让度量独立于业务负载，负载均衡另行处理。[原文§3.1](https://pdos.csail.mit.edu/~decouto/my-papers/mobicom03.pdf)

继承：同时保留数据与ACK方向、真实重试及探测开销，比较最少跳数与质量度量。改进问题：链路样本有年龄、接触短暂且队列突发时，何时应继续使用较低ETX路径，何时值得付费修路？需要比较同等探测预算下的送达与修路开销；不能把ETX当完整干扰调度器或任意移动网络的吞吐最优保证。

### F02：利用正在传输的数据发现路由问题

CTP将数据面验证与自适应信标用于汇聚路由；路径切换使用滞回，拓扑正常时放慢信标，发现不一致时重置间隔。其维护具有具体控制规则，不能只概括为“定期广播”。CTP使用Trickle变体，§4.2明确`k=∞`，不能把F04的有限k冗余抑制直接记成CTP原实现。[原文§4](https://sing.stanford.edu/site/assets/publications/sensys09gnawali.pdf)

继承：区分被动数据验证、主动维护及滞回。改进问题：多目的业务下，能否只修复影响仍有用业务的局部路径，并限制稳定区域的重复维护？应与具备数据验证/自适应维护的强对照比较。原系统偏汇聚树；移植到任意源目的多跳网络需要明确定义目的状态和环路约束，不能直接宣称复现CTP。

### F03：把拥塞纳入逐包转发决策

BCP以队列差、链路服务率与使用代价构造权重，分布式实现近似选择下一跳；LIFO与floating queues处理时延及有限存储问题。原文将理想无干扰链路集调度与实际分布式近似区分。[原文§2、§5.2及附录](https://anrg.usc.edu/www/papers/IPSN10_Moeller_Sridharan_Krishnamachari_Gnawali.pdf)

继承：拥塞/代价感知转发、有限队列与吞吐—时延折中。改进问题：短接触、带截止消息和过时队列摘要下，如何避免昂贵的无效转发或热点？必须与BCP式强基线对齐信息与控制成本。LIFO的已交付包时延会遗漏滞留包；所有签发消息的到期/丢弃/截尾须同时报告。有限TTL/缓冲不证明长期稳定，也不能把理想调度理论结论转给普通Wi-Fi实现。

### F04：区分必要维护和重复维护

Trickle以随机发送、冗余计数及动态间隔交换代码摘要；监听期避免异步短监听引起的冗余广播。原问题是版本维护，不是路由或可靠业务传送。[原文§4](https://csl.stanford.edu/~pal/pubs/trickle-nsdi04/)

继承：相同状态抑制重复通知，变化时及时重置；将发现/维护代价单独测量。改进问题：移动隐藏终端、状态局部不一致或失联时，如何设置重置范围，避免全网同步突发？需比较固定周期、只自适应间隔、再加冗余抑制的消融。不能由该文特定密度结果推定任意多跳业务容量。

### F05：以真实Mesh及分类服务作为机器人网络对照

ACHORD把商业Mesh、数据分层、可靠传输与流控、网络测量和通信感知行动结合；作者稿含选择重传ARQ、token bucket以及中继部署反馈，实测包括地下探索。[作者稿§III–V](https://arxiv.org/html/2206.02245v1)

继承：分类业务、有限服务预算、回连积压控制和实际网络反馈。改进问题：固定移动轨迹与计算条件后，网络维护和转发规则能否改善多源交互的及时交付与控制成本？与其完整可靠/限速能力比较；部署新中继的收益须和额外设备、移动/覆盖代价分列。商业Mesh内部MAC/路由不可见，不能把复用其接口写作已实现同款底层协议。

### F06：保留机会存储转发的有效能力

MOCHA通过本地数据库、消息头与P2P同步传播最近信息，允许存储转发，并向规划层提供通信指标。作者稿IV-C仿真采用单次仅一节点发送的竞争约束，原文也指出实机可能存在空间复用；因此该规模结果不能替代一般无线Mesh容量结论。[作者稿§III–IV](https://arxiv.org/html/2309.15975v1)

继承：断连缓存、按实际接触交换、头部/正文分开计费。改进问题：有可用多跳路径和仅间歇接触两种服务如何衔接，避免重复摘要与过期正文占用接触窗口？需要与保留最新信息、存储转发及限速的MOCHA式对照比较。不能将其降格为简单FIFO；最新主题状态与不可丢的独立请求对象须分开定义。

## 3. 从依据到网络研究骨架

| 研究环节 | 主要继承 | 固定条件下的可控量 | 需要回答的比较问题 |
|---|---|---|---|
| 路径与恢复 | F01、F02 | 路径代价、滞回、修复触发/传播范围 | 同业务与轨迹下，减少中断或维护成本是否值得额外探测？ |
| 拥塞与服务 | F03、F05 | 下一跳、入队/发送次序、速率与丢弃规则 | 相同签发负载下及时有效交付能否提高，是否牺牲弱流/旧消息？ |
| 控制扩展 | F02、F04 | 信标间隔、冗余抑制、事件重置范围 | 加密与扩区分别怎样改变每次有效交付所需控制空口？ |
| 断连与机会交换 | F05、F06 | 存储转发、摘要范围、接触内优先级 | 路径恢复与机会接触分别能服务多少仍有效的业务？ |

近期宜先比较一项网络改变：在成熟路由/转发上，研究带年龄的局部网络信息如何触发有界维护，及其对有效交付和控制空口的影响。它是待比较候选；是否优于自适应信标、拥塞感知转发及机会同步，要由共同无线栈和同条件实验决定。不得仅因重新命名或组合既有机制就宣称新贡献。

B线可以先使用明确定义的合成业务，固定源目的、签发时间、正文大小、截止、优先级和轨迹，检验路径、干扰、队列和控制维护。A线继续修复JSON工具协议并准备真实业务轨迹；真实轨迹取得后再做外部业务验证。合成网络机制实验不等待JSON成功，但也不能声称产生了自主Agent需求。计算时延/资源对各方法固定或使用同一记录，网络收益不能来自少推理、换模型或加算力。

网络实验至少分别评价固定面积加密、固定密度扩区、负载增加与变化速率；报告无线节点数与实际模型端点数、及时有效交付、全部失败、成功时延、控制/重试/ACK空口和恢复空窗。不得用成功子集时延掩盖未交付，也不得以小型受控两跳结果推网络扩展边界。本轮仅建立文献依据，无新增实验或改进效果结论。

## 4. 邻近预印本单列

| 工作 | 本次一手核查 | 在当前框架中的用途 |
|---|---|---|
| Hu等，LLM-Based Multi-Agent Systems over Wireless Networks: A Joint Agent–Network Design Perspective | [arXiv:2609.37094](https://arxiv.org/abs/2609.37094)，v1，2026-09-29，页面标注Submitted to IEEE Wireless Communications；本次核摘要/元数据，未新增全文精读，未核实正式录用/出版 | 联合交互/网络设计的邻近观点；不承担已发表协议骨架，也不把“已投稿”等同已发表 |
| Jiang等，AgentComm: Semantic Communication for Embodied Agents | [arXiv:2604.13558](https://arxiv.org/abs/2604.13558)，v1，2026-04-15；本次核摘要/元数据，未核得正式会议/期刊出版凭据；arXiv DOI不是正式期刊DOI | 消息语义处理的邻近工作；本轮固定消息/模型条件，不把内容压缩当网络机制改进 |

“未核得正式发表”只陈述本次核查范围，不断言作者没有其他版本。若后续出现一手正式出版凭据，再按新版本补充；本次六篇骨架不依赖这两项的发表身份。
