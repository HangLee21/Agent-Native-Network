# M-021 软件仿真

正式入口：`simulation/outputs/E1-019/20261107-04-combined/BATCH_INDEX.json`，引用02首对和03其余28场，共30场、15配对、7200源计划。01是保留的检查版本，不计正式样本。每场events.jsonl/context.json/planner_inputs.json/summary.json可直接给E2/D读取。数据均software_simulation，不是RF实测，没有运行M019/020或设备。

字段沿E2 CONTRACT：t_s模拟秒，run_id/pair_id/scenario_id/seed/arm；packet_id/src/dst/origin/sim_boot/seq/payload_bytes/payload_tag；generate/tx_attempt/rx/relay/destination_rx/drop，node/next_hop/route_version与信道draw/key；observed_state/detection/solve/config_publish/control_tx/rx/install。只有destination_rx且node==dst才是交付。summary.destination_unique包含2秒排空，destination_unique_before60取[0,60)，晚到不塞第59秒。

原SOCP直接调用planner.py。mean=capacity_payload_bps*pdr，variance=cap²p(1-p)为独立Bernoulli服务近似；缺边/零服务用声明的逻辑惩罚(10*maxcap)²，非物理测量的方差。若原解仍有禁边则拒绝，不后改概率。原bridge量化u16，每节点每流500ms抽一次下一跳并保持。原概率表可能回环，64项去重会丢回环包；因此初始PDR1不保证所有业务到达，事前丢包不能隐去。

时序：t0前两臂装同一初表（bootstrap成本未计）；每1秒观察滞后.5秒的全状态快照，检测同步，模拟求解.2秒，实际主机壁钟/缓存命中/原计算壁钟另列。中央传感是理想带外、无丢失，不模拟遥测成本；未调用H可达性/路径见证给策略，不传未来。不可行保持上一表。完全相同输入缓存跨种子复用，但不改变模拟.2秒，缓存查询不冒称现场求解耗时。

控制仅在变化检测成功求解后发一次有限源/seq去重洪泛、TTL8，每有向边复制排队，control应用字节/容量+.05秒传播；不是周期刷新、ACK/提交。control_tx是应用级复制字节，不是真实MAC广播数/RF重传/PHY空口时间。安装由实际模拟接收触发，断边到达和离线节点不能安装；安装清当前选择到下一500ms tick。节点离线保留旧表，返回是暂停恢复而不是空表重启。

数据每向2pps、32B，TTL8、无ACK/重传，独立有向边FIFO32/服务器。服务按开始时容量，成功概率取开始/结束min，传播到达若断边/节点离线则丢；数据传播.01秒、头开销不计。未模拟共享无线竞争/干扰/半双工耦合，不能外推ESP-NOW实测性能。生成至60，排空至62，残留未决不补造交付。

信道hash(seed,scenario,millisecond,edge,packet_id)不含arm、不按调用顺序消耗RNG；路由抽样另hash(seed,scenario,node,500ms_epoch,flow)。同一时间/边/身份抽样一致，改变路径/尝试时刻后的键也随之改变，并不是强制所有不同路径共享同一个抽样。

复现命令（本批已执行，读取不必重跑，输出必须唯一新目录）：

```powershell
& '.local/mid/E1-016/venv/Scripts/python.exe' simulation/mid_link_study/engine/run.py --first-pair --output simulation/outputs/E1-019/<新首对>
& '.local/mid/E1-016/venv/Scripts/python.exe' simulation/mid_link_study/engine/run.py --skip-first-pair --output simulation/outputs/E1-019/<新余28场>
```

各格5种子×240=1200源计划，原始目的计数：渐弱fixed846/adaptive963，中继退出850/1116，分区恢复775/775。无优势/失败样本全部保留。这不是恢复时间或“差额全归旧路由”的结论；回环、安装等待、链路概率、分区须由E2结合H事后真值分解。combined/CHECKS检查15对相同源计划/初表、目的身份/payload一致、分区[20,40)无目的、C离线无安装。

跨聊天消息曾被自动审批拒绝，之后采用任务卡及上述文件交接，没有换工具绕过。首对及整批均已可消费，无须等新冻结或文档。
