# 原生协作需求与维护成本：只读复算归档

2026-10-26，E1-005/M-007。这里保存对006阶段主45回合的派生统计，没有新增任务策略或无线运行。10个instant实例描述能力需求与维护方式，35个延迟/FIFO回合单列为诊断；节点数均为9。

| 目录 | 内容 |
|---|---|
| [20261026-01-census](20261026-01-census/) | 45回合统计、750逐任务行、8847逐消息行、原因分组、统计定义及输入/输出hash |
| [20261026-02-verification](20261026-02-verification/) | 5项语义测试的实际stdout/stderr、退出码、命令及冻结源码 |

M用[归档脚本](../../../coordination/reviews/M-007-archive.py)逐字节复制12份文件，共1449689字节。原始输出保留；[ARCHIVE_MANIFEST.json](ARCHIVE_MANIFEST.json)记录每个来源、归档路径、字节与SHA256。`.gitattributes`禁止此目录的换行转换。

主要结果及解释见[需求与成本报告](../../../research/agent_native_network/DEMAND_CENSUS.md)。10个instant实例包含175项任务，其中139项存在单机器人能力解，36项至少需要多人；实际85项多人开工。1738条广播产生538419应用字节、13904份接收副本。缓存引用是读取路径统计，不是信息价值或可删除流量。

复算入口为[simulation/demand_census.py](../../demand_census.py)。脚本拒绝已存在的输出目录，复算需使用新的run-id；它仅使用标准库，不加载任务环境或权重。原始45回合仍位于[006归档](../2026-10-25-E1-004-causal/)，此次输入manifest逐项记录其存储/解压hash。新目录中的源码副本用于核对版本，执行时使用仓库根目录下的复算入口。

独立审查见[C-007](../../../coordination/reviews/C-007.md)；当前研究顺序见[需求驱动链条](../../../research/agent_native_network/DEMAND_DRIVEN_RESEARCH_CHAIN.md)。
