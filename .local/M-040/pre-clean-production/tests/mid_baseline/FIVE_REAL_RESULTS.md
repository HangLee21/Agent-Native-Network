# 五板实际结果：E2独立核对

2026-11-07。**120/120条源业务逐身份对应唯一目的rx_local，payload均与真实host send命令一致；其中20/20条受控四跳具有完整逐跳证据。** 这是对H12次既有真实采集的一次离线分析，E2没有操作设备、追加RF或重验未改包。

| 范围 | 本轮实际核对 |
|---|---|
| 任意对端 | AB/AC/AD/AE/BC/BD/BE/CD/CE/DE双向，20个方向各5/5，合计100/100 |
| 链1 | A-B-C-D-E及逆向，每向5/5，10条完整四跳 |
| 链2 | B-A-D-E-C及逆向，每向5/5，10条完整四跳 |
| 唯一身份 | 120条origin/origin_boot/seq/dst在本批次均唯一 |
| 内容 | 120条payload与原host命令相符，命令nonce均有唯一成功回执 |
| 原始来源 | 每场景各板raw.bin解析MID事件与native.jsonl对应节点事件多重集合完全一致 |
| 结束 | 原日志base/final stats、boot/build、coverage及stop状态通过；H结果均报告端口关闭 |

内部中继证据累计消息数：A=10, B=10, C=10, D=20, E=10。两个链的内部角色并集覆盖ABCDE；不是只核B，也不把首个中继的MAC callback当目的收到。逐消息先查源tx_queued和实际tx_submit，再依次查三个内部节点rx_relay与tx_submit（实际next_hop须为下一节点），最后查目的rx_local。每段原文件/行号与payload在identities.json；每例修正后的five audit另存同输出。NATIVE-01源实际提交条件继续保留。

采集同build=mid-v1-a9a060af8512b126b7a8679d85bf5070803bb5b9796b442f030cfb124dca42ad，按每场景实际boot关联，不用示例boot1。统一包/刷写次数/DE备份与恢复按H提供的设备证据报告；E2没有重新读设备或重复核整包。D备份第三段原失败及一次有据恢复、三板旧24条/6链结果均保留，不覆盖。

H控制采集窗口合计168.424994秒/720秒、12/12场景，源业务120条；这是host场景时窗（含控制/串口/排空），不是RF PHY airtime。每方向此次观察PDR=1仅描述本次5个包，不能当长期可靠性、吞吐、规模能力或QoS估计。实际SOCP逻辑限制形成指定链，不意味着真实RF直连断开、遮挡被自主发现或覆盖范围提升。MID源端仍目的未确认，没有新增端到端ACK。RTT、RF重试、PHY airtime未知。OLED驱动READY是软件首帧状态，五板新版完整像素/PRG用户观察仍未确认，不从旧H004实物确认外推。

证据入口：simulation/outputs/E2-016/20261107-05-real-five-review/summary.json、identities.json、十二个独立audit、RUN_MANIFEST.json。独立分析入口tools/mid_baseline/validation/review_five_real.py；本次0.812秒，新阶段受控检查/分析约1.624秒/3600秒（01测试路径失败保留）。只核新采集原始来源和关键链，不重跑旧包/构建/三板套件。E2全部命令退出、串口/Flash/RF0，无后台或轮询。结果待C独立终核/M验收，不自行done。
