# E2-005 共同消息服务证据归档

2026-10-25。来源为`simulation/outputs/E2-005/`，原文件保留。M在执行者停止写入后归档78份文件，原始约9.0 MB，存储约0.62 MB；所有原始字节与解压还原字节一致。只排除可再生成的Python字节码，具体路径记录在[ARCHIVE_MANIFEST](ARCHIVE_MANIFEST.json)。

- `20261025-01-verification/`：冻结实现及10项标准库测试，退出码0。
- `20261025-02-frozen-pilot/`：E1即时信息首个pilot产生的同一141条消息，在六种服务条件下回放，包含原输入副本、源码快照、参数、事件、交付和截尾记录。

结果与解释见[服务诊断报告](../../../research/agent_native_network/MESSAGE_SERVICE_DIAGNOSTIC.md)。FIFO 2048/4096/8192的交付延迟p95分别为3.2555/0.5631/0.2235个作者模拟时间；该结果仅描述固定业务的共享应用字节服务，不直接推断任务损失。

较大JSON以gzip保存；解压后可按原JSON读取。每份文件的原始/存储SHA256和压缩方式见manifest。`.gitattributes`禁止对本归档做换行转换，保证跨平台字节来源一致。回放工具当前读取JSON/JSONL，使用压缩输入前须解压到新的临时文件。
