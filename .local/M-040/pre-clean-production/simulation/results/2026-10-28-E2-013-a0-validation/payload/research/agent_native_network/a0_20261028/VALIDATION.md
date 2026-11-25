# E2-013：A0独立核验结果

2026-10-28，E2独立窗口。**冻结证据一致性核验通过；A0兼容能力仍未建立。** E2模型/下载/训练/仿真均0，正式标准库核验1/2次，未用第二次额度。E1由M冻结后才读取，验收仍由C-015/M负责。

## 冻结版本与独立结果

HEAD `7f92debd36310a7d5e37ef52d23c019138284cdd`。依据[E2-013主卡的M冻结段](../../../coordination/tasks/E2-013.md)，读取[完整清单](../../../coordination/reviews/M-014-freeze.json)，SHA256 `ebd13fd8df0b5dddb0236211a87154d286860054d3c4a208ee75a51eed13cc06`。596项文件执行前后与清单hash匹配，含全部10个run、失败、账本、源码、配置、输入、报告及归档。未读活动输入，无Git写操作、跨聊天发送。

准备版依据旧提交制定判据；冻结后按[适配记录](../../../simulation/edge_agent_validation/ADAPTATION.md)处理新worker目录、append-only账本、私有context及M监测模式。视觉/JSON/引用判据未降低；默认2GiB与经M授权的有监测1.5GiB启动门槛分列。[判据](../../../simulation/edge_agent_validation/criteria.json)及[脚本](../../../simulation/edge_agent_validation/validate_a0.py)不导入E1模块。

正式命令：

```powershell
python -B -X utf8 simulation/edge_agent_validation/validate_a0.py --freeze coordination/reviews/M-014-freeze.json --output simulation/outputs/E2-013/20261028-01-frozen-a0
```

执行前目标目录不存在，退出0。[公共manifest](../../../simulation/outputs/E2-013/20261028-01-frozen-a0/manifest.json)保存Python、源码/判据/卡/冻结配置快照及输入hash；[自动结果](../../../simulation/outputs/E2-013/20261028-01-frozen-a0/validation.json)510项记录一致性检查通过、失败0。该数字是文件/字段核对数，不是独立实验或模型样本。随后完成[冻结源码人工复核](../../../simulation/edge_agent_validation/SOURCE_REVIEW.md)；自动输出保留原字节，其manual_source_review_required标志不回写。

## 事实与能力分别报告

| 核对对象 | 独立核对结果与边界 |
|---|---|
| 全任务账本与预算 | 2次正式预检，1次worker reserved/finished，提示修订0；worker墙时33.203000000008615秒。失败计4次/720秒预算，保护后无新启动/预检；不是预算全部耗尽，也不得据剩余额度自动恢复 |
| 03默认模式 | RAM1939304448 byte低于2GiB，VRAM4621MiB；resource_blocked、worker0。原卡/配置/源码/失败保留，合法资源失败不算证据缺失 |
| 08监测模式 | 卡快照含M直接CUDA+FP16+low_cpu_mem_usage及1.5GiB修订；预检RAM1899212800 byte、VRAM4610MiB通过，启动瞬间RAM2009837568 byte。配置与门槛可查，不保证加载完成 |
| RAM保护 | 原始128行，最大间隔0.26600000000325963秒；末值412577792 byte低于536870912 byte，触发low_system_ram，process/ledger/summary一致。系统可用RAM不是worker进程峰值，不能将全机变化都归因于worker |
| 启动与回收 | 命令指向隔离解释器及08源码；result仅初始loading。PID49936记录已wait回收，保存PID检查未见worker/controller存活。初始save在import torch之前，无本次versions，不能定位停止子阶段；E2未重新枚举全机 |
| 输入/私有提示 | 两PNG独立解码红蓝64×64，CRC/hash对应；spec仅第一张，prompt无预期red/blue，重建context hash匹配。未写prepared或pixel张量，不能说模型已处理图像 |
| 来源身份 | 13项记录与revision、锁、manifest一致，Git blob和LFS正文身份分开。E2核记录与实现，未重读2GB权重/env，不声称本轮独立重算所有模型文件 |
| 回归/版本 | 保存07为35项通过；07/08/当前核心源码一致。嵌套mock不算真实worker；E2未重跑E1回归，35不是模型样本 |

| A0能力维度 | 本次结论 |
|---|---|
| 模型加载完成 | **未建立**；无model_loaded，33.203秒不是加载时延 |
| processor图像张量 | **未测/未建立** |
| 生成started / completed | **0 / 0**；worker启动1另列 |
| JSON及工具格式 | **未测**；没有原始回答 |
| 本地引用合法性 | **未测**；没有原始回答 |
| 红蓝视觉语义 | **未测**；空输出默认false不是实际误判，第二输入worker未启动 |
| 加载/生成GPU峰值、实际依赖快照 | **未取得**；静态元数据/历史导入不补本次缺项 |
| 协作、A1/A2、无线耦合、泛化准确率 | 本轮不提供此类结论 |

## 原字节归档与限制

逐项核E1归档296项与来源、长度、SHA一致，未改E1数据。03旧manifest缺config_sha256，用M冻结和归档绑定保存配置并显式保留缺项；05/09/10辅助manifest后补，未知时间/命令保持null。09 GBK读取UTF-8失败与10修正均保留，不当模型执行。

自动结果SHA256 `8230e2a2374631de4d3130c79c52cd19b258751a5f7b3878bd7b46b88316acf4`；执行manifest SHA256 `ff0a2c9e9dcc671e94498a44b3f1278e2b74c3a08436f3b5b3598bc1e74c19b5`。执行源码/判据hash见manifest及source快照，PREPARATION.json保留准备原版本。

E2记录另归档至`simulation/results/2026-10-28-E2-013-a0-validation/`，仅含E2输出、核验源/判据、人工复核及本报告，不复制模型/env。未发现需E1修复的证据矛盾；A0仍缺实际加载、张量及生成，由M决定新资源/运行时方案并另立卡。不降低判据补成功，不自动重试或恢复剩余名额。

本窗口核验命令已退出，无模型/下载/研究后台进程；交review后停写，待D整合、C-015核对和M验收。
