# Task: Feasibility Validation of Self-Organizing Network-Guided Multi-UAV Physical Field Reconstruction

## 1. Research Objective

基于 Mendeley Data 数据集：

https://data.mendeley.com/datasets/bn6n2639xh/2

验证以下核心研究假设：

**在动态城市无线电环境中，多无人机通过自组织网络交换局部物理场信息，并进行分布式协同采样，能否在相同采样预算、飞行距离和任务时间下，提高三维无线电地图重建精度？**

本阶段定位为 Research Feasibility Validation。

不要求实现完整无人机飞控系统，也不要求立即开发复杂的分布式优化算法。

优先通过可控仿真实验判断研究方向是否成立。

## 2. Dataset Audit（必须首先完成）

使用指定的 Mendeley Version 2，固定数据版本，禁止混用其他版本。

已知数据集信息：

- 城市区域：1.25 km × 1.25 km
- 空间网格：250 × 250
- 空间分辨率：5 m × 5 m
- 中心频率：2.45 GHz
- 带宽：10 MHz
- 动态时间：600 s
- 时间更新：1 s
- 动态高度：2 m、25 m、50 m、80 m
- 动态数据格式：250 × 250 × 600
- RSSI 单位：dBm

首先检查实际下载文件、MATLAB 数据结构和 guidemanual.pdf。

注意：GitHub 仓库 README 可能对应旧版 300 s 数据。必须以指定 V2 的实际文件和元数据为准。

验收内容：

1. 数据文件完整性和版本确认。
2. 数据维度、坐标映射、时间维度和高度信息。
3. RSSI 数值范围、缺失值、异常值。
4. 多高度、多时刻地图可视化。
5. 移动辐射源导致的空间和时间变化分析。
6. 数据访问接口：能够通过 (x,y,h,t) 查询真实 RSSI。

输出：
- DATA_AUDIT.md
- 数据加载与预处理代码
- Ground Truth 可视化
- 数据文件清单及版本记录

## 3. Physical Field Reconstruction Baseline

建立统一的物理场重建框架：

F(x,y,h,t)

无人机只能访问其当前位置和当前时刻对应的真实 RSSI。

完整 Ground Truth 仅供离线评价程序使用，严禁进入无人机决策模块。

至少实现：

1. IDW
2. Kriging
3. GPR（需要输出预测均值和方差）

测试不同采样率：

1%、2%、5%、10%、20%。

评价：

- MAE
- RMSE
- P95 Absolute Error
- Spatial Reconstruction Error
- Temporal Reconstruction Error

输出：
- BASELINE_REPORT.md
- Ground Truth / Sampling / Reconstruction / Error Map 对比图
- RMSE 与采样率关系曲线

所有方法使用相同的测试数据、采样预算和评价标准。

## 4. Multi-UAV Sampling Simulation

建立多无人机采样仿真环境。

初步节点数量：

N = 5, 10, 20, 30

每架无人机具有：

- 唯一节点 ID
- 三维位置
- 飞行速度
- 当前采样数据
- 局部物理场地图
- 局部不确定性
- 邻居列表
- 任务状态

采样模型：

y_i(t) = F(x_i(t), y_i(t), h_i(t), t) + noise

约束：

1. 每架无人机只能获得当前位置的测量值。
2. 不能提前读取未来时刻的 RSSI 地图。
3. 高度优先使用数据集提供的四个动态高度平面。
4. 飞行轨迹必须连续，考虑速度和安全距离。
5. 传感器噪声作为可配置参数。
6. 相同位置的重复采样必须记录。

动态环境使用 600 s 数据；静态环境用于控制实验。

先在单高度场景完成 Pilot，再扩展到多高度和多节点。

## 5. Communication Network Simulation

构建动态通信图：

G(t) = (V, E(t))

初步使用基于无人机距离的通信范围模型：

A_ij(t) = 1, if d_ij(t) <= R_c

随后增加：

- 链路丢包
- 通信时延
- 带宽限制
- 链路质量变化
- 节点失联
- 网络分区与恢复

第一阶段可以使用距离门限模型，第二阶段再引入路径损耗和建筑遮挡。

注意：数据集中的 RSSI 是环境辐射场测量值，不等同于任意两架无人机之间的链路 RSSI。必须单独建模无人机之间的通信链路。

### 消息设计

至少设计：

NODE_STATE:
节点 ID、位置、速度、时间戳。

MAP_SUMMARY:
区域编号、预测均值、预测方差、采样数量。

TASK_INTENT:
候选目标区域、信息价值、预计到达时间。

TASK_UPDATE:
任务归属、任务完成状态、失效状态。

记录所有消息的字节数、发送次数、接收次数、时延和丢包情况。

## 6. Sampling Strategies and Ablation Experiments

必须比较以下五种方案：

A. Fixed Route:
固定路线，多无人机独立采样，不进行网络通信。

B. Fixed Route + Communication:
固定路线，交换采样数据或地图信息，但不调整采样路径。

C. Independent Active Sensing:
每架无人机依据自己的局部地图和不确定性独立决定下一采样位置，不交换协同任务信息。

D. Distributed Network-Guided Active Sensing:
无人机交换局部地图摘要、候选采样位置和任务状态，通过邻居协商、分布式竞价或其他无中心协调机制分配任务，减少重复采样。

E. Centralized Oracle:
使用全局信息的中心化规划方案，仅作为理想性能上界。

重点比较：

- B vs A：信息共享本身的价值。
- C vs A：独立主动采样的价值。
- D vs C：网络协同决策带来的增量价值。
- D vs E：分布式方法距离理想全局方案的差距。

D 组必须真正通过网络消息改变无人机的采样目标或运动轨迹。

不能只在实验结束后集中汇总数据，再宣称实现了网络协同。

运行期间，D 组禁止使用中心化 Planner。离线评价程序可以集中收集日志和计算指标，但不能向无人机策略提供全局信息。

## 7. Distributed Active Sampling Algorithm

初步采用 GPR 预测方差或预期误差下降作为采样价值。

对候选位置 q：

Utility_i(q) = Expected Error Reduction / Travel Cost

每个节点：

1. 建立本地地图和不确定性估计。
2. 选择 Top-K 候选采样区域。
3. 向邻居发送候选区域及任务意图。
4. 通过分布式协商减少目标冲突。
5. 根据自身位置、任务状态和剩余资源决定下一目标。
6. 完成采样后更新局部地图。
7. 将必要摘要信息发送给邻居。

优先实现简单、可解释、可复现的分布式任务分配方法。

Pagano et al. (2025) 的 E-ICF 和 4×4 Gramian 可作为方法参考，但不要直接将其四维扩散源参数模型套用到整个 250×250×H×T 的无线电地图。

## 8. Evaluation Metrics

### A. Reconstruction
- MAE
- RMSE
- P95 Error
- 各高度重建误差
- 各时间段重建误差

### B. Sampling Efficiency
- RMSE vs Sample Count
- RMSE vs Flight Distance
- RMSE vs Mission Time
- 重复采样比例
- 有效空间覆盖率

### C. Network Performance
- Total Communication Bytes
- Per-node Communication Bytes
- Packet Delivery Ratio
- Average Latency
- Network Connectivity Ratio
- Network Partition Duration
- Average Node Degree

### D. Mission Performance
- Total Flight Distance
- Mission Completion Time
- Energy Proxy
- Collision Count
- Safety Constraint Violations

## 9. Fairness and Statistical Validation

所有方案必须控制：

- 相同无人机数量
- 相同初始位置
- 相同传感器噪声
- 相同采样预算
- 相同飞行速度上限
- 相同重建模型
- 相同评价数据

至少开展两类比较：

1. 相同采样数量下的重建精度。
2. 相同任务时间或飞行距离下的重建精度。

初步使用至少 20 组随机种子，报告均值、标准差和 95% 置信区间。

对于关键对比，进行适当的配对统计检验。

## 10. Mandatory Acceptance Deliverables

最终必须提供：

1. DATA_AUDIT.md：数据集版本、数据结构和可用性分析。
2. EXPERIMENT_PROTOCOL.md：实验设计、变量、假设和公平性约束。
3. BASELINE_REPORT.md：传统物理场重建基线。
4. NETWORK_DESIGN.md：通信图、消息格式和动态拓扑模型。
5. ALGORITHM_REPORT.md：各采样策略的算法流程。
6. RESULTS.md：对照实验、消融实验和最终结论。
7. 可运行的源代码、配置文件和随机种子。
8. 结果 CSV 和必要的日志。
9. RSSI 地图、无人机轨迹、采样分布、误差地图和网络拓扑可视化。
10. 一份简短的 Research Feasibility Conclusion。

### 必须回答的最终问题

Q1：多无人机协同采样是否优于独立采样？

Q2：交换局部地图信息是否能够改善重建精度？

Q3：通信是否实际改变了无人机的采样位置和运动轨迹？

Q4：在相同采样预算下，网络协同是否减少了重复采样？

Q5：在动态通信拓扑、丢包和时延条件下，协同收益是否仍然存在？

Q6：节点数量增加时，通信开销和重建精度如何变化？

Q7：网络协同带来的精度收益是否足以抵消额外通信和运动成本？

Q8：该研究方向是否值得进一步发展为动态自组网与三维物理场联合优化问题？

## 11. Execution Rules

采用分阶段执行：

Phase 0：数据审计和研究方案确认。

Phase 1：单高度、单时刻、少量无人机的最小可行实验。

Phase 2：动态 RSSI 场景下的多无人机采样。

Phase 3：动态通信拓扑和分布式任务协商。

Phase 4：完整对照、消融和规模扩展实验。

每个阶段先运行小规模 Pilot，检查正确性后再扩大规模。

不要一开始就开发复杂神经网络、完整无人机动力学或复杂路由协议。

不要为了得到预期结论而调整实验结果。

如果实验没有显示自组网收益，应明确报告负面结果和适用边界。

**最终交付的核心不是代码数量，而是有充分对照实验支撑的研究可行性结论。**