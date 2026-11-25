# D-004 实测归档

正式采纳 `20261025-02`；其余目录保留试运行、失败或中断记录。详细说明见仓库 research/agent_native_network/ 中对应运行报告，独立审查见 coordination/reviews/C-004.md。

ARCHIVE_MANIFEST.json 逐文件记录原始输出路径、原始 SHA256、存档 SHA256 和字节数。大于64 KiB的JSON/JSONL使用mtime=0的gzip压缩，解压即恢复原始字节；其余直接复制。旧输出、旧源码和旧结果未覆盖。运行中data/环境依赖不打包，固定来源和恢复方法在各run清单及报告中。
