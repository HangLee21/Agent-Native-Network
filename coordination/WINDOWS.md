# 窗口登记与交接

五个独立聊天已在本机 Multi-Agent Network 项目创建。它们是本项目的长期角色聊天，和其他机器上的同名聊天分开。

- 项目 ID：`d1d5c8d4-4a2a-460d-90b2-9129ef59bdd8`
- host：`local`
- 五窗口工作副本：`D:\Multi-Agent Network`（同一主目录，无新 worktree）
- 起始分支/提交：`main` / `e724f7a557cf322280f252d394cb8533c8663fc7`
- 组织文件：本地未提交改动；所有窗口已被要求保留
- 任务状态：以各自 INIT 卡和后续研究卡为准；绑定不等于启动
- 本轮范围：仅初始化、写回执、完成交接，不运行实验

| 角色名称 | 实际聊天 ID | 初始化卡 | 后续绑定 | 初始化回执 |
|---|---|---|---|---|
| M \| Research Lead | `01a16824-1141-7202-929b-3b558df47ade` | [INIT-M](tasks/INIT-M.md) | [ORG-002](tasks/ORG-002.md) | [回执](handoffs/INIT-M.md) |
| E1 \| Core Experiments | `01a16824-294e-7eb2-85eb-d98b7a8748f1` | [INIT-E1](tasks/INIT-E1.md) | [E1-001](tasks/E1-001.md) | [回执](handoffs/INIT-E1.md) |
| E2 \| Validation & Ablation | `01a16824-3f4e-7e61-8a83-08d2dd8c82f6` | [INIT-E2](tasks/INIT-E2.md) | [E2-001](tasks/E2-001.md) | [回执](handoffs/INIT-E2.md) |
| C \| Repository Auditor | `01a16824-5c84-7081-8f0c-7e1e94beff35` | [INIT-C](tasks/INIT-C.md) | [C-001](tasks/C-001.md) | [回执](handoffs/INIT-C.md) |
| D \| Research Repository | `01a16824-727d-7fd3-8696-c1a0b9694386` | [INIT-D](tasks/INIT-D.md) | [D-001](tasks/D-001.md) | [回执](handoffs/INIT-D.md) |

## 写入责任

初始化已由搭建聊天 `01a1680c-aba8-7160-a421-31cbe2710e5a` 验收收尾；五窗口各自只写了独占回执。ORG-002 已完成，新 M 已确认接收总控交接，共享管理职责归上表 M 聊天，搭建聊天不再自动参与研究任务。

D-001、E1-001、E2-001、C-001 保持 backlog。角色窗口仅收到任务上下文；以后由 M 根据用户安排激活，不能凭初始化成功就开始执行。

## 以后换窗

同角色的新聊天可追加 02、03。旧窗口保存任务卡、记录进程并停止写入；新窗口核实后 M 更新本登记，同角色只保留一个当前写入窗口。实际任务卡始终位于主目录 `coordination/tasks/`。

恢复提示词：

> 你接手角色 <角色>。主目录为 D:\Multi-Agent Network。先读 AGENTS.md、START_HERE.md、coordination/roles/<角色>.md、coordination/CURRENT.md 和指定任务卡 <任务ID>。核实当前工作副本和交接检查点，简述当前状态、可写范围、下一步；只继续该任务已经授权的工作。若仍为 backlog，报告待办范围后等待，不启动实验。不要重读全部历史聊天。

## 2026-10-25 科研框架阶段

用户要求完整科研链条。M在本聊天集成M-003；临时子代理/root/network承接D-003，/root/heteromrta以E2角色承接E2-003，/root/audit承接C-003。对应独占写入范围见任务卡。长期角色聊天保持原登记，本轮没有跨聊天派发。起始提交dde4cff，分支codex/baseline-reproduction-20261023；进入本轮时工作区干净。

## 2026-10-25 S1实现阶段

按用户“推进”及角色职责，M-004集成；同一聊天内/root/heteromrta承接E1-003，/root/network承接D-004，/root/audit承接C-004独立审计。各卡规定文件/输出范围，互不覆盖。长期角色聊天未发送消息。前一阶段无实验限制已随003完成结束，新实验预算以004卡为准。

004收尾：E1/D/C均停止写入，无实验进程；M按独立证据关闭其任务并释放范围。长期角色聊天未唤醒。后续实现由新卡登记，当前不留后台队列。
