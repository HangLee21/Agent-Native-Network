# 检索、证据与一致性记录

执行日期：2026-10-20，Asia/Shanghai。只保存书目、摘要性核查和链接；未批量下载 PDF。未执行任何论文代码。

## 1. 仓库与执行环境

当前路径 `D:\LLM_Project\Agent-Native Network` 起始为空，无已有研究资料可复用。向上查找 `D:\AGENTS.md`、`D:\LLM_Project\AGENTS.md` 及本目录说明未发现文件。Git 实际根目录为 `D:/`，初次状态读取被所有权保护阻止；通过命令级 safe.directory 参数完成检查，没有写入全局配置。第一次含重复相对路径的状态命令产生路径警告，随后用 `git -c safe.directory=D:/ status --short -- .` 重做，起始无输出。

系统 Python 3.14.5 的 HTTP 依赖不完整（requests 未安装，urllib 间接依赖 ipaddress 缺失），未安装依赖；改用 PowerShell Invoke-WebRequest 读取 arXiv HTML citation 元数据和 Crossref JSON。临时元数据位于系统 TEMP，不进入项目。写作采用本地 research-writing-skill。

## 2. 检索方法及范围

纳入研究窗口以2023–2026为主，保留时效、稳定性和单模型切分的必要早期对照。按标题/arXiv/DOI合并版本，paper_id唯一。先核实用户提供三篇，再扩展命名工作及原文参考文献，最后补机制基础与实验平台官方文档。

| 批次 | 实际查询/入口 | 结果与处理 |
|---|---|---|
| Q1 | 用户三个arXiv链接，Reasoning-Native、LLM2Swarm | P01–P04/P10；原文方法与实验核查 |
| Q2 | RoboTalk、CoMuRoS、CoELA、RoCo | P06–P09；剔除同名机器人软件/学位论文等误匹配 |
| Q3 | Agent-Native Wireless Communications；wireless context engineering | P05/P11；发现版本、有效期、接口已有直接先例 |
| Q4 | edge agent survey、LLM agents edge-cloud | P19/P12；可访问IJCAI官方记录 |
| Q5 | AgentPrune、G-Designer及P01参考文献 | P13/P14；记录逻辑图与物理路由差异 |
| Q6 | Age of Information survey、gossip、incorrect information、Tassiulas stability | P15–P17/P21；必要机制基线 |
| Q7 | Petals、USENIX LLM edge NSDI | P18/P20；查看NSDI 2026目录，未把训练/服务集群论文大量纳入 |
| Q8 | site:ieeexplore.ieee.org multi-agent LLM wireless | P22、无线决策综述等线索；P22纳入，其他未做全面阅读 |
| Q9 | site:dl.acm.org agent wireless MobiCom；OpenReview题名 | ACM定向搜索未获得足够可核实直接条目；OpenReview论坛有浏览器挑战 |
| Q10 | ns-3 OFDMA MultiUserScheduler、Linux mac80211 injection | 原型可控性依据；不计入论文数 |
| Q11 | ICLR proceedings题名、PMLR G-Designer、AoI/AoII/Gossip DOI、ACL Petals | 补齐七篇正式发表记录；另见HyperCluster模型切分线索，已有P18对照故未扩充 |

本轮完成 **22篇纳入记录，10篇核心原文核查**。不报告未经逐条计数的总命中数和排除数量。检索并未逐年穷尽 ACM/IEEE/ICLR/NeurIPS/ICML/ICRA/IROS/CoRL/MobiCom/MobiSys/SenSys/NSDI/SIGCOMM/INFOCOM/TMC/TWC/IoT-J；不能据此作“全球首次”判断。

前向/后向扩展证据：P01参考文献明确链接 AgentPrune、G-Designer 和推理通信方向；P04引用 wireless context engineering；CoMuRoS相关工作表含CoELA/RoCo；LLM2Swarm引用CoELA/RoCo。前向引用仅做标题检索和已取得文献的交叉阅读，尚未通过Semantic Scholar/OpenAlex建立完整引用图。

## 3. 核心证据定位

| ID | 证据位置 | 核查要点 |
|---|---|---|
| P01 | [§IV](https://arxiv.org/html/2609.37094#S4)；Fig.3–4 | 固定RSU、无D2D、仿真对比 |
| P02 | [全文](https://arxiv.org/html/2604.13558)，§III-A/IV-A | BS/机器人角色；闭源模型；OFDM编码设置 |
| P03 | [全文](https://arxiv.org/html/2610.02161)，§4/4.1 | A100评估与Qwen3-VL/动作模型 |
| P04 | [全文](https://arxiv.org/html/2602.17738)，§V-B | 有报告的仿真数字，但复现配置不足 |
| P05 | [全文](https://arxiv.org/html/2605.15873)，§IV-B/C/V | loop/version/validity、接口与无线控制 |
| P06 | [全文](https://arxiv.org/html/2609.23997)，§IV训练评估 | 共享vLLM、独立上下文；leader-follower |
| P07 | [全文](https://arxiv.org/html/2511.22354)，§III/IV；[项目](https://comuros.github.io/) | 中央Task Manager；实体机器人与API配置 |
| P08 | [全文](https://arxiv.org/html/2307.02485)，§3/5.2 | 无噪声广播；主实验OpenAI API |
| P09 | [全文](https://arxiv.org/html/2307.04738)，§3.3/5.1；[项目](https://project-roco.github.io/) | 集中运动规划、GPT-4、UR5演示 |
| P10 | [全文](https://arxiv.org/html/2410.11387)，§3.2/3.3；[代码](https://github.com/Pold87/LLM2Swarm) | 明示模拟本地执行，外部GPT-4o |
| P11 | [v2全文](https://arxiv.org/html/2602.07321v2) | 与搜索索引v1作者列表不同 |
| P19 | [IJCAI官方记录](https://www.ijcai.org/proceedings/2026/858) | 正式Survey Track、作者及DOI |
| P20 | [USENIX官方记录](https://www.usenix.org/conference/atc25/presentation/tian) | 正式ATC 2025及官方BibTeX |
| P21 | [作者机构报告](https://drum.lib.umd.edu/items/571fda52-aefb-4497-9a2d-69d8c7c907b9)；Crossref | 1992与DOI核对 |
| P22 | [IEEE记录](https://ieeexplore.ieee.org/abstract/document/11726473)；Crossref | 16节点双射频Mesh来自摘要，不等同全文核查 |

## 4. 书目版本与冲突处理

18篇arXiv记录直接从官方HTML的citation_title/citation_author/citation_date读取，避免手工补作者。P11搜索索引保留v1的八作者列表，而当前官方v2及元数据为六作者；本目录采用v2，不能混用旧作者。

P04 DOI `10.1109/MNET.2026.3721818` 通过Crossref题名、年份、容器、作者交叉确认，记为IEEE Network期刊记录；卷期页码未核实，不补写。其arXiv方法版本和期刊最终版本可能有差异，本轮解读依据所链接arXiv文本。

P09 正式ICRA 2024记录及DOI经[IEEE页面](https://ieeexplore.ieee.org/document/10610855/footnotes)核实，year采用2024，first_year为2023。P10经作者README确认NeurIPS 2024 Open-World Agents **Workshop**，不记作NeurIPS主会。

OpenReview直接论坛触发浏览器验证后，改从官方会议录补核。P08确认为ICLR 2024，P13为ICLR 2025，P14为ICML 2025；已同步CSV/BibTeX。正式来源如下：

- [CoELA：ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/54b8b4e0b4ba4aad112e84f32e3b5dbb-Abstract-Conference.html)
- [AgentPrune：ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/bbc461518c59a2a8d64e70e2c38c4a0e-Abstract-Conference.html)
- [G-Designer：PMLR/ICML 2025](https://proceedings.mlr.press/v267/zhang25cu.html)
- [P15：MIT作者机构记录，JSAC 2021](https://dspace.mit.edu/entities/publication/ca039de7-e561-4a0f-bd3a-b92d0c436020)
- [P16：TCOM 2025](https://ieeexplore.ieee.org/document/10893697/)
- [P17：TWC 2023卷期，2022在线发表](https://ieeexplore.ieee.org/document/9921185/)
- [P18：ACL 2023 System Demonstrations](https://aclanthology.org/2023.acl-demo.54/)

P13正式会议页使用Jeffrey Yu，arXiv使用Jeffrey Xu Yu；P18官方ACL元数据使用Maksim Riabinin，arXiv及PDF有Max Ryabinin写法。本目录正式引用遵循所选会议记录，同时保留arXiv关联，不把姓名变体当成新论文。其余未取得正式发表证据的条目仍保守引用预印本。

P21二级检索出现1993日期，但作者机构报告和Crossref的出版年为1992，以后二者为准。P22通过Crossref确认四位作者与2026会议；IEEE直开有Internal Error，但搜索工具可返回官方摘要，不计作全文读通。

P04、P21、P22的Crossref检查入口分别为：

- [P04 Crossref](https://api.crossref.org/works/10.1109/MNET.2026.3721818)
- [P21 Crossref](https://api.crossref.org/works/10.1109/9.182479)
- [P22 Crossref](https://api.crossref.org/works/10.1109/RADIOELEKTRONIKA71189.2026.11726473)

arXiv DOI 与期刊DOI不同。本目录CSV缺失DOI写“未核实”，BibTeX省略该字段，不把推算的arXiv DOI伪装为已核实正式出版DOI。未核实代码链接不猜测；有作者项目入口但未检查仓库时不视为代码验证。

## 5. 分类与证据等级

A必须同时具备独立模型Agent、受限网络机制以及可确认实体端侧部署；初始22篇为0，问题审查新增P26后为1。B纳入模型协作/Agent-Network工作，即便执行集中或物理部署未知。C收录时效、队列、上下文和网络机制基础；D只保留必要部署/切分/综述对照。P22暂为B，待核实部署，不从“无线节点数”推断“模型实例数”。

E1：书目与摘要；E2：方法、系统、实验段原文；E3：在E2基础上额外看作者代码/配置说明。本轮E3不包含运行测试。CSV verification_status对元数据、方法和部署分别描述，不使用一个“已核实”掩盖所有未知。

## 6. 未完成事项及访问限制

1. P22全文与实际LLM部署、推理后端、控制接口尚未核实，是当前最重要缺口。
2. P04的仿真器、代码、模型部署和期刊最终正文需要进一步核对；不能据其“high-fidelity”措辞赋予充分可信网络验证。
3. 部分正式发表版本/DOI仍待核实；需要官方会议录或期刊记录，不能只抓arXiv首次年份。
4. 尚未穷尽2025–2026无线MAC、消息撤销/DTN、跨层控制工作；需要补充标题/摘要筛选及引用图。
5. 本机网卡和ns-3未检查或安装；普通Wi-Fi的RU可控性目前只是严格保守假设。
6. 本轮没有任何应用任务成功率、通信性能或能耗实验结果；方案中的数值仅为计划和约束设定。

## 7. 轻量校验

完成后核对CSV必需字段、paper_id/arXiv去重、BibTeX key一一匹配、Markdown本地链接、核心文献引用及文件数量。在线核查主要依赖正文与官方元数据读取，不将链接存在解释为其全部技术断言成立。

实际检查结果：8个文件，22条CSV记录、22个唯一BibTeX key；25个用户必需字段齐全，实际31列；18个arXiv编号无重复；文档内本地链接无缺失，代码围栏成对，未发现乱码替换字符。CSV与BibTeX年份、已知DOI一致。分类为A=0、B=13、C=5、D=4；E2/E3核心阅读共10篇。目录约92 KB，无PDF、模型权重或仿真输出。

三条已收录代码URL（CoMuRoS、LLM2Swarm、EC2-Bench）均经HTTP GET返回200；仅确认可访问，不代表已执行或核实全部实现。公式人工检查了bit/秒/Hz/W/J量纲、队列守恒、目的端吸收、有限缓存、半双工与取消竞态。未进行Mermaid图形渲染或LaTeX编译，也未宣称数学性质得到证明。

## 8. 问题存在性定向审查（2026-10-20）

用户要求先证实问题强存在。因此将选题判断从“机制组合空缺”调整为“实际损失—原因—已有解决—剩余问题”，暂停把架构设想作为立项前提。

检索簇包括 DARPA SubT communication lessons、ROS 2 wireless experimental performance、multi-robot LLM latency/communication、on-device agent coordinated networking。先读系统失败与通信部署，再追踪反例和解决方案；本轮非数据库穷尽检索，不能据此估计全领域发生率。

纳入五篇原始研究 P23–P27。arXiv 官方 citation 元数据核实标题、全体作者、首次日期和标识；重点核查范围见 CSV。正文均通过官方 arXiv HTML 读取，未批量下载 PDF。P23/P24 是现场部署，P25 是实际无线加注入故障，P26 区分真机测试与轨迹仿真，P27 是野外应用且 LLM 调用在云端。E2 表示读到方法/系统/实验，不代表复现。

补充来源与限制：

- P27 正式期刊及 DOI 由[作者项目页](https://tfr-air-ground.fcladera.com/)核实；阅读了[作者仓库首页](https://github.com/KumarRobotics/lang-air-ground-teaming)，但未深入源码，保留 E2。
- P26 的 [USENIX NSDI27 条目](https://www.usenix.org/conference/nsdi27/presentation/lee-goodsol)已发现，页面可读内容不足，未将 2027 会议记为已出版论文；引用已核实的 2026 arXiv。摘要 HFS/HAFS 名称不一致，正文统一 HAFS。
- [LLM 多机器人综述](https://link.springer.com/article/10.1007/s10514-026-10257-4) §6.3/7.1 作为引用追踪入口。其指标缺失讨论仅支持测量不足，不支持网络瓶颈已经成立；据此找到 P27，最终技术判断回到原始论文。
- [Swarm Robot Communications in ROS 2](https://www.diana.uma.es/publications/) 作为后续交叉验证线索；作者页核实 DOI 10.1109/ACCESS.2024.3470254，但本轮未完成实验段核查，未混入五篇证据。
- P25 表头出现 Kb、正文使用 KB；记录采用 §V-B 明确的 KB，保留此排版差异。不能从其 RELIABLE/KEEP_ALL 配置推断所有发行版的默认行为。

本轮修正严格 A 类计数为 1（P26），八条件全部满足计数仍为 0。前述第7节为初始版本检查记录；更新后为27条文献、27个BibTeX key，分类A=1/B=14/C=8/D=4；初始10篇核心核查另加5篇问题定向核查。未运行模型、网络实验或源码；新增的“门槛”和“停止条件”是后续方法建议，非已获得结果。

## 9. 现场故障与现有解决方案追踪（2026-10-20）

新增 P28 MOCHA（arXiv:2309.15975）与 P29 ACHORD（arXiv:2206.02245），核查原文方法和实验；标题、作者、预印本年份读取官方 citation 元数据。正式发表存在引用线索，但本轮未完整复核出版元数据，BibTeX 继续引用所读预印本，不用被引年份替换首次年份。

P27 补读 §5.2–7.1，区分云 API 失败、里程计失败、可通行性瓶颈和协作信息收益。P28 补读 §III–IV，区分交互完成率与任务及时性，标记现场单跳接触和模拟信道简化。P29 补读 §III–V，区分失联时段与包延迟，标记 Fig.8 跨日比较混杂。原文来源和定位均见问题审查 §0.6，未从第三方自动摘要抄录性能归因。

通过 GitHub API 读取 MOCHA 默认分支树；直接假设 main 的首个请求返回404，随后读取仓库 default_branch 后成功。记录快照 `bfbde0d186d77278085b25a365bf735d5acdc6bd`，读取 database.py、synchronize_channel.py、topic_configs.yaml 中相关实现；未执行、克隆或安装依赖。P28 评为 E3，仅指额外源码核查，不能等同于复现或确认论文版本一致。

没有取得原始现场时间序列，也没有量化本项目任务在强基线之后的剩余损失。未将库内 TODO 当成研究问题，未将低完成率全部归因于网络。后续所需事件表已更新 NEXT_STEPS。

当前29条文献、29个引用key，A=1/B=14/C=10/D=4。八条件全部满足计数仍为0。前两轮的22/27条数字保留为历史检查记录。

## 10. 找矿流程及反馈价值核查（2026-10-20）

用户确认：设备平台已具备，协作流程未确定；传感载荷、端侧算力、链路可后期确定或改装。不得把建议流程记成实验室已有事实。新增 P30–P32，D类从必要部署对照扩展为必要应用/部署对照。

检索围绕 UAV hyperspectral mineral ground validation、adaptive sampling robotic prospecting、legged robots scientific exploration，排除将厂商宣传收益作为科研实测。P30的出版网页遇429、PDF读取失败，保留机构原始摘要与Crossref元数据，评级E1。P31取得AAAI原始PDF并阅读方法/实验，确认高分辨率航空数据代理原位测量；P32取得arXiv接受稿全文，确认人工控制室延迟和低毫秒机间通信的区别，均为E2。

三篇标题、完整作者、正式年份、DOI及刊物用Crossref works接口核对；P31末位作者按正式记录保留Anatha Kiran，未自行纠正拼写。P32正式题名与arXiv大小写不同，采用出版元数据。文献书目32条，分类A=1/B=14/C=10/D=7，严格A计数未变。

另发现 [Autonomous science during large-scale robotic survey](https://doi.org/10.1002/rob.20391) 的出版社摘要，作为进一步追踪的现场自适应勘查线索；未阅读完整方法，不纳入本轮三篇主证据，也未引用未核实收益数值。

本轮产出为任务需求分析与四组对照设计，未获得现场日志或运行性能。下一阶段应先检验反馈价值，再测量网络影响，不以地外延迟、全量光谱广播或人工高频协商制造瓶颈。未下载模型、安装软件或改装设备。

## 11. 文献确定任务与仿真优先路线（2026-10-20）

按用户要求，顺序更新为文献确定任务、初步仿真检验存在性、理论模型与算法、后期实机验证。取消把大量现场测试作为启动前提；NEXT_STEPS 的旧工程方案标为备选。

新增 TASK_DEFINITION.md，确定资源约束下的地表矿物协同勘查任务；明确无人机区域先验、地面近距离观测的拟议分工，以及终局汇总公平性、隐藏真值隔离和评价代理的边界。设备与载荷未确定的用户事实保持不变。

复核 [P31 作者机构原始 PDF](https://publications.ri.cmu.edu/storage/publications/pub_files/2015/0/Thompson_2015_SpatioSpectral.pdf) Results/Table 1/Conclusion：自适应重规划较静态科学计划的额外收益有限。该反证加入任务与对照设计，避免将采样优化收益冒称通信收益。另复核 P30 机构摘要及 P32 作者预印本页面；不升级 P30 的 E1 评级。

文献数量仍为32，未新增书目。未执行模型、仿真或硬件测试；当前产出支持进入数据与模拟器选型，不构成网络瓶颈、新算法收益或 Agent 特有性的实验证明。

## 12. Python/SimPy 工程先导实验（2026-10-20）

用户授权按任务级仿真方向初步推进。核查 [SimPy 事件 API](https://simpy.readthedocs.io/en/latest/api_reference/simpy.events.html) 与 [JPL 数据页](https://aviris.jpl.nasa.gov/data/free_data.html)。Cuprite 旧 FTP 在当前环境返回 502，同路径 HTTPS 返回 404，UPV/EHU 镜像返回 403；没有取得真实影像，不把数据页面当成完成数据核验。

建立隔离 .venv；未修改缺失标准库模块的系统 Python。实现任务、紧凑观测、可靠字节队列、断续接触、终局公平汇总与固定留出评价。真实数据接口要求来源、使用条件、预处理记录，禁止 pickle。默认仅使用合成场景，所有时间和通信参数标为未经实测校准。

本轮最终运行 2 种先验 × 24 个配对种子 × 7 条件，共 336 次；11 项因果、边界与输入检查通过。理想共享未展示优于本地自治的稳定改善，良好链路与理想共享的任务误差一致；更基础的限制是采样后简化估计器的平均误差高于仅使用先验。完整快照与解释见 [simulation/results](../../simulation/results/2026-10-20-synthetic-v1/INTERPRETATION.md)。

指标是轻量残差插值的留出光谱 RMSE，不是 P31 解混方法的复现，不是矿物识别准确率。当前结果只说明原型可运行，不能支持真实找矿瓶颈或 Agent 特有性。下一步先补数据和应用估计基线，暂不搭建新理论模型。文献数量仍为 32。

## 13. Cuprite 获取与观测价值初查（2026-10-20）

从 [Settembre 等正式论文](https://doi.org/10.1186/s40323-025-00313-6) Data availability 核实作者仓库链接，成功获取固定提交的 Cuprite MAT、README 和许可证。复核 P31 Experiments/Method 的航空数据代理与线性混合构件；本轮不声称完整复现。数据论文作为本轮来源引用，尚未加入原32篇网络/任务综述集合。

原始数据为188×47500，元数据nRow=250/nCol=190，与README概述有差异。原始索引3出现6724个异常大值，删除该波段；187维谱逐像元L2归一化。未取得可靠中心波长、缩放与地理配准，故不用作绝对反射率或实际航程。固定提交、校验和、使用条款及质量处理均记录于 [方案](../../simulation/OBSERVATION_PROTOCOL.md)，不再分发原始数据。

以人工9通道观测和开发区4条校准光谱为共同起点，比较0/4/8/16/32次额外测量、三种采样规则、三种观测条件、三个区域和12个种子。得到1620条评分记录（包含确定性重复，非独立实地样本）。带噪声光谱覆盖的32次测量使三地区归一化光谱RMSE相对初始库降低31.27%、17.46%、40.28%；仅增加原低维信息派生的库列没有改善。所有预算和不利结果保留。

15项代码检查通过。初步结论仅是规定代理设定下的补充观测价值；不能推断途中共享、无线瓶颈或矿物识别收益。下一步先加入任务行程预算和采样基线，再评价多节点共享。结果解释见 [Cuprite 初查](../../simulation/results/2026-10-20-cuprite-observation-v1/INTERPRETATION.md)。

## 14. 行程预算与途中共享（2026-10-21）

固定上轮数据、评价区、初始校准库和NNLS估计器，新增未校准网格移动、采样/决策时间及终点约束；运行前设定单节点3条件、双节点4条件、2预算、2噪声和12种子，在3区域共执行1008次。无噪声种子为确定性重复，不作为独立实地样本。

22项代码检查通过；全部节点按预算抵达终点。导出校验发现同名nodes字段覆盖轨迹，修复后重跑，1008条任务指标与原运行一致，最终快照保留node_runs完整记录。源代码、参数、原始指标和种子0事件均归档。

带噪声双节点B区紧预算下，理想共享对本地策略平均误差改善5.37%，对联合静态方案改善2.63%；A区没有同样的正向变化，C区宽预算下对本地策略为-2.70%。完整结果见 [报告](../../simulation/results/2026-10-21-cuprite-route-v1/INTERPRETATION.md)。不以单一区域或只对弱最近点基线的优势宣称普遍共享需求。

规划器只利用9维投影更新覆盖，尚未直接利用高维证据重估矿物解释不确定性；这限制本轮正负结果的外推。下一步先检查起终点稳健性和文献反馈规则，尚未运行受限无线网络或设计新理论机制。文献集合仍为32篇，本轮未新增检索论文。

## 15. 共享收益的布局稳健性（2026-10-21）

执行前固定12种分区轴/边界/正反起终点，保持估计器和采样规则，完成5184次执行。25项检查通过，432条原布局记录复现。B区紧预算跨布局对本地平均改善1.99%、对静态1.24%，仅7/12布局同时占优；所有负例保留。详见 [结果](../../simulation/results/2026-10-21-cuprite-geometry-v1/INTERPRETATION.md)。

高维投影不可见扰动检查确认现有9维覆盖规划器的信息使用限制；不等于已证明更复杂规划器必有收益。本轮无新增文献，集合仍为32篇；无无线受限实验。下一步核查有文献依据的观测反馈机制，不因局部收益直接建立网络理论。

## 16. 反馈文献、因果审计与空间混合（2026-10-21）

本轮按“观测如何改变决策”检索并核查原始来源，新增P33（出版商/机构摘要，E1）、P34（作者workshop原文§2–4，E2）、P35（机构出版书目和arXiv v1 §II–V，E2），集合35篇。P35正式版与预印本未逐字比对，未将二手检索结果中的DOI写入已确认字段。SGP-Tools教程列为实现线索，未安装或复现，不赋予E3。多个CMU PDF地址发生超时，P35改读作者arXiv原文；P33保持摘要级。来源链接集中于 [机制审查](FEEDBACK_MECHANISM_REVIEW.md)。

先保存FEEDBACK_AUDIT_PROTOCOL再运行：1728组full/compact/preplanned比较，full指标全部复现旧快照。9维投影完全复现完整谱；72种不同无噪声条件（864条重复种子记录）由出发前计划复现。噪声下B区紧预算对更强静态方案平均为−1.06%，不是过去对旧static的+2.63%。两者对照不同，不覆盖历史结果。

依据空间混合动机另保存SPATIAL_MIXING_PROTOCOL，固定1/2/4/8块均值、12布局、3区域、2预算，无噪声1种子、有噪声6种子，2016组/8064评分。尺度1的1008条ideal/preplanned对应指标与因果审计完全一致；有噪声非平凡混合18组合只有1个组合超过半数布局同时胜过3种对照，不将此描述量当作显著性门槛。

30项检查通过，数据与源码哈希核验，轨迹/所有负例归档。结果支持暂停当前覆盖策略网络分支；不支持否定现实空地找矿，也没有开始无线受限模拟或新理论。用户要求连续推进，已在同轮完成文献、审计、追加机制检查和阶段决策。

## 17. 救灾方向独立筛查（2026-10-21）

按用户新问题核查NIST TN1545官方摘要、NIST IR8243摘要/引言/测试框架、DARPA官方任务、P29现场通信结果及OSRF SubT官方仓库。来源和限定见 [救灾筛查](RESCUE_TASK_SCREENING.md)。将“搜索发现回报”列为更直接候选，未将地下竞赛等同火场，未把1058秒失联当作包时延。未安装模拟器、未执行救灾仿真、未提出新算法；论文主表仍35篇，报告与任务来源单列。

## 18. 救灾发现回报先导与返回周期补查（2026-10-21）

核查OSRF官方API的报告/确认、传感器及中继接口，和Communication Model Tutorial的拓扑/距离启发式与保真度边界；链接见 [任务定义](RESCUE_TASK_DEFINITION.md)。未安装SubT，未把官方示例速率当实测值，论文计数仍35。

运行前保存RESCUE_REPORT_PROTOCOL，执行5184次，两支路合成几何、24种子、全连通/小消息负对照和六种已有策略近似。随后固定RESCUE_RETURN_PROTOCOL，另执行5184次60/120/240秒周期，1728条120秒记录复现；种子0–7选择周期、8–23留出。35项代码检查通过，原始分层、种子0事件、源码哈希及全部周期均归档。

结果：摘要优先组全部已发现目标在截止前交付，首次可达后平均等待约1.00–1.03秒；主要残差是失联等待。周期/中继存在搜索与回报取舍，不能据弱FIFO差距提出新调度算法。后续验证公开建筑拓扑及更充分既有连通性基线，不宣称Agent或火灾现场新结论。

## 19. 公开城市拓扑与强返回对照（2026-10-21）

读取OSRF官方Communication Model Tutorial；下载固定提交083c6a8acb0c25aa1a35e34517e628cd3b52ae77的urban_circuit 01–08 DOT及LICENSE/COPYING。只复用图，不将visibility标签解释成物理距离。下载清单与SHA256归档。论文主表仍35篇，本轮未新增文献条目。

运行前固定RESCUE_GRAPH_PROTOCOL，执行12672次，开发种子0–7、留出8–23。加入机会携带、返回基地、最近覆盖点和待报数量触发，全部候选保留。结果后增加沿实际轨迹即时回报AUC作为解释性分解，未用它选参。40项测试通过，全部12672行的因果分解、全覆盖负例、唯一键及源码哈希审计通过。原始数据、轨迹和逐图留出汇总见simulation/results/2026-10-21-rescue-graph-v1。

结论限于已知图上的合成接触模型：更强既有回报规则有效，但时效与发现量冲突。未验证真实火场、联合路径规划或中继能力上限，未确认Agent特有问题。完整解释及后续停止条件见该结果目录INTERPRETATION.md。

## 20. 救灾实际动作与通信依赖（2026-10-22）

核查DRZ现场报告arXiv v1 §III-C、IV-B/C、V及正式版书目，TRADR项目原始任务说明，iHERO官方摘要/作者页，以及MACE §III–IV。新增P36–P38，主表38篇。收敛出外部视角辅助作业、灾情更新改变部署、勘察指导下一任务三条信息—行动链，优先推进第一条。记录出处与核查范围见RESCUE_OPERATIONAL_EVIDENCE.md。本阶段完成文献证据和下一任务定义，沿用此前仿真结果。

## 21. 初步模型、baseline与协作通信执行器（2026-10-22）

按用户要求回到Agent-Native去中心化网络目标，完成AGENT_COLLAB_MODEL和BASELINES；重新确认ACHORD、MOCHA原文及RFC9171服务规范入口。文献主表保持38篇，标准资料单列。运行前固定AGENT_COLLAB_PROTOCOL，执行8640次：72条件、5策略、24种子，保存360条种子0轨迹与全部原始数据。模型为4节点外生链路时序，运动固定，规则智能体只通过已到达请求/结果更新任务。

46项测试通过，全量无需求/无背景对照、行唯一性和源文件哈希审计完成。结果揭示任务优先可保护短交互，接触等待和必要结果容量会改变协作与本地执行的代价。下一步以等待预算、协作接纳和执行资源占用展开模型。结果见simulation/results/2026-10-22-agent-collab-v1/INTERPRETATION.md。

## 22. 任务调度三路线筛查（2026-10-23）

完成CBBA/ACBBA、DCMRTA、HeteroMRTA、局部意图MAPPO、CapAM、学习出价、CTAS七组候选筛查，分别记录原文阅读范围与代码可得性，见TASK_SCHEDULING_SCREEN.md。候选使用T1–T7独立编号，已入表论文仍38篇。固定三个作者仓库提交与源码哈希，确认权重文件路径/大小但尚未加载。

HeteroMRTA原环境在NumPy2.5.4下单元素数组转float失败；以记录在案的内存兼容修正通过9机器人15任务初始化和观测检查。其agent_observe及状态构造直接读取全体任务/机器人字典，已定位后续通信接入与mask审计位置。尚未执行训练或策略评测。本阶段选择其为首个学习复现对象，原Greedy和CTAS-D作为同任务对照，网络诊断跟随原始复现开展。

## 23. 新增综述与具身网络扩展性分析（2026-10-23）

读取用户新增《任务感知网络调度_新版文献综述_论文原图版.pdf》全部19页文本，并渲染检查第16、17、19页对照与研究方向。临时文本/图片保存在忽略目录data/survey_review_2026_10_23，原PDF未修改。

沿引用重点核查7篇：ARMA、Co-Scheduling v1、AutoCast、C-MASS 2024 v1、CoSMO、CC-OPI v1的方法原文；CORA为作者机构摘要，ACM全文入口403。另复核P28 MOCHA/P29 ACHORD。来源、阅读章节及版本统一记录于RELATED_WORK补查表。Don't Fire Together作为错峰机制线索补查；出版方页面本机直开429，未把其详细数值作为本轮核心分析依据。其余PHY/工业方向条目保留为综述提供的候选。

重要修正：Co-Scheduling渐近结论要求任务与计算/通信资源同比扩展；C-MASS允许时变W_t；ARMA已测量控制字节且80UE为独立调度计算测试；CoSMO已有包含排队的ns-3网络仿真，优化动作仍是状态更新/卸载。CC-OPI的规模开销是应用层广播统计，其全局任务公告与空口模型边界分别记录。

RESEARCH_GAPS §0.9给出当前核心问题、局部信息/双类队列/共享空口骨架与配对诊断。更新README、NEXT_STEPS、AGENT_COLLAB_BASELINES和V0模型入口。保持已登记38篇主表及BibTeX不变，新增候选本轮按名称与链接单列；没有新增仿真结果、训练或策略评估。

## 24. 首轮优化层次与评价口径收敛（2026-10-23）

按用户提出的立足点/baseline/层次/指标四项问题，明确首轮优化分布式状态更新及MAC之上的消息队列服务，PHY/MAC及路由采用共同配置，实际服务由网络执行器产生。MOCHA为直接机器人通信协议对照，AutoCast为任务价值发送对照；HeteroMRTA与原Greedy是任务执行器，CoSMO/MGF/C-MASS按任务兼容条件后续纳入。

评价沿用HeteroMRTA makespan，配合完成比例、每完成任务空口成本与规模曲线。修正此前通用“相对本地独立执行净收益”的口径：必须组队的任务使用同策略即时信息参照；独立执行对照只用于可行任务。更新AGENT_COLLAB_BASELINES首轮方案、RESEARCH_GAPS与NEXT_STEPS；本轮没有新增仿真或复现结果。

## 25. 研究与创新判断原则修正（2026-10-23）

用户明确指出：已有工作不代表问题被做好或解决；创新无需以无人做过/想过为前提。相应修正README、RESEARCH_GAPS、AGENT_COLLAB_BASELINES与NEXT_STEPS：已有机制作为baseline，分析原条件下的能力、机制限制及可改进的性能—成本/复杂度/理论性质，再分析扩展条件。八条件用于系统特征描述；协议层作为首轮实验入口，MAC/PHY/路由及跨层优化保持开放。

RESEARCH_GAPS §2由排除式“创新边界”改为可检验改进方向；历史条目中的旧判断明确由当前原则替代，历史实验与来源数据保留。该更新为研究方法与计划修正，没有改变既有测量结果。

## 26. GitHub发布整理（2026-10-23）

按用户要求整理本轮研究内容：新增仓库首页导航，将用户提供的综述PDF作为原始参考资料纳入版本管理，更新研究目录的当前应用、证据与实现状态，并区分历史阶段。主文献表仍为38篇，定向补查与任务筛查单列。

提交前校对修正：能力互补任务的评价使用完成比例/makespan及同策略参照；队列模型补入旧版本移除量和更新触发动作；首轮接收集合固定；完成时间优化明确使用负效用或等价最小化。已标注v1的文献链接固定版本，数学表达统一为GitHub Markdown格式。已有实验数据和源码保持不变。

## 27. 本机原权重配对运行与通信组件核查（2026-10-23）

从e724f7a接手并保留原README/协作组织修改，在codex/baseline-reproduction-20261023分支执行。任务及审查见coordination/tasks/E1-002、D-002、C-002、M-002。作者论文再次核对§III返回驻地makespan与§IV推理入口：[作者PDF](https://marmotlab.org/publications/73-RAL2025-HetMRTA.pdf)。

HeteroMRTA固定db51e29535e34bcaa8cb75f70be3fd28b0027988并恢复38,361,491字节权重；SHA256为7cb4ab4fdaea750e52132e65481024b1c123252221a70b0336f839abfe7ccf5a。Python3.11.5/NumPy1.26.4/Torch2.3.1，复用已有库，CPU推理。两组9机器人、15/20任务各5个种子，原权重与作者Greedy共20次全部任务完成并返回驻地，无失败或超时。均值分别21.408737/24.030662与25.900583/32.299929；同seed初态哈希一致。非论文原测试集复现。原Greedy实际上取最后可行动作；仅补dist的seed0诊断停在驻地，达到10000动作预算，失败轨迹完整保留。

MOCHA固定bfbde0d186d77278085b25a365bf735d5acdc6bd、AutoCast固定5a69701081dcda9741106ad749270dc27b647ee9、AutoCastSim固定其gitlink 10837c2a942e92312ea1a53697bc4513d9325454，86份文件记录双哈希。14项原AST组件探针通过；AutoCast控制Beacon可包含点云，示例10/1000点对应653/17483字节；原发送预算在两个60ms对象后退出，累计120ms。默认中央控制缓存及直接数据写缓存已定位，完整ROS2/CARLA和无线竞争没有运行。

C独立核对任务能力约束、返回时间、动作mask、完整分母、种子/源码哈希，以及组件代码和序列化字节；2项执行安全测试通过。原始结果、代码快照和失败诊断采纳至simulation/results/2026-10-23-E1-002-heteromrta及2026-10-23-D-002-network-components。详细限制与恢复命令见HETEROMRTA_REPRODUCTION.md和NETWORK_BASELINE_RUNTIME.md。75份既有结果另以接手哈希核对，未覆盖。下一阶段围绕送达缓存、同步成本和消息队列进入机制实验。

## 28. 完整科研链条与实验框架（2026-10-25）

按用户要求建立[RESEARCH_EXPERIMENT_CHAIN](RESEARCH_EXPERIMENT_CHAIN.md)，统一现场需求、论文进展、研究问题、初步理论模型、算法构思、数据、指标、消融与扩展实验、图表和实施顺序。配套资料为framework_20261025下的LITERATURE_FRONTIER、MODEL_ALGORITHM、EXPERIMENT_DESIGN。任务与审读见M-003/D-003/E2-003/C-003；本轮只读已有代码/结果，未运行仿真、训练或完整协议。

新增定向检索发现更直接的2026工作：CommHG已包含接收缓存、查询/遥测及回复/控制竞争；AC-DMTA已按分配稳定性触发信息交换；Planned synchronization已有执行、观测和重新协商成本模型。研究据此采用更强比较对象，在相同问题下检验联合更新/发送的性能—成本、复杂度和动态适应改善。具体官方来源、版本与读取范围保存在文献分项；新来源本轮单列，不改变原P01–P38及BibTeX。

数据分项核查HeteroMRTA、AutoCast/CARLA和SubT官方入口，区分原任务、统一网络适配、传感回放与救灾闭环。定义完成率/原makespan、含失败时间分数、空口与忙时、有效及时交付和未交付分母；规模实验分开控制面积、密度、任务量和无线资源。原实验结果保持原位，新方案没有填入预期性能数字。

源码审读明确S1的关键工作：观测、mask和Worker的全局控制分支均需遵守消息可得性；保留同时间逐机器人微步用于零延迟回归；原location为派遣目的地，网络轨迹须另建；受限信息执行检查回溯出发问题。信息/计费四格先固定回放校准，闭环报告具体干预的总效应与交互。上述事项直接服务于后续结果的正确性，详细审读与修订记录见coordination/reviews/C-003.md。

## 2026-10-25 S1送达接口与原协议运行（M-004）

本阶段由用户“推进”授权，起点7b6b09c。E1实现缓存，D运行原协议，C独立只读审计，M集成与归档；未训练模型、修改作者代码或覆盖历史结果。

- [HeteroMRTA接口报告](HETEROMRTA_NETWORK_INTERFACE.md)：正式03共10实例，373实际动作及最终状态与E1-002归档一致；384消费机会的zero观测、mask、分支与动作完全等价。远端延迟0.5/2的影子动作差异为138/215，mask差异136/230。正延迟未执行影子动作，结果用于信息敏感性诊断。9项测试通过。373次单份JSON命令发布合计88,636字节，不计为空口；delay2结束处8个接收副本尚未投递。
- [MOCHA运行报告](MOCHA_RUNTIME_ENTRY.md)：原MOCHA、固定官方SMACH及ZeroMQ双进程回环18项检查通过，包含入库、双向最新视图和对端退出超时。成功应用包交换371字节，另有11字节无响应请求提交；完整ROS/DDS与无线未验证。两次运行及适配时钟失败均保留。
- [几何核验](../../coordination/reviews/M-004-geometry.json)：只读复算原20回合767段路线，7段计划出发早于动作，最大3.54426178229925模拟时间。C独立核对。这是因果移动适配的实际依据，不改原复现的指标定义。
- 正式归档：[E1-003](../../simulation/results/2026-10-25-E1-003-interface/README.md)、[D-004](../../simulation/results/2026-10-25-D-004-protocol/README.md)。各ARCHIVE_MANIFEST逐文件记录原始/存档SHA256，大JSON以无时间戳gzip保存，解压可恢复原始字节；失败与中止保留。
- [独立审查](../../coordination/reviews/C-004.md)、[阶段判断与下一步](../../coordination/reviews/M-004-interpretation.md)。下一步从因果执行、本地唤醒和反馈构造任务闭环，再比较即时信息/延迟/共享服务。

## 2026-10-25 可扩展性与网络服务全面分析（M-005）

用户要求基于动态与扩展性矫正重新全面分析。工作区起始f136c6e且干净；M整合，D-005定向核原文，E2-004建立模型与识别实验，C-005独立审读。没有运行新仿真、协议或训练，也没有修改研究代码和历史结果。

当前总入口为[SCALABILITY_COMPREHENSIVE_ANALYSIS](SCALABILITY_COMPREHENSIVE_ANALYSIS.md)，配套[证据与研究位置](scalability_20261025/EVIDENCE_POSITIONING.md)、[模型与识别实验](scalability_20261025/MODEL_AND_IDENTIFICATION.md)。首版RESEARCH_EXPERIMENT_CHAIN与framework_20261025保留并加当前入口；旧研究结论不回写成新结果。

主要调整：以规模/协作度/实际数据负载/变化率→维护和任务流→排队与竞争服务→及时有效信息→任务后果为主链；同时研究任务反馈引起的后续业务。主产出是共同资源和任务门槛下的实测达标运行域；不预设规模必然导致物理误码，也不把有限缓存有界当作需求可服务。

本轮复核MGF v2的固定源数、同比任务/资源扩展及下一槽无错假设；AutoCast已有车辆密度实验及少量radio重放；C-MASS已有拥塞相关W_t和维护成本；CoSMO已有ns-3排队。CommHG、AC-DMTA、ARMA/CORA、ACHORD等作为强起点，不泛化宣称网络问题无人研究。应用证据区分真实灾害中的人机协作、自主/监督自治系统验证和本项目待测规模效应。来源精度见D-005文件。

三层网络实验分别为共同预算下可靠授权服务、显式排队服务和实际竞争无线；无限即时信息仅作单列的资源放松参照。需求分母、失败/超时、ACK与正文可见性、广播/多跳/空间复用，以及策略自身规模泛化均由明确的记录与对照处理。下一实现先补因果闭环和业务账本，再用分层服务定位主导损失，随后开展算法消融及规模×动态曲线。

C-005终审已通过，复核关闭ACK/正文出队、L0共同容量和跨观察窗成本三项问题；只采纳分析设计，不作为新算法效果证明。M核验445份既有simulation/data文件哈希不变，184处本地链接存在，详见[一致性记录](../../coordination/reviews/M-005-consistency.json)。

## 2026-10-25至26日：因果任务闭环与共享应用服务（M-006）

用户“继续”授权有限实现与计算，从ff2157c干净工作区开始。E1-004完成新因果执行器，E2-005完成共同服务/回放，C-006独立审计，M集成。未修改固定作者代码与权重，未训练，旧结果保留。

- 58回合分为1pilot、45主矩阵、10结果后共同等待敏感性、2极小延迟定位。原10实例因果instant全部成功。15任务正延迟/FIFO在seed2/3零完成；20任务主三条件均5/5完成。全部回合正常退出，失败保留为H=200未完成。
- 失败链已由事件定位：t=0并发分派分散互补能力，等待200使最早重决策晚于H；消息全部交付。极小正延迟也复现。共同wait20把delay0.5成功数由3/5变4/5，另一个种子仍同步重派。该结果解释恢复规则与初始信息时序，不提供容量阈值。
- FIFO同成功seed0/1/4中，2048相对8192有更多抵达已开工/完成任务的访问与维护消息。固定141条/42674字节pilot回放独立给出队列效应；三档FIFO交付p95为3.2555/0.5631/0.2235作者时间。回放与闭环分开解释。
- 10项终版因果测试及10项服务测试通过。C从58回合已有证据独立重建6030决策、11091消息、750次现场开工和6固定回放，没有运行新策略。核验脚本与JSON在coordination/reviews/C-006-verification.*。
- 总报告[CAUSAL_SERVICE_STAGE](CAUSAL_SERVICE_STAGE.md)，细节[HETEROMRTA_CAUSAL_EXECUTOR](HETEROMRTA_CAUSAL_EXECUTOR.md)、[MESSAGE_SERVICE_DIAGNOSTIC](MESSAGE_SERVICE_DIAGNOSTIC.md)。归档共750份原始证据，经原/存储/解压三方hash校验；445份原文件未改。55回合结果图展示主矩阵与等待敏感性，pilot/epsilon另列。

下一阶段先建立共同分布式分派/恢复及限速强基础，再评价更新与发送机制。当前时间、字节均为仿真/应用单位，未引入MAC/PHY、多跳或实机测量；节点扩展与新算法评估尚待实施。
