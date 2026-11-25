# 任务调度baseline筛查与复现选择

2026-10-23。目标：先复现已有任务调度，再定位通信对端侧协作决策的影响。此次是定向筛查，覆盖规则/拍卖、在线优化和学习策略三条路线。候选条目T1–T7单列于本文件；原论文主表38篇保持原编号。

本机进度更新（2026-10-23）：已完成[原权重与作者Greedy小实例评估](HETEROMRTA_REPRODUCTION.md)，正式结果见[归档](../../simulation/results/2026-10-23-E1-002-heteromrta/INTERPRETATION.md)。下文“初始化通过、权重未评估”为原筛查时快照；最新结果为20次正常运行成功及一项单行修改失败诊断。

## 筛查结果

|候选|任务与控制变量|方法/训练|信息假设与网络入口|复现决定|
|---|---|---|---|---|
|T1 CBBA及ACBBA|任务包、执行次序、冲突消解|贪心出价+邻居一致性；不训练|交换赢家、出价等状态；ACBBA明确处理异步、乱序与冗余信息|规则对照。官方CBBA MATLAB包已定位；ACBBA另核查原算法与代码|
|T2 DCMRTA，ICRA 2024|同质机器人动态组队及下一任务选择|注意力策略，REINFORCE，训练用leader-follower|任务及同伴状态进入决策，完成mask共享|备用学习基线；作者代码和约27MB权重已定位|
|T3 HeteroMRTA，RA-L 2025|异构能力匹配、组队、任务序列；目标makespan|注意力策略，代码采用REINFORCE，含flashforward机制|代码直接读取全体agent/task字典；可在观测构造处接入消息缓存|**首个实际复现对象**；作者代码、约38MB权重、测试入口齐备|
|T4 Learning Policies for Dynamic Coalition Formation，arXiv v3 2025|局部可观测、动态任务、组队及改派|U-Net+MAPPO，集中训练/分布式执行|感知范围与通信范围分开，范围内同伴意图进入观测|**网络耦合优先候选**；已核查原文，当前检索未定位作者代码入口|
|T5 CapAM，ICRA 2022|单机器人任务、容量与期限约束|图胶囊注意力+REINFORCE|图状态及机器人上下文；需进一步核查信息刷新实现|保留为单机器人任务对照；代码、约13MB权重已定位|
|T6 Learned Bidding，arXiv v1 2026|单机器人任务的出价与分配|PPO学习出价，保留拍卖/一致性；MILP解用于奖励塑形|局部观测出价，通信仍由一致性框架承担|规则与学习结合的候选；代码入口本轮未定位|
|T7 CTAS / CTAS-D|能力约束下任务分配、路线与时序|随机规划；确定性版本作为MIP对照|集中获得实例信息，适合小规模解质量参照|随HeteroMRTA原基线进入；核查求解器、时限与状态后运行|

来源与阅读定位：

- T1：[MIT作者项目页](https://acl.mit.edu/projects/consensus-based-bundle-algorithm)，CBBA、ACBBA、CCBBA及Relays说明；[官方MATLAB包](https://acl.mit.edu/files/CBBA_MATLAB_ACLMIT_July13_2010.zip)。本轮定位下载入口，尚未执行MATLAB。
- T2：[作者论文](https://www.marmotlab.org/publications/56-ICRA2024-MRTA.pdf)，摘要、§III观测/动作与共享mask；[作者代码](https://github.com/marmotlab/DCMRTA)。
- T3：[作者论文](https://marmotlab.org/publications/73-RAL2025-HetMRTA.pdf)、[作者页面及正式版DOI](https://jimmychiun.me/publications/heterogeneous-task-allocation.html)、[作者代码](https://github.com/marmotlab/HeteroMRTA)。作者预印本短标题与正式版本标题存在差异，正式版本由DOI 10.1109/LRA.2025.3534682标识。
- T4：[原文](https://arxiv.org/html/2412.20397)，§III、IV-A/B、Table II与V-A。环境名GyMRTA，基于EPyMARL扩展；执行每步可改派，原基线含作者修改的PCFA。
- T5：[原文入口](https://arxiv.org/abs/2205.03321)、[作者代码](https://github.com/iamstevepaul/MRTA-Graph_RL)，本轮重点核查README、依赖和文件树；方法细节继续原文核查。
- T6：[原文](https://arxiv.org/html/2605.21932)，摘要、§I–II；训练方式与目标已核查，后续细读§IV–V。
- T7：[作者项目页](https://brg.engin.umich.edu/publications/robust-task-scheduling/)、[原文摘要](https://arxiv.org/abs/2106.12111)。项目页搜索索引可读取，直接打开返回403；当前不据此判断代码不可用。DCMRTA仓库提供CTAS-D调用与结果解析脚本。

## 为什么先复现HeteroMRTA

选择依据是异构协作任务匹配、原始代码可得、提供预训练权重和基线入口。先执行原任务：多种能力的机器人共同满足任务需求，全部必要机器人到达后开始作业，评价完成任务并返回驻地的makespan。

已固定三份仓库版本与源码SHA256，见[下载清单](task_baseline_sources.json)。HeteroMRTA提交为`db51e29535e34bcaa8cb75f70be3fd28b0027988`，许可Apache 2.0；DCMRTA和CapAM的源码快照也保存在忽略目录`data/task_baseline_screen`。

代码入口：

- `worker.py:59`调用`env.agent_observe`，在下一任务选择前取得观测。
- `env/task_env.py:271`遍历全部机器人，构造能力、位置差、旅行/作业/等待状态。
- `env/task_env.py:294`遍历全部任务，构造剩余需求、原始需求、作业时间和分配状态。
- `env/task_env.py:467`组合这些状态与动作mask。后续改通信时必须同时审计mask，确保接收缓存与动作可行性判断的信息口径一致。

这里形成一个明确的诊断入口：原始即时状态输入→消息送达后更新的本地副本。保留原策略和任务实例，即可测量状态更新延迟怎样影响选任务、组队和等待。

## 已完成的可运行性检查

执行作者原环境的初始化与观测构造：9机器人、15任务、seed=0，观测形状分别为`(1,16,15)`、`(1,9,11)`、`(1,16)`，数值均有限。原代码在NumPy 2.5.4下遇到单元素数组转float错误；运行时将`float(tasks_time[i, :])`替换为`.item()`，原下载文件保持不变。此步骤验证环境入口，尚未加载策略权重或评价性能。

复现命令：`.venv/Scripts/python.exe -m simulation.screen_task_baselines`。脚本依据清单下载固定版本、校验哈希并执行上述检查。[检查记录](task_baseline_smoke.json)保存版本与兼容修改。

## 实验顺序与归因

1. **原始复现**：加载HeteroMRTA预训练权重，使用原实例生成器、贪心解码、原指标，跑小规模配对实例；对照作者Greedy以及CTAS-D。记录失败/超时、可行解、求解时间和MIP gap，求解器未完成证明的解按incumbent报告。
2. **网络诊断**：保持权重、任务、移动与执行规则，逐步替换状态读取为本地缓存；分别加入固定延迟、周期更新、链路间歇。先记录决策变化，再统计不必要等待、重复投入、能力不足、错误改派和任务完成量。
3. **学习适应性**：完成冻结策略诊断后，再在受限信息下训练/微调。冻结评估与重训练结果分列，以区分输入变化的影响和学习可恢复的部分。
4. **规则对照**：同一信息接口下加入适用于该任务的规则方法。普通CBBA处理单机器人任务，合作任务优先使用原论文Greedy或适配的coalition方法；先确认任务可行域一致再比较。
5. **局部意图分支**：继续定位T4作者实现。它具有现成的邻居意图与动态改派，可用于细查更新频率、消息大小、丢失与任务反复改派之间的关系。

网络层继续用MOCHA/ACHORD作机制参照。学习策略负责选择任务，通信机制负责把决策所需信息交付给各节点；两层分别替换和测量，保持Agent-Native去中心化无线网络主线。
