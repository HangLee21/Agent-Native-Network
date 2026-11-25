# E1-007 竞争广播服务证据

2026-10-26。来源为`simulation/outputs/E1-007/`，原始文件全部保留。两轮运行共10份源文件，原始336,343字节，归档79,555字节。首轮16项、补充后终轮17项测试均通过；17个独特语义测试，没有任务策略回合。

[终版测试manifest](20261026-02-tests/manifest.json)保存解释器、命令和源码hash，同目录含原始测试日志、完整微场景账本及源码快照。[ARCHIVE_MANIFEST.json](ARCHIVE_MANIFEST.json)逐文件保存源路径、存储路径、大小和原始/存储SHA-256；超过64KiB的JSON以gzip无损保存，解压后应匹配原始hash。manifest和本说明为归档新增元数据。

服务源码为简化单竞争域广播模型：20MHz/6Mbps参数、同slot批量竞争、忙时冻结、双快照latest及真实空口计费，具体见[服务说明](../../../research/agent_native_network/WIRELESS_SERVICE_IMPLEMENTATION.md)和[固定合同](../../../research/agent_native_network/WIRELESS_SERVICE_CONTRACT.md)。没有执行ns-3或实际设备无线实验。

验收：[C-009](../../../coordination/reviews/C-009.md)、[M-009保存检查](../../../coordination/reviews/M-009-consistency.json)。任务与回放结果另见[E2归档](../2026-10-26-E2-007-wireless/README.md)。跨机器独立复算若使用原始输出路径，按manifest恢复相应目录并校验hash。
