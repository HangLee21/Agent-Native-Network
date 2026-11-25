# E2-006：配对规模目录归档

2026-10-26。逐字节保存`simulation/outputs/E2-006/20261026-01/`共62份文件、360,543字节，原始文件保留。[ARCHIVE_MANIFEST.json](ARCHIVE_MANIFEST.json)包含源/存储路径与SHA-256。

seed5/6各含作者9节点/60任务原始initial和主目录，按任务前缀及完整9节点能力配置复制构成10个不同配置。固定总任务15与固定每节点5/3任务两族共享9/15起点。目录前缀、原9节点及能力副本核验通过，20次初始策略前向及5项结构测试通过；完整任务回合另见[E1归档](../2026-10-26-E1-006-execution/README.md)。

[20261026-01/catalog_index.json](20261026-01/catalog_index.json)索引任务目录和hash，[manifest](20261026-01/manifest.json)保存生成命令、来源与单步检查。文件中的绝对路径是原机记录，跨机器应以归档相对位置恢复并核对hash。manifest和本说明为归档新增元数据，不计入62份源文件。

报告：[规模目录检查](../../../research/agent_native_network/SCALE_ENTRY_PREFLIGHT.md)、[阶段判断](../../../research/agent_native_network/DEMAND_EXECUTION_STAGE.md)。验证：[C独立审查](../../../coordination/reviews/C-008.md)、[M一致性](../../../coordination/reviews/M-008-consistency.json)。
