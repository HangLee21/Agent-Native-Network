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
