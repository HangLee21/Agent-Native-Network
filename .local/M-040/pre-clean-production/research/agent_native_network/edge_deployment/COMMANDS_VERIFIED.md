# 命令核对范围

D先前01-command-check实际运行JSONL入口--help和离线profile生成，未开串口。正式指南现已使用E2发布的`python -m tools.mid_edge.example deploy/recv/send`及JSONL`python -m tools.mid_edge`真实参数；本次02-release-docs再次仅运行--help并核profile/package哈希。

H012/14真实运行同一JSONL入口；E2-023/04、05沿原始本地CLI/串口核字节、身份、复位、无屏。D没有为写文档再发包。示例文字“你好，C！”的UTF8为13字节，e4bda0e5a5bdefbc8c43efbc81；二进制例00ff6869。它们是可执行应用示例，不冒称D已额外发过这两条示例。

本轮当前端口A COM12/B COM10/C COM7，全部命令显式--baud 460800。E2 README中较早的端口映射为历史，以QUICKSTART与本轮MAC核验记录为准。
