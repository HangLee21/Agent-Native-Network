# 分析侧归一化事件提案

此合同供E1/H冻结后对齐，尚不是其真实串口schema。分析器不会自动把原ANN或未来MID原日志当成本格式；适配器需保存原文件hash、原行号、原始事件，禁止生成“目的端收到”的替代日志。现有归一化输入只用于synthetic工具验证。

每行schema=mid.validation.event.v1，run_id、event、node_id、boot_id、event_seq（非负整数）、t_us（本机单调钟）与evidence_kind。event_seq为本机本boot唯一日志号，不是RF重传计数。H外层可为direction=device_rx/event={...}/evidence_kind=hardware_serial；host_tx不当收到。

业务事件补充flow_id、origin_id、origin_boot_id、seq、destination_id、payload_bytes。generated须在源本boot；endpoint_rx只在实际目的节点且unique_receive=true（严格bool）计交付。tx_queued/link_callback/timeout/control_tx_submit分别保留，MAC回调success是bool/未知，不当端点ACK。control_tx_submit.frame_bytes是应用提交长度，不是PHY airtime；控制原源/控制序号/中继及route_epoch/route_version/selected_next_hop需保留供冻结后执行一致性验证，当前分析器未判定其正确性。

display_snapshot含based_on_event_seq与display_state，引用同node/boot的一条实际事件。允许CMD_OK←command_accepted，TX_QUEUED←tx_queued，LINK_OK/LINK_FAILED/LINK_UNKNOWN←link_callback，LOCAL_RX←唯一目的endpoint_rx，CFG_APPLIED←control_applied，TIMEOUT/FAILED←对应事件。ANN_CONFIRMED只允许mode=ann的ann_confirmed。MID源端DELIVERED/SUCCESS没有baseline证据，不接受；此处状态是验证标签，最终屏幕中文/英文由H冻结映射。

配置schema=mid.validation.config.v1，streams列flow_id/source_id/destination_id/expected_generated与两端日志完整性。measurement_duration_us须配receiver_local_window或host_monotonic_controlled_window，不推算时长。示例默认覆盖false、窗口null。输出schema见RESULT_SCHEMA.json；无覆盖/身份冲突/计数不符则PDR/goodput为null，RTT及PHY指标未观察则null。JSON重复键/NaN拒绝。

硬件声明须同run的不可变H-005 context：task_id=H-005,status=capture_complete,evidence_kind=hardware_measured，input_freezes与分析配置一致（含E1/H实际hash）；log_sha256将全部输入日志resolve后的绝对路径映射到原字节SHA256；coverage按实际MAC记录完整性。缺失/冲突来源或synthetic标签拒绝。H实际stop/overflow/boots/counters如何支撑coverage须在冻结后审查，现阶段这只是来源门控，不作物理认证。context/raw/config一经计算不能再改写。

`analyze_files(config_path, log_paths, context_path=None)`只读文件，返回dict；无串口/固件/外部依赖。CLI示例：`python -B tools/mid_baseline/validation/analyze.py --config CFG --log LOG --output simulation/outputs/E2-016/<已带RUN_MANIFEST的新run>/analysis.json`，拒绝覆盖或写其他输出根。H若需接入使用函数写自身授权新输出，先共同冻结；目前未接入H工具。
