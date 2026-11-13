# ABC三板MID实际运行结果

2026-11-06。H已完成A/B/C各一次实际刷写、启动和四组无线小包运行：源端唯一受理24包，目的端匹配唯一接收24包；受控两跳6包均有完整源—中继—目的身份关联。E2随后独立复核原始日志，确认24条身份、payload和6条两跳链均匹配。**C最终验收尚未定向交付D，不写成最终验收通过**。D整理H/E2固定证据，未重跑分析器、实验或设备操作。

## 设备、固件与启动

实际使用package-01，manifest SHA256 `d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683`，运行build_id为`mid-v1-99e77eba7e472bd687ea18321d6ac566e9e8b21d764431e1b42ec7fee945c2f3`。本轮不再全面复核旧包。作者机制仍按已记录的miod候选提交适配，未改称TRO原实验精确复现；来源说明沿用 [SOURCE_AUDIT.md](SOURCE_AUDIT.md)。

| 板 | 实际MAC | 本次MID boot_id | 刷写/启动 | 字母标签 |
|---|---|---:|---|---|
| A | `90:da:72:48:a4:f8` | 1771240051 | 1次实际写入，启动身份已读 | A |
| B | `90:da:72:48:a5:cc` | 1703315987 | 1次实际写入，启动身份已读 | B |
| C | `90:da:72:48:a4:e0` | 1198675223 | 1次实际写入，启动身份已读 | ?，MAC正确 |

设备身份与备份准备见已有ABC侧记；本次应用结果见H的 [21号汇总](../../../simulation/outputs/H-005/20261106-21-real-results/result.json)。刷写、启动原文保留在`simulation/outputs/H-005/20261106-16-MID-deploy/`的A、A2、B、C子目录；A为首次工具失败，A2才是实际成功写入，不能把目录数算成两次A刷写。

## 四组实测

下表“接收/受理”按原始`origin/origin_boot/seq/dst`关联源端唯一受理和目的本地唯一接收，未把TX回调或中继接收计为交付。每包用户payload为16byte。方向计数来自H原生分析，已获E2本轮独立复核，D未复跑。

| 场景及原始结果入口 | 正向接收/受理 | 反向接收/受理 | 总计 | host控制窗口 |
|---|---:|---:|---:|---:|
| [17号AB](../../../simulation/outputs/H-005/20261106-17-AB-RF/native-analysis.json) | A→B 5/5 | B→A 5/5 | 10/10 | 12.577999s |
| [18号AC](../../../simulation/outputs/H-005/20261106-18-AC-RF/native-analysis.json) | A→C 2/2 | C→A 2/2 | 4/4 | 9.328999s |
| [19号BC](../../../simulation/outputs/H-005/20261106-19-BC-RF/native-analysis.json) | B→C 2/2 | C→B 2/2 | 4/4 | 9.187000s |
| [20号受控两跳](../../../simulation/outputs/H-005/20261106-20-controlled-two-hop-RF/native-analysis.json) | A→B→C 3/3 | C→B→A 3/3 | 6/6 | 10.467999s |

四组共4次运行、host控制窗口合计41.561997s，含配置、串口和排空，**不是PHY空口时长**。24/24为本次小样本观察计数；各方向本次PDR为1.0，不支持长期可靠性、最大吞吐、覆盖距离或模型QoS达标的结论。native分析中的goodput按本次低发包量和采集窗口计算，不作为无线容量结果。

各run目录保存plan.json、native.jsonl、各板原始串口文件、info、context、result和native-analysis；[EVIDENCE_INDEX.json](../../../simulation/outputs/H-005/20261106-21-real-results/EVIDENCE_INDEX.json)给出具体来源路径。H的固定[observations](../../../simulation/outputs/H-005/20261106-21-real-results/observations.json)与[运行manifest](../../../simulation/outputs/H-005/20261106-21-real-results/RUN_MANIFEST.json)保留执行范围和限制。

### E2独立结果复核

[E2实际结果报告](../../../tests/mid_baseline/REAL_RESULTS.md)及[summary](../../../simulation/outputs/E2-016/20261106-12-real-data-review/summary.json)确认：24条数据身份跨本批次唯一，源端实际send命令的payload/nonce成功回执、源tx_queued/tx_submit与目的rx_local逐条对应；6条两跳链还逐条核源的next_hop=B及B转发next_hop=终点。每板raw.bin解析出的MID事件多重集合与native.jsonl一致，实际context/boot/build、base/final stats及最终停止状态也已核。

逐身份原文件/行号在[identities.json](../../../simulation/outputs/E2-016/20261106-12-real-data-review/identities.json)。E2使用NATIVE-01修正分析器，并用另外的身份连接代码独立重建结论；修正audit结果另存其12号目录，未改H旧native-analysis或原始日志。E2未新增设备运行或重验未改包；C最终审查/M验收仍单列。

### 两跳实际发生的依据

20号汇总记录：中继B有6条rx_relay、6条指向最终目的的tx_submit，均能与源端发送和目的rx_local按同一数据身份关联；两个方向各3条。A源的数据为boot1771240051、seq8/9/10、dst=C；C源的数据为boot1198675223、seq5/6/7、dst=A。native-analysis中的relay_evidence和identity_evidence保留原日志文件及行号，两个方向controlled_forwarding_verified均为true。

因此，H实测报告支持“这6包完成了经过B的两跳转发功能”。该场景在SOCP输入图中对A–C施加逻辑禁直连条件，不能解释为实测RF直连不可达、算法发现遮挡或覆盖收益。B只在此case作为中继；A/C本次中继能力未直接测量。三板能彼此作为业务源/目的，不等于所有板的转发能力已分别实测。日志未给TTL观测，不声称实测TTL变化。

## 停止、显示与控制事件

四组所有参与板stop均确认，H报告全部串口关闭；E2另核日志最终radio=false/stopping=false/locked=false，不把句柄关闭写成E2亲自操作。H汇总设备耗时保守上界722.969/1500s，C增量382.688/600s；RF运行账本使用4/6次、host窗口计时41.561997/360s，没有追加RF运行或业务失败重发。设备耗时账本对每次采集保守计45s，与实际host窗口是不同量，二者均不是PHY airtime。

H原生分析记录各场景控制API提交次数依次为6、9、9、9；这是应用提交观测，不是RF重传数或空口占用。控制字节和airtime未取得，不由提交次数推算。

原package-01三板display_hw均为2，表示记录到I²C首帧READY；它不能证明整屏像素、各页内容或PRG动作已由人确认。C当时显示`?`符合package-01预设，完整MAC正确。随后H仅向C的0x10000写入package-02修正版app，build为`mid-v1-bbf80a4ee3b4101bca1d625c6a62b4542384c9d873fdf048737faa92525b71a4`、boot为124817285；用户明确确认“显示 C，翻页正常”。[用户实物确认](../../../simulation/outputs/H-005/20261106-22-C-label/USER_CONFIRMATION.md)及[写入结果](../../../simulation/outputs/H-005/20261106-22-C-label/result.json)支持C标签与PRG观察已完成，不外推A/B显示或所有页面。A/B仍为package-01；上述24/24交付及6条两跳链仍属于原package-01/原boot，标签修正没有新增RF。旧ANN+OLED确认不外推本次MID版本。MID源端没有目的ACK，源显示仍应是目的未确认；目的本地rx_local不等于源已经得到无线确认。

## 失败及未测项

实际部署保留一次A工具失败：[A/result.json](../../../simulation/outputs/H-005/20261106-16-MID-deploy/A/result.json)记录`guarded_write()`缺少`options`参数的TypeError，write_calls=0、RF_started=false、closed=true。修正工具调用签名后A2完成一次实际写入；该失败不能算一次失败刷写或无线丢包，也没有从记录中删除。

四个实际RF场景的H结果均success=true、error=null，未报告本次业务接收缺失；这不意味着异常队列、回调超时、故障隔离等路径都做过物理测试。

| 尚未取得/验证 | 本报告的处理 |
|---|---|
| C最终审查及M验收 | E2独立结果已交，C/M最终结论尚未收到 |
| A/B新版OLED及三板所有页面像素 | 未全面确认；C的package-02标签和PRG已获用户确认，READY仍单列 |
| 端到端RTT | null，无相关endpoint ACK/源时钟往返依据 |
| RF重传次数、airtime、控制实际空口成本 | 未知，不从API回调推算 |
| 物理信道标定、吞吐容量、覆盖/QoS收益 | 未测；假设模型不当作校准 |
| A/C作为中继的物理验证、D/E板及五板实验 | 未完成，不由本次结果外推 |
| 定位/SDP移动闭环、原六节点巡逻 | 未执行，不称原论文完整复现 |

