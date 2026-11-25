# 研究来源与运行记录导航

2026-10-26，D-007。依据现有本地记录整理；本次没有联网、下载、执行实验或重新核验外部论文。历史执行分工M-002至M-009来自M聊天内子代理；本轮独立角色窗口接管见[CURRENT](../../coordination/CURRENT.md)，独立C窗口复核见[C-010任务卡](../../coordination/tasks/C-010.md)。历史报告中的C标签保留其原义，不代表当时由既有C聊天执行。

## 研究进度与证据入口

| 阶段 | 已保存记录 | 使用边界 |
|---|---|---|
| 007需求账本 | [需求链条](DEMAND_DRIVEN_RESEARCH_CHAIN.md)、[账本复算](DEMAND_CENSUS.md) | 原生需求与交付条件诊断分列；缓存读取不直接证明信息贡献。 |
| 008运行时与规模 | [执行阶段](DEMAND_EXECUTION_STAGE.md) | 已有运行时关联、共同恢复及规模实例记录；属于保存结果，本次未重跑。 |
| 009简化无线 | [阶段报告](WIRELESS_EXECUTION_STAGE.md)、[E2-007归档说明](../../simulation/results/2026-10-26-E2-007-wireless/README.md) | 60固定回放和18任务为历史记录；单竞争域不覆盖空间复用、路由与完整无线系统。 |
| 后续候选 | [NEXT_STEPS](NEXT_STEPS.md)、[应用需求](demand_20261026/APPLICATION_REQUIREMENTS.md) | 状态恢复及应用需求扩展须另立任务；W1–W3尚未实现。 |

## baseline来源与复现记录

| 资料 | 内容与证据范围 |
|---|---|
| [任务筛查](TASK_SCHEDULING_SCREEN.md) | 7组候选的适用性与来源入口；其中初始化状态是历史快照，最新HeteroMRTA进度看其顶部更新及复现报告。 |
| [初始源码筛查清单](task_baseline_sources.json) | 固定3仓库commit、14份源码/说明/许可文件的URL与SHA-256；weights仅记路径和大小，不能单独作为可校验权重下载清单，也不覆盖全部候选。 |
| [HeteroMRTA复现报告](HETEROMRTA_REPRODUCTION.md)与[正式结果](../../simulation/results/2026-10-23-E1-002-heteromrta/INTERPRETATION.md) | 原权重与作者Greedy小实例评估、失败诊断、环境记录及来源恢复入口；不能等同论文表格复现。 |
| [MOCHA / AutoCast组件记录](NETWORK_BASELINE_RUNTIME.md) | 固定作者版本、取得范围、许可及组件探针；不代表完整ROS/CARLA或竞争无线运行。 |
| [MOCHA原同步运行入口](MOCHA_RUNTIME_ENTRY.md) | 后续原状态机运行记录；与上述组件记录分开使用，具体已验证范围以该报告为准。 |
| [009任务manifest](../../simulation/results/2026-10-26-E2-007-wireless/20261026-02-task/manifest.json) | 保存作者commit、10项资产URL/hash、case配置与源码hash；HeteroMRTA checkpoint来源在assets中可定位。manifest记录资产，不证明当前机器仍持有对应文件。 |

“来源已定位”“文件已取得”“环境已运行”“结果已复现”分别引用对应证据，不相互替代。本次没有重验忽略目录中的资产、依赖可用性或上游链接。

## 应用合同的适用阶段

[APPLICATION_REQUIREMENTS](demand_20261026/APPLICATION_REQUIREMENTS.md)与[WORKLOAD_CONTRACT](demand_20261026/WORKLOAD_CONTRACT.json)为D-006阶段的需求证据和设计合同，保留原文与空值；`execution_ready=false`。其中指向E1-005的“当前工作”及“时间未映射”是当时阶段状态，不能作为本轮执行授权。

[009无线阶段](WIRELESS_EXECUTION_STAGE.md)采用20秒/模型时间单位、100米/长度单位，是009状态业务实例的统一物理换算，未经设备日志标定。它不自动适用于未执行的W2地图工作流，不能据此追填W2合同的时间参数。W1–W3仍需数据或几何来源、正文编码、消费函数、共同回退及接触/无线配置；45秒/20米仅为合同登记的COHORT原场景规则，不是本项目统一期限。

## 运行manifest与通用模板

通用入口为[RUN_MANIFEST模板](../../coordination/templates/RUN_MANIFEST.json)。[D-007接管记录](../../coordination/handoffs/D-007.md)的“009 manifest抽查与模板映射”逐项说明上述样本如何对应模板字段，保存了受检文件指纹和核查范围。

抽查已确认：归档[task_cases.json](../../simulation/results/2026-10-26-E2-007-wireless/20261026-00-preflight/task_cases.json)与[服务合同快照](../../simulation/results/2026-10-26-E2-007-wireless/20261026-02-task/WIRELESS_SERVICE_CONTRACT.md)的实际SHA-256分别匹配样本的 `case_spec_sha256` 和 `contract_sha256`。未逐项重算资产或任务结果。

样本以 `python`、`author_commit`、`assets`、`cases` 及预算字段保存专用信息；项目Git提交、完整依赖快照、起止时间、退出码等通用字段未直接记录。`source_hashes`不能代替完整脏工作区记录，作者commit也不能代替项目commit。缺失范围仅针对该manifest，其他历史证据需按链接另查。

未来运行须使用通用来源字段，并补充实验专用参数：

- 显式保存任务/run标识、工作副本、项目提交与脏文件hash、完整命令、Python和依赖快照、作者版本、数据/权重及配置hash。
- 明确任务与网络种子、预算、输出目录、起止时间与时区、进程/退出状态、限制和审查引用；采集不到的字段标明未知及原因。
- 专用参数保留无线配置、单位映射、恢复规则及case清单，明确它们与通用字段的映射；运行结束后据实际结果更新完成状态。
- 历史manifest保持原字节。需要补充说明时新增有来源的映射记录；无法恢复的历史字段继续保留缺失，不根据目录日期、计划回合数或后续成功报告猜测时间、PID、退出码。

归档路径恢复、压缩文件与原始hash关系按[E2-007归档说明](../../simulation/results/2026-10-26-E2-007-wireless/README.md)处理。跨机恢复所需环境与作者资产另行取得，不能假定归档包含它们。
