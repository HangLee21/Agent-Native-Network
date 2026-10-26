# 从这里开始

本项目：Agent-Native Network。主目录：`D:\Multi-Agent Network`。

五个独立角色聊天已创建并完成初始化回执验收。实际聊天与任务绑定见 [窗口登记](coordination/WINDOWS.md)，总控交接见 ORG-002 任务卡。002阶段的原baseline评估与组件审计已完成。003阶段科研框架已完成。S1接口与原协议实测已验收并推送，M-004已完成；结果和下一因果闭环入口见当前摘要。

## 五个窗口

| 窗口名称 | 主要工作 | 启动说明 |
|---|---|---|
| M \| Research Lead | 定目标、拆任务、协调文件写入、验收集成 | [M](coordination/roles/M.md) |
| E1 \| Core Experiments | 原始 baseline 复现、核心方法和主实验 | [E1](coordination/roles/E1.md) |
| E2 \| Validation & Ablation | 独立验证、消融、稳健性与公平比较 | [E2](coordination/roles/E2.md) |
| C \| Repository Auditor | 代码、结果来源、结论边界与交接审计 | [C](coordination/roles/C.md) |
| D \| Research Repository | 文献、来源版本、证据与研究资料索引 | [D](coordination/roles/D.md) |

## 每次接手只读这些

1. [协作规则](AGENTS.md)及本角色启动说明。
2. [当前摘要](coordination/CURRENT.md)：区分研究记录与本机核实状态。
3. [任务索引](coordination/TASKS.md)中分配给自己的任务卡，先看交接检查点。
4. 任务卡指定的资料；需要时再查原研究计划和历史结果。

开始修改前用 `git status --short --branch`、`git rev-parse HEAD` 核实当前工作副本。用户直接交办的新任务由 M 补入任务卡，避免只留在聊天里。

如果当前位于独立 worktree，实时管理文件仍读取 `D:\Multi-Agent Network\coordination\`，不要用 worktree 中的旧任务卡替代主卡。任务卡会登记自身绝对路径及当前状态写入者。

## 管理入口

- 最新阶段：[固定无线条件下的业务与任务](research/agent_native_network/WIRELESS_EXECUTION_STAGE.md)。M-009已完成60回放与18任务，参数合同、模型范围、机制诊断及下一步见该报告；当前验收和进程以CURRENT及主卡为准。
- 当前最新实验：[需求执行链条与首轮规模结果](research/agent_native_network/DEMAND_EXECUTION_STAGE.md)。M-008完成30回合与运行时信息账本、共同恢复；9/18/36节点任务已跑通。验收、进程和下一步以CURRENT及M-008任务卡为准。
- [组织架构与目录分工](coordination/README.md)
- [窗口登记与换窗方法](coordination/WINDOWS.md)
- [架构决策](coordination/DECISIONS.md)
- [任务卡模板](coordination/templates/TASK.md)
- [实验来源模板](coordination/templates/RUN_MANIFEST.json)

项目研究背景继续从[原 README](README.md)进入。`simulation/AGENT_COLLAB_PROTOCOL.md` 描述研究中的通信仿真，不是本机窗口协作规则。

当前研究总入口为[需求驱动研究链条](research/agent_native_network/DEMAND_DRIVEN_RESEARCH_CHAIN.md)：以多态团队的实际协作需求和扩展为起点，按需求与成本测量选择网络机制。[可扩展性全面分析](research/agent_native_network/SCALABILITY_COMPREHENSIVE_ANALYSIS.md)及首版[科研链条](research/agent_native_network/RESEARCH_EXPERIMENT_CHAIN.md)保留为模型和实现参考。M-006完成58任务回合、6固定回放，见[阶段结果](research/agent_native_network/CAUSAL_SERVICE_STAGE.md)；M-007只读其中45个主回合建立[需求与成本账本](research/agent_native_network/DEMAND_CENSUS.md)。最新验收与交接见coordination/CURRENT.md；各阶段实验预算互不自动延续。
