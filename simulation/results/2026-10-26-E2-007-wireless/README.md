# E2-007 固定业务回放与任务闭环归档

2026-10-26。完整保存`simulation/outputs/E2-007/`的547份源文件，原始1,001,006,825字节，归档44,094,619字节。原始文件保留，未覆盖旧实验。60次固定回放均完成，18个任务回合均成功；没有额外任务调参回合、训练、异常或预算停止。

- `20261026-00-preflight`：7项接口测试、18个冻结配置、原合同和源码hash。
- `20261026-01-replay`：10条008真实消息轨迹×3个MAC种子×FIFO/latest，共60次；每次记录原窗口与排空结果。
- `20261026-02-task`：6个任务目录×事件FIFO/事件latest/20秒刷新，共18回合；源码、权重来源、完整消息/信息账本及物理事件。
- [20261026-03-analysis/cases.csv](20261026-03-analysis/cases.csv)：逐任务指标；同目录有描述统计及有限诊断。
- 最终机制诊断为`20261026-03-analysis/mechanism_trace_v2.json.gz`，v1保留过程版本；v2按事件ID截取决策前物理状态。生成脚本同目录保存，没有新增策略回合。

[ARCHIVE_MANIFEST.json](ARCHIVE_MANIFEST.json)逐文件记录原始与存储SHA-256、路径和大小。超过64KiB的JSON/文本压缩为gzip，其余逐字节复制；解压后应与原始hash相同。归档manifest和本说明为新增元数据，不计入547份源文件。

运行配置中的绝对路径为原机记录。跨机器复算应按manifest的相对路径恢复原输出布局，补齐旧008/006参考归档及已核验作者资产；压缩文件先恢复原名。C复算器读取这些原始布局，M保存核验直接检查归档内容，无需重新运行任务。完整作者权重与本地环境仍按仓库资产说明取得，本归档不重复打包。

运行目录内的`WIRELESS_SERVICE_CONTRACT.md`是结果前原文快照，逐字节保留；其中相对链接仍以`research/agent_native_network/`为基准。阅读与导航使用上方所链接的仓库合同，保存检查同时验证快照字节及按原位置解析的链接。

报告：[阶段判断](../../../research/agent_native_network/WIRELESS_EXECUTION_STAGE.md)、[执行细节与机制诊断](../../../research/agent_native_network/WIRELESS_EXECUTION_IMPLEMENTATION.md)、[固定无线合同](../../../research/agent_native_network/WIRELESS_SERVICE_CONTRACT.md)。验收：[C-009](../../../coordination/reviews/C-009.md)、[M-009保存检查](../../../coordination/reviews/M-009-consistency.json)。

当前模型是固定物理参数的简化单竞争域。应用字节、帧字节、尝试发射时间、信道busy并集和接收副本分别统计；广播帧级分位数与接收副本分位数区分样本单位，原窗口与排空统计均保留。18个任务只含两个任务种子、一个闭环MAC种子，不能从回放重复数推出任务泛化样本量。
