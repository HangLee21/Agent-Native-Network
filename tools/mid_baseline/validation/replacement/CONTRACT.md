# M-019固定表与重规划配对数据合同 v1

2026-11-07，E2在查看新实测结果前固定。物理操作仅H；沿package-03，不重刷/重验旧包，不新增ACK。端点A/B，C/D在役、E备用；触发退出者必须在触发前10秒实际承载源—中继—目的身份链，否则记机制条件未满足，不从结果中删样本。

## 固定计划

RUN_ORDER.json为5对10场，pair01 fixed→replan，02 replan→fixed，03 fixed→replan，04 replan→fixed，05 fixed→replan，不能看结果改序。首对直接算正式样本；若修改机制/配置，旧首对标pilot、保留且重新声明设计版本，不静默替换。两臂每场60秒，A→B/B→A各2包/秒，slot=0..119，时刻slot*0.5秒，各32byte，240条计划业务/场，2400总计划。建议退休事件目标20秒；实际生效时刻另外记录，不能以计划20秒冒充生效。

载荷编码：ASCII RPL1（4byte）+pair_id无符号小端u16+direction单byte(0=A→B,1=B→A)+保留0单byte+slot无符号小端u32+固定0..19字节，总32byte；同pair同direction同slot两臂完全相同，不含arm。native源seq与boot另保留，不能拿payload slot替代wire seq。

所有端点发送由独立调度时钟驱动。现场求解、配置门控/串口等待或退休操作期间不能暂停源计划或清空发送队列。每个slot在原计划时刻写planned事件；实际dispatch若晚/未发生仍记dispatch/undispatched及原因，不能补发成按时流量。源命令nonce固定为pNN-arm-direction-slot，每条同nonce回执，保存源tx_queued/tx_submit与完整origin/origin_boot/seq/dst。拒绝、未调度、接纳未提交、提交未到达分别保留。串口写可能占资源，延误照实记，不能从曲线删掉。

## 相同干预与图条件

两臂相同硬件/MAC/build、模型来源/参数、负载、初始表与种子（若用）、退出/启用备用动作及目标时刻。H恢复每场初始状态并记录新实际A boot；不复用假boot或旧未关闭radio。两臂均软件stop在役中继、start E；与拔电不同。fixed保留初始表不发布替代表；replan在成员变化后用当时模型现场运行原SOCP，发新表至存活成员和E，不等退出节点，不预填替代下一跳。新表schema与CLI由E1给，E2不改算法。

若桌面直达/分流令退出无服务变化，报告原事实。仅在两臂共同声明的受控逻辑图上做替换机制解释（例如初始A-C-D-B，替换后A-E-D-B只是可检验的机制意图，最终须实际求解得到，不写死下一跳）。模型逻辑边不能称自然掉线、移动恢复或RF屏蔽。

## 采集JSONL

每条envelope含run_id/pair_id/arm、host_monotonic_ns、kind和source。设备事件kind=device_rx,event保留完整mid.serial.v1原对象；host_tx.command保留真实JSON。planned含direction/slot/planned_ns/payload_hex；dispatch含direction/slot/nonce、实际host时刻；未执行为undispatched（保留原因）。设备本地monotonic_ms/boot原值不转换成另一节点的时钟。

外部事件kind=annotation，name至少：run_start、trigger_requested、retire_requested、retire_effective、spare_start_requested、spare_active、solve_start、solve_end、config_publish_start、config_applied、spare_first_relay、run_end。retire_effective仅以该设备stop/stats实际radio=false且stopping=false的回执观察时间支撑；记录raw来源，不以发stop时间代替。spare_active同理。config_applied和E首次中继须引用真实原事件/消息身份，不根据意图补造。注解可后处理生成，但必须附raw文件/行号与original_host_ns，原日志不改。

run_context.json（不可变）含schema=mid.replacement.context.v1、run_id、pair_id(1..5)、arm、design_version、package/build/MAC/boot、schedule_t0_ns、duration_s=60、planned_interval_ns=500000000、measurement_clock=host_monotonic、evidence_kind=hardware_measured、source_logs(path/sha256)、endpoint_coverage(A/B bool及缺失理由)、stop/port状态、初始模型/table指纹、干预请求/生效时刻与现场solve输入/输出来源。同pair两臂initial_condition_id必须一致；不一致的pair结果另标不匹配而非丢弃。覆盖中断、溢出、端点重启不得输出确定PDR；保留观察数与unknown原因。

分析具体键：endpoints={"A":实际MAC,"B":实际MAC}、boots={实际MAC:本次整数boot}、build_id、endpoint_coverage={实际MAC:bool}、status=capture_complete或capture_incomplete、stop_confirmed={实际MAC:bool}、log_sha256={输入绝对路径:原字节SHA256}。硬件status/端点stop不完整时仅保留观察，不给确定时窗指标。planned/dispatch类的方向用direction_id整数0/1，避免与外层direction=device_rx/host_tx混淆。

## 输出给D与统计

run_packets.json：每direction/slot一行，planned/dispatch/accepted/submitted/delivered/content_match分列、wire identity、原始行号、actual host capture times；空窗/漏发不删。源queued仅与本机同nonce成功send回执关联，不能用最邻近跨板时刻猜身份；无法关联标ambiguous。源数据与目的通过wire identity关联，payload验证对齐slot。

run_seconds.json：两方向各60个[second,second+1)窗，planned_count、dispatch_count、source_accepted、source_submitted、unique_delivered、unique_payload_bits、goodput_bps、coverage_status，零值保留，缺日志用null。按目的首次有效接收的host采集时刻归窗；晚于60秒的接收另列late_after_window，不藏进最后一窗。该轴含串口/采集延迟，不是跨板同步时钟，更不是单向RF延迟。

事前基线=实际retire_effective前最近10个完整1秒窗平均有效吞吐。阈值=80%基线；恢复为干预后连续3个完整窗各≥阈值，恢复时刻取第三窗末。若基线0/不足10窗则不可评价；若干预前3窗已达阈值、干预后全部窗未低于阈值，标no_interruption、恢复0，不能宣称重规划加速。未满足恢复标right_censored并给观察终点；覆盖缺失为unknown，不当0。另报按计划slot最长连续未交付包数及其计划时长；这不是物理链路断连时长。

pair_results.json：fixed/replan每方向的逐秒曲线、有效交付、恢复状态/时间、最长缺失、后干预交付面积差（replan-fixed）与初始条件匹配状态。展示每一对，不只均值；汇总给有效配对数、各差值、median/IQR/min/max，不对5对使用精细显著性或把删失恢复时间当已观测均值。控制器计算/串口开销与链路提交次数分开，PHY airtime/RF重试仍未知。

分析器额外要求context.shared_inputs含model_sha256、initial_table_sha256（共同逻辑表/NetworkUpdate，不含两臂各自boot/配置seq的wire头）、scenario_sha256、workload_id。缺指纹的配对标unknown而不是匹配，实际不同标mismatch，不删失败。单run入口analysis.py --context ... --log ... --output simulation/outputs/E2-017/<新run>/analysis.json；配对入口pair_runs.py --run <分析1> --run <分析2> ... --output <E2新文件>。均不操作串口。原日志必须在分析前带run manifest，分析输出写新目录，不覆盖H原文件。

串口cmd=invalid/nonce=null不能配到某个send时，保留对应host计划/dispatch和未关联回复；不是RF失败，不给有效链路服务率。未形成完整窗口的link capture valid=false，观察1条RX可以作为观察计数，但均值/方差和容量字段null，不能混入E1模型。

UART候选接入：H按自己已授权流程验证B，不由E2加刷写门槛。context可用builds={MAC:实际build_id}、uart_bauds={MAC:实际应用速率}记录单板pilot混版/混速率；不能把ROM/bootloader/刷写baud当应用baud。若builds存在，按节点核对而不强行把其他旧板写成新build。uart_rx_overflow或非零uart_fifo_overflows/uart_ring_overflows使端点数据完整性未知，不能算作RF损失。原始计数、实际TX字节、写入返回长度/分隔符及迟到nonce仍需H保存。正式配对两臂须相同软件/速率映射；shared_inputs应另加software_configuration_id记录该映射，pilot不能混入5对正式数据。新候选发布/构建不等于实板通过，也不宣称修复A的ROM身份问题。

H预算：10场×60秒计600秒；额外一次定向链路采集最多20方向×10秒/方向、每向≤100帧，按M最新决定32byte/10pps 100帧/方向并记实际窗口（若已采2pps另存，不混表）；一个有限故障pilot（有变更须标pilot）不超总RF20分钟。链路窗口给实际offered/accepted/submitted/unique_rx/bits_per_s和每秒值；低负载全达仅为该负载下服务观察，不作最大容量或标定QoS。H设备/准备总2小时，不追加失败补样本。

M单位修正：正式两臂每向2pps×32byte=512bit/s需求保持不变，链路观测10pps注入2560bit/s，只是该负载下的有效载荷服务观察/容量下界。E1用真实bps均值/样本方差，标明每个窗口实际注入；不可行如实报，不默改需求、虚增容量或补未声明headroom。原始每秒窗口可再聚合2秒供建模，不能混用两种窗口方差。
