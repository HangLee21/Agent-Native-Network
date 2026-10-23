# 当前摘要

建立时间：2026-10-23（Asia/Shanghai）。本页由 M 更新；任务实时状态只看任务卡。

## 本轮范围

2026-10-23，用户已授权连续推进原baseline复现、机制分析和初步仿真，阶段完成后提交推送。M 已接管总控；E1-002 已完成20次正常配对评估及1次失败诊断，D-002 已完成14项原组件探针，C-002 已独立验收，M-002 已完成归档，阶段提交361f5e2已推送origin/codex/baseline-reproduction-20261023。使用本聊天内临时子代理完成分工，长期角色聊天未唤醒。

## 本机已核实的起点

- 主目录：`D:\Multi-Agent Network`。
- 远端：`git@github.com:HangLee21/Agent-Native-Network.git`。
- 建立架构前：`main`，提交 `e724f7a557cf322280f252d394cb8533c8663fc7`，工作区干净。
- 本次 clone 存在研究文档、仿真源码与已跟踪的历史结果；未找到 `.venv/`、`data/`、`simulation/outputs/`。
- 上述信息是建立时快照。组织文件当前为本地新增/修改；后续接手必须重新检查 Git 状态。

## 研究主线：从既有文档读取

当前方向是具身集群中协作状态维护与任务消息共享无线资源的扩展性问题；HeteroMRTA 原策略/Greedy 小实例配对为近期实验入口，MOCHA 与 AutoCast 分别提供通信机制和任务价值调度参照。以上属于仓库记录，未在本机复现。

研究优先级仍由 [NEXT_STEPS 第 0 节](../research/agent_native_network/NEXT_STEPS.md)和[研究问题分析](../research/agent_native_network/RESEARCH_GAPS.md)提供；本页不另建一份研究路线。

## 接手时容易混淆的地方

| 现有记录 | 本机应如何理解 |
|---|---|
| [任务筛查](../research/agent_native_network/TASK_SCHEDULING_SCREEN.md)称已有固定源码与环境初始化 | 历史记录；源码所在 `data/task_baseline_screen/` 本机缺失，权重评估仍未完成 |
| [仿真 README](../simulation/README.md)称 `.venv` 已建、记录过 Python 故障 | 原环境叙述，不证明本机依赖可用；不要照抄旧机器判断 |
| [下载检查脚本](../simulation/screen_task_baselines.py) | 按清单下载 `files`，不自动获取权重；会改写 `task_baseline_smoke.json` |
| [agent_collab](../simulation/agent_collab.py)、[rescue_graph](../simulation/rescue_graph.py)及相应 audit 脚本 | 存在固定历史结果路径，执行前检查写入，不能直接作为只读审计命令 |
| 研究目录中的 AGENT_COLLAB 文档 | 研究对象的通信协作模型，与本机角色窗口分工分开阅读 |

## 下次恢复

先读 M-002/E1-002/D-002/C-002 的主任务卡和交接记录。旧四张待办卡的范围由新卡承接，避免重复启动。M-001只统计了历史CSV，不能视为本机仿真或HeteroMRTA复现；其证据在simulation/outputs/M-001/20261023-01/。

## 本轮实际产物

- HeteroMRTA：9机器人、15/20任务各5种子，两策略全部完成并返回；均值21.408737/24.030662与25.900583/32.299929。原Greedy实现问题和单行修复失败已记录。
- MOCHA/AutoCast：固定源码及14项组件探针；完整ROS2/CARLA/无线协议任务未运行。
- 当前环境：.venv使用Python3.11系统库，权重/源码在data；这些目录Git忽略，不随clone复制。恢复命令见两份研究运行报告。
- 归档：simulation/results/2026-10-23-E1-002-heteromrta/、2026-10-23-D-002-network-components/；审查coordination/reviews/C-002.md。
- 无活动计算或后台队列。下一步：即时信息/送达缓存接口的零延迟等价检查，再比较更新触发与消息队列；Greedy变体先明确定义回站与等待。
