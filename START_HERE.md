# 从这里开始

最近完成：[M-015网络主线框架](coordination/tasks/M-015.md)：以已发表成熟网络论文为依据，固定计算条件，聚焦动态多跳网络服务与扩展成本；已通过C-016独立终审并由M验收，本轮只做框架与实验设计。

Agent-Native Network；主目录：`D:\Multi-Agent Network`。

每次接手先读[协作规则](AGENTS.md)、[本角色说明](coordination/README.md)、[当前摘要](coordination/CURRENT.md)和[任务索引](coordination/TASKS.md)中分配的主任务卡；再按卡读取指定资料。先核实分支、提交和Git状态，保留已有修改。

最近完成：[M-014真实模型A0执行阶段](coordination/tasks/M-014.md)，已通过E2核验、C-015独立终审并由M验收；[阶段报告](research/agent_native_network/A0_EXECUTION_20261028.md)。累计4次worker、3次真实生成，加载已跑通，严格JSON工具协议未通过；A0尚未整体通过，协议与输出适配属于后续真实业务链；固定业务的网络实验可独立推进。

实验进度总览：[完整实验框架与当前位置](research/agent_native_network/EXPERIMENT_FRAMEWORK.md)。按研究阶段查看输入、实现入口、完成证据和下一步；[M-013](coordination/tasks/M-013.md)已通过C-014独立核对并由M验收；后续每阶段完成后更新总览对应行。

历史阶段[M-012前置实现与有限兼容验证](coordination/tasks/M-012.md)：[阶段报告](research/agent_native_network/PREPARATION_20261028.md)已通过C-013独立终审并由M验收。模型资产与隔离环境已取得，该阶段真实模型前向为0（其后M-014已完成3次生成）；原生ns-3已完成两次动态两跳微场景。研究主线保持M-011修订。

最近完成[M-011方向纠偏](coordination/tasks/M-011.md)，完整要求见[用户任务](coordination/handoffs/M-011-user-request.md)。文献、架构模型与实验规划已通过C-012独立终审并由M验收；后续执行按新任务卡启动，旧计划不自动驱动执行。

最近完成[M-010详细研究报告](coordination/tasks/M-010.md)：D撰写、E2核对数据、C独立终审，M已验收。阅读[详细报告](research/agent_native_network/RESEARCH_PROGRESS_AND_PROBLEM_STATEMENT.md)；本轮没有运行新实验。

最近完成[ORG-003](coordination/tasks/ORG-003.md)独立窗口接管及文档修正，已通过C-010终审并由M验收。实际五窗口及本轮任务见[窗口登记](coordination/WINDOWS.md)。用户已授权向既有四角色窗口发送任务；实际进度只以主卡和交付物为准。

当前框架：[已发表论文支撑的网络研究框架](research/agent_native_network/NETWORK_RESEARCH_FRAMEWORK.md)（M-015整合，C-016终审通过，M已验收）。方向沿革：[动态可扩展具身边缘智能网络修订](research/agent_native_network/RESEARCH_REORIENTATION_20261027.md)（M-011整合，C-012终审通过，M已验收）。此前[需求驱动研究链条](research/agent_native_network/DEMAND_DRIVEN_RESEARCH_CHAIN.md)保留为历史探索。最近保存实验：[009无线阶段](research/agent_native_network/WIRELESS_EXECUTION_STAGE.md)。更早阶段沿研究文件和当前摘要的历史链接查阅。

管理规范：[目录与流程](coordination/README.md)、[组织决定](coordination/DECISIONS.md)、[任务卡模板](coordination/templates/TASK.md)、[实验来源模板](coordination/templates/RUN_MANIFEST.json)。角色说明：[M](coordination/roles/M.md)、[E1](coordination/roles/E1.md)、[E2](coordination/roles/E2.md)、[C](coordination/roles/C.md)、[D](coordination/roles/D.md)。

独立worktree仍读取主目录coordination中的实时任务卡。`simulation/AGENT_COLLAB_PROTOCOL.md`是科研仿真说明，不是窗口协作规则。
