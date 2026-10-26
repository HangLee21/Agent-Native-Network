# E1-006：运行时信息链条与共同恢复归档

2026-10-26。来源为`simulation/outputs/E1-006/`下5个新目录，原始文件保留。30个正式回合：旧规则10回归（8成功、2到H未完成）、共同恢复10成功、规模入口10成功；没有额外任务回合、计算截断或训练。

- `20261026-00-preflight`：结果前测试、固定矩阵、来源hash；另存只读汇总脚本。
- `20261026-01-legacy`：旧规则回归；50组行为日志与旧归档相等。
- `20261026-02-recovery`：相同任务与权重下的共同恢复配对。
- `20261026-03-scale`：9/18/36节点配对目录的完整instant运行。
- [20261026-04-analysis/cases.csv](20261026-04-analysis/cases.csv)：全部30回合数据；同目录保留统计及原始文件清单。

388份源文件原始共259,438,050字节，存储14,001,337字节。大于64KiB的JSON/文本以确定性gzip无损保存；其余逐字节复制。[ARCHIVE_MANIFEST.json](ARCHIVE_MANIFEST.json)逐文件记录源路径、存储路径、大小、原始和存储SHA-256。解压后应匹配原始hash；manifest及本说明是归档新增元数据，不计入388份。

配置中的绝对路径保留原机运行位置。跨机器复算时，根据manifest的相对路径恢复输入，并校验hash；`.json.gz`先解压即可恢复原JSON。本归档不包含作者未跟踪权重/环境，依仓库固定资产说明取得并校验。原执行源码快照和新源码hash保留，当前执行器源码采用`-text`避免Git换行转换改变hash。

C复算器读取原始`simulation/outputs/<任务>/<run>/`布局及旧C-006参考结果。跨机器应先按各manifest恢复这些输入布局再运行；M的归档校验则直接检查压缩文件的存储与解压hash，不需要新任务仿真。

报告：[阶段判断](../../../research/agent_native_network/DEMAND_EXECUTION_STAGE.md)、[实现细节](../../../research/agent_native_network/DEMAND_EXECUTION_IMPLEMENTATION.md)。验证：[C独立审查](../../../coordination/reviews/C-008.md)、[M一致性](../../../coordination/reviews/M-008-consistency.json)。规模实验测量任务自然业务，应用字节与接收副本分列；未实现无线空口服务。
