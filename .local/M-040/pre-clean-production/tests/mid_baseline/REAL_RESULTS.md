# ABC实际有限通信：E2独立结果核对

2026-11-06。对H已完成的四次真实RF日志独立分析，**24条源唯一接纳均匹配24条目的唯一rx_local；受控AC双向6条均有完整源—B中继—目的链，payload与原host发送命令一致**。这不是新增RF运行或包重验。

| 原始H运行 | 双向源接纳/目的唯一收到 | 完整受控两跳链 |
|---|---:|---:|
| 17-AB-RF | 10/10（5+5） | 不适用 |
| 18-AC-RF | 4/4（2+2） | 不据此宣称两跳 |
| 19-BC-RF | 4/4（2+2） | 不据此宣称两跳 |
| 20-controlled-two-hop-RF | 6/6（3+3） | 6/6 |

每条按origin/origin_boot/seq/dst配对，所有24条身份跨本批次唯一。源tx_queued只是接纳；另外查源tx_submit、真实send命令nonce/ok及payload，再与目的rx_local配对。6条受控链同时查源tx_submit next_hop=B、B rx_relay及tx_submit next_hop=终点、目的rx_local；每一段原文件和行号保存在identities.json。NATIVE-01修正分析器对受控两方向均给true，此结论另由独立连接代码重建，不仅转述H汇总。

四个run的实际native/context/plan/result及各板UART raw.bin对H证据索引一致；每块raw.bin解析出的MID事件多重集合与native.jsonl中该板事件完全一致。固定build/本次boot、context来源、两端/三板base-final stats、coverage、stop与锁定状态由当前分析器核对，无日志完整性issue。每流此次观察PDR=1仅描述这些少量包，不表示统计可靠性估计、长期吞吐、范围或QoS收益。原始boot不替换为示例boot，未重编或重新核未改52件包。

H报告所有stop确认及端口关闭，E2核对了日志中的最终radio=false/stopping=false/locked=false及其结果记录；不把H报告物理句柄状态写成E2亲自操作。E2本轮串口/刷写/RF均0。H记录四次host控制窗口合计41.561997秒（含配置/串口/排空，不是PHY空口时长），仍在原6次/360秒预算内。

受控输入在模型中逻辑禁AC直接边，实际证据支持A→B→C与C→B→A转发功能，**不能推断RF直连不可达、覆盖增益、QoS达标或自主恢复**。三板均已作为源和目的，只有B在本受控case中验证为中继，不能外推A/C转发已实测。源MID仍目的未确认，未增加ACK；RTT、RF重试、PHY airtime保持null。显示驱动READY不等于像素/PRG物理验证；H004旧确认和用户对C字母?的询问不等于三板新版OLED完整确认。

结果：simulation/outputs/E2-016/20261106-12-real-data-review/summary.json；24条逐身份/行号见identities.json；各run修正原生audit另存同目录，不改H已有native-analysis或原始文件。分析入口tools/mid_baseline/validation/review_real.py，实际执行0.078秒；manifest记录输入文件SHA、代码SHA和无新增设备操作。保留H首次A工具参数写前失败（write_calls0）与旧E2失败，未为缺项追加硬件run。该实际结果交C独立终核、M验收，E2不自行done。
