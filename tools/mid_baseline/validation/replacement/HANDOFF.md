# E2-017可消费交付

## 最终入口：4个完整配对，1个不完整配对保留

`simulation/outputs/E2-017/20261107-17-final-results/DATASET.json`为当前入口，REPORT.md/summary.json/pairs.json与initial-preconditions.json同目录。全部10场原始日志各分析一次，不重跑首对；第1、2、3、5对完整、每对fixed80/240对replan230/240，第4对fixed不完整（64完整写入/64接纳/62目的观察），配对差值null，保留未补跑。第3对replan有1条源明确拒绝，不能称所有源全接纳。

名义2400、观察dispatch2224、源接纳2223、各场唯一接收之和1532；不是全实验确定PDR。4完整对恢复5.937–5.954秒、fixed右删失；每方向事后面积差19200bit。D须读取metrics_valid和未知状态，fault04未观察时隙不得显示成RF零吞吐/物理丢失。后续stop和boot变化另列fault-evidence，不补回原业务覆盖。原context软件指纹用有原始info来源的补充映射，原字节不改。H设备采集已结束，E2无监控/设备进程或新实验；C/M按本地文件独立接手。

以下首对/中途交接保留历史，最终以17-final-results为准。

## 最新：正式首对已独立分析

入口：`simulation/outputs/E2-017/20261107-09-pair01-audit/DATASET.json`，报告同目录REPORT.md。D直接读fixed.paired.json/replan.paired.json的packets/seconds/annotations/directions，以及pairs.json配对差值，不重新解析/猜造RF数据。08-pair01内未补字段的原分析各只运行一次；09文件加有来源的software_configuration_id补充，H原始context/manifest不改。后续五对汇总复用这些首对文件。

每臂240计划/dispatch/成功接纳/源TX提交；目的唯一收到固定80、重规划230。双向各40/120对115/120，重规划恢复5.937秒、固定右删失39.953秒，连续三1秒窗判据不改。实际原始日志核干预前ACDB/BDCA、替换后AEDB/BDEA；现场solve1.953秒的8个计划slot继续dispatch+接纳，实际各晚63ms。软件映射由原始info实证，缺项和补证明确列入pairs，不猜填。只有1对，桌面受控逻辑图，不作自然断链/覆盖/容量/QoS结论。

其余4对待H交付，不轮询。以下为此前准备记录，其中“当前未取得”仅代表首对到达之前。

## H/E1：采集与求解接入

- CONTRACT.md、RUN_ORDER.json已固定5对顺序及同负载口径，首对fixed→replan，随后交替；10场60秒、双向各120个slot/32byte，2400条计划业务，触发目标20秒。读合同详细字段，不等待E2重发审批。
- E1现场worker已由E1交付于tools/mid_baseline/planner/replacement/online.py。本窗口不改该worker或求解结果。H独立Popen记录solve起止，源调度继续；退休/备用和发新表按原授权执行，不等待退出节点。源send拒绝或现场solve失败均记录并继续计划，不能暂停/补包。
- M单位决定已纳入：链路观测10pps/32B/10秒100帧；正式每向2pps/512 bit/s。每秒服务观察可聚合为5×2秒给E1，但均值/样本方差必须同单位同窗口，不把低负载全达当容量，不可行不暗改需求。
- 当前H报告的A失联、BC缺nonce命令/串口pilot是具体设备/接纳障碍，不是RF损失。初始partial原文件保留，valid=false，不生成有效服务率；观察1条目的RX不能替代完整窗口。UART修复候选/实际验证由E1/H处理，E2不重刷或新增run。

## D：马上可用的旧五板真实回放数据

`simulation/outputs/E2-017/20261107-02-existing-five-replay/replay.json`为已有12场景/120消息的直接绘图数据，不是新替换实验。schema=mid.replay.dataset.v1，cases[].messages含identity、源/目的、payload、实际事件，cases[].events按同一host采集时刻排列，事件保留next_hop、相对秒、原始host_ns、设备本地ms和源文件行号。nodes坐标明确是示意；不同设备本地时钟不可相减，host时刻含UART/轮询延迟，不当物理单向时间。120消息全部来自前阶段E2已核结果，无伪造丢失/链路或新实验值。

后续替换数据由analysis.py输出同一run的packets/seconds/annotations/directions，D可按CONTRACT直接接动态图、双方向曲线与事件标记；packet计划未执行/拒绝/未知均保留，空窗0与unknown null区分。pair_runs.py合并两臂、按pair显示差值和离散度，删失恢复时间不作已观测均值。

## 可运行的分析

```powershell
python -B tools/mid_baseline/validation/replacement/analysis.py --context <H不可变run_context.json> --log <H原始capture.jsonl> --output simulation/outputs/E2-017/<新run>/analysis.json
python -B tools/mid_baseline/validation/replacement/pair_runs.py --run <fixed分析> --run <replan分析> --output simulation/outputs/E2-017/<新run>/pairs.json
```

输入schema/配对共享指纹/事件口径见CONTRACT。两程序仅离线读文件，不操作设备/运行求解/画图；原数据不改。H已开始采集时不为此合同停业务：原日志可先完整保留，适配已有字段时须保留原文件行号，不能补造计划、接纳或RX。计划参数或机制变化标新design_version/pilot，别静默混进正式五对。

当前7项synthetic检查通过：固定载荷、空窗/右删失、3窗恢复/无中断、拒绝仍有计划、未知覆盖与重复、配对差值/初态错配、无nonce未关联回复不当RF损失。未运行新设备或重跑整包。真实有效链路窗口及10场配对尚未取得，不输出假实测曲线。
