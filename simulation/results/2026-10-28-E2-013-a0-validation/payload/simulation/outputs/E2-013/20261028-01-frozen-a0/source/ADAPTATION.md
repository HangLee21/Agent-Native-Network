# M冻结后适配记录

2026-10-28，正式核验前适配，尚未消耗正式运行次数。冻结来源：coordination/reviews/M-014-freeze.json，SHA256 `ebd13fd8df0b5dddb0236211a87154d286860054d3c4a208ee75a51eed13cc06`。M主卡确认E1 completed/review停写；596项先行哈希比对一致。

准备版依据旧E1-010结构，冻结E1-012实际结构改为顶层worker-NN、append-only worker_reserved/finished/formal_preflight事件、task-card-snapshot.md及仅含ID的私有context。适配为分别重建这些关系；嵌套回归中的mock call/worker目录不计真实worker。

M已在E1-012明确修订直接CUDA+父进程RAM监测：该模式启动1.5GiB、运行时低于512MiB停止；03默认仍2GiB，显存2.5GiB及调用/token/时间预算不变。判据保留默认值，新增条件模式值；核对执行时卡快照及配置，不用核验时空闲资源替代。此为执行门槛变更，不降低视觉、JSON或引用兼容的能力判据。

证据一致性与能力结果拆开。资源受阻/保护停止本身不是证据不完整；未生成时，JSON/引用/颜色均未测，不能把E1评分器空字符串产生的false当视觉误判。只有真实生成时才评价工具/语义。现有真实worker只留loading；不要求本来不存在的processor张量、版本/GPU峰值或生成输出来通过“受阻记录一致性”检查，仍将这些能力标未建立。

03旧manifest缺config_sha256，由M冻结与归档绑定其配置并明确缺项；不改原始manifest。05/09/10为后补辅助manifest，时间/命令未知保持null，仅据保存文件核辅助检查，不当正式模型运行。脚本检查运行清单、全部失败、归档原字节、原始RAM曲线、保护回收、账本以及07/08/当前最终源码一致，正式输出另存公共manifest。

PREPARATION.json是准备时原记录，保留原字节和旧脚本hash。本适配的最终hash记入实际核验manifest与E2主卡，不回写历史准备记录。除逐文件hash、AST/JSON静态解析和人工读取外，正式运行前未执行结果验证器、模型、E1模块或E1检查脚本。
