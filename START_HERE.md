# 从这里开始

本项目：Agent-Native Network。主目录：`D:\Multi-Agent Network`。

五个独立角色聊天已创建并完成初始化回执验收。实际聊天与任务绑定见 [窗口登记](coordination/WINDOWS.md)，总控交接见 ORG-002 任务卡。002阶段的原baseline评估与组件审计已完成。003阶段科研框架已完成。S1接口与原协议实测已验收，M-004负责集成交付；结果和下一因果闭环入口见当前摘要。

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

- [组织架构与目录分工](coordination/README.md)
- [窗口登记与换窗方法](coordination/WINDOWS.md)
- [架构决策](coordination/DECISIONS.md)
- [任务卡模板](coordination/templates/TASK.md)
- [实验来源模板](coordination/templates/RUN_MANIFEST.json)

项目研究背景继续从[原 README](README.md)进入。`simulation/AGENT_COLLAB_PROTOCOL.md` 描述研究中的通信仿真，不是本机窗口协作规则。

当前研究总入口为[科研与实验框架](research/agent_native_network/RESEARCH_EXPERIMENT_CHAIN.md)。本轮按主任务卡开展有限预算的接口与协议运行；最新进展与交接见coordination/CURRENT.md。
