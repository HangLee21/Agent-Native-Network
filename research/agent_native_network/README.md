# Agent-Native 去中心化无线网络研究

**研究题目：** Agent-Native Decentralized Wireless Networking for Collaborative Edge Intelligence  
**版本：** V1.4，2026-10-23（Asia/Shanghai）

**状态：** 主线转为已有任务调度baseline复现。已筛查7组方法，选择HeteroMRTA作为首个可执行学习基线，原Greedy/CTAS-D作为配套对照；局部意图MAPPO与CBBA异步变体列为后续重点。已完成固定源码版本、状态读取审计与原环境初始化检查。

最新：[任务调度筛查与复现选择](TASK_SCHEDULING_SCREEN.md)。此前[自建模型](AGENT_COLLAB_MODEL.md)和[8640次机制实验](../../simulation/results/2026-10-22-agent-collab-v1/INTERPRETATION.md)保留为辅助工具。先还原原方法任务及表现，再通过通信信息更新诊断差距。

找矿覆盖分支保持暂停，历史结论见 [反馈机制审查](FEEDBACK_MECHANISM_REVIEW.md)。

首轮336次合成实验未确认共享优势，保留为 [历史结果](../../simulation/results/2026-10-20-synthetic-v1/INTERPRETATION.md)。后续改用真实航空数据与非负混合估计构件，在三个固定区域观察到补充光谱代理降低预测误差；仍不等于真实地面观测、找矿识别或通信收益。见 [Cuprite 结果与边界](../../simulation/results/2026-10-20-cuprite-observation-v1/INTERPRETATION.md)。

救灾候选方向已独立筛查：[搜索发现回报与核查协同](RESCUE_TASK_SCREENING.md)。任务与通信证据较直接，但已有方案后的剩余损失及Agent特有需求仍待验证。

## 研究定位

面向无人机、机器狗、手机和工业节点各自运行模型的系统，研究自主通信需求与无线网络控制之间的闭环。最终目标保留控制面、传输、路由、MAC/PHY及移动拓扑的完整系统范围。任务规划和模型训练用于产生业务负载，不作为当前主要创新。

部署严格分为 P1 多实体设备本地推理、P2 共享硬件上的独立上下文/逻辑实例、P3 云端模型 API、P4 单模型跨设备切分。P2 可用于功能验证，不能替代 P1 的设备性能证据；共享权重和独立上下文也不必然意味着多个独立推理进程。

## 本轮结论

当前集合共 **38 篇**（2026-10-22新增P36现场部署、P37交互探索、P38自适应通信窗口；核查范围见[现场证据](RESCUE_OPERATIONAL_EVIDENCE.md)）。此前35篇的核查记录如下（P33–P35分别为E1/E2/E2，见反馈审查）：原32篇中，初始 22 篇中有 10 篇核心原文核查，随后补充 7 篇问题相关系统与实验核查（其中 MOCHA 另核对源码）；另新增 3 篇找矿/科学勘查对照，其中 2 篇核查方法与实验，1 篇只核实摘要和书目。新增 HAFS [P26] 已支持端侧独立 Agent 与受限网络机制，**A 类由 0 修正为 1**；其 AP/SFU 架构不满足去中心化动态多跳目标，八项完整系统条件仍无一篇全部确认。不能混淆“端侧 Agent 已有实测”与“八条件全部满足”。

**问题优先结论：** 野外机器人断续连接、大消息无线交付退化，以及特定端侧 Agent 上下文流与实时业务竞争，有原始研究支持。普通 Agent 短文本拥塞、频繁依赖失效及必须跨层改造，目前证据不足。已有本地自治、紧凑语义图、机会通信和 DDS 配置优化可以显著缓解部分问题。先核查这些方法之后的真实任务损失，再决定是否需要新机制；不能把文献组合空白当作问题存在。

问题证据、反证、适用边界和停止条件集中见 [RESEARCH_GAPS.md §0](RESEARCH_GAPS.md)。联合优化、语义压缩、版本标签等仍需遵守既有研究边界。

**应用收敛：** 用户确认实验室已有无人机/机器狗平台，但载荷、链路及协作流程未定。优先核查找矿中的区域筛查—地面核查需求，火灾为对照场景。空地观测互补已有依据；同次作业反馈价值和实际网络瓶颈仍需分别验证。具体证据见 RESEARCH_GAPS §0.8，任务定义、反证和四组对照见 [TASK_DEFINITION.md](TASK_DEFINITION.md)；当前没有“必须实时协作”或“必须多跳”的结论。

## 文件导航

| 文件 | 内容与维护入口 |
|---|---|
| [RELATED_WORK.md](RELATED_WORK.md) | 技术脉络、10 篇核心原文核查及相关边界 |
| [PAPERS.csv](PAPERS.csv) | 35 篇文献元数据、部署、网络实现及证据字段 |
| [references.bib](references.bib) | 与 paper_id 一一对应的引用；未核实 DOI 不填入 BibTeX |
| [RESEARCH_GAPS.md](RESEARCH_GAPS.md) | 问题存在性审查、反证、八条件矩阵及待验证假设 |
| [ARCHITECTURE_MODEL.md](ARCHITECTURE_MODEL.md) | 三类架构图、消息协议、V0 数学模型及可控性 |
| [TASK_DEFINITION.md](TASK_DEFINITION.md) | 首个任务、文献依据、评价对象、初步仿真对照与停止条件 |
| [RESCUE_TASK_DEFINITION.md](RESCUE_TASK_DEFINITION.md) | 当前救灾发现回报任务、先导结论与停止条件 |
| [FEEDBACK_MECHANISM_REVIEW.md](FEEDBACK_MECHANISM_REVIEW.md) | 反馈来源、因果审计、空间混合及停止判定 |
| [NEXT_STEPS.md](NEXT_STEPS.md) | 当前推进顺序与暂缓采用的技术备选 |
| [EVIDENCE_LOG.md](EVIDENCE_LOG.md) | 检索策略、版本冲突、来源链接、访问限制和核查结果 |
| [simulation](../../simulation/README.md) | 可运行任务级原型、测试及合成场景结果 |

## 证据与更新规则

E1 表示书目/摘要核实；E2 表示方法和实验原文核查；E3 表示额外核对作者公开代码或配置。E3 不表示执行过代码。所有“未核实”保持未知，不能转成“是”或“否”。分类 A/B/C/D 描述相关性，证据等级描述读到了什么，两者独立。

引用使用 `[P01]` 等稳定标识，对应 CSV 和 BibTeX 的同名 key。CSV 的 year 是实际引用版本年份，first_year 保留首次预印本年份。正式发表未核实的记录引用已核实预印本，publication_status 明示此限制，不能将它解释为确认尚未发表。

后续更新顺序：先核对官方版本及部署证据，再更新 CSV/BibTeX，最后更新综述、矩阵和数量。新论文若满足全部八条件，应优先重写研究空缺；不得为保持选题新颖性降低其证据等级。

## 仓库检查

开始时当前目录为空，无可复用文档及本地 AGENTS.md；父级两处 AGENTS.md 亦未发现。Git 根目录实际为 `D:/`，触发 dubious ownership。使用一次性 `git -c safe.directory=D:/` 完成范围限定的只读检查，未更改全局配置、初始化仓库或提交。检查范围内起始工作区无变更。未触碰其他目录的实验结果。

上述为首次检查的历史记录。随后按用户要求在当前目录建立独立仓库并关联 `HangLee21/Agent-Native-Network`；后续文件维护均在该独立仓库内。
