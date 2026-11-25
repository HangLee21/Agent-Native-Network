# D-017 清理状态提示交接

2026-11-07，按M的cleanup_unconfirmed提示修正接手。D只改control页面及本卡，不访问8766、不调用recover或设备适配器，不重启服务。E2/H可先恢复现有服务，不必等页面检查。

页面已区分清理未确认、实验保留、其他进程占用、运行中、仅预览模式、尚未预览、计划过期及已提交。清理未确认时，单独显示涉及板号、失败阶段、下一步和服务错误；不会盖成“H实验优先”。此状态允许只读预览，但发送仍禁用，stop不再误当仍在运行的worker可供重试。

兼容当前服务：GET status只有active_run_id时，在用户打开/点击刷新时最多再GET该run一次，消费state/result/stop_confirmed/expected_chain/participants/error。没有新增轮询或恢复POST。仅存在于计划/实际参与列表且stop缺少确认的板会列入，不把四个已确认停止的板也报故障。当前已保存故障快照的A板、info-f8未关联回复，已离线核到界面显示。

结构化状态优先消费：status.active_run或blocking_run、status.cleanup或run.cleanup（兼容diagnostics）；其中affected_nodes/failed_nodes、failure_stage/failed_stage/stage、next_action/next_step、message优先原样使用；缺项再从实际run推导。reason/state=cleanup_unconfirmed显示清理未确认；console_recovering显示正在恢复。板号可为A–E或已绑定MAC。没有板号证据时明确写“尚未提供”，不猜所有板故障。若E2最终字段不同，按生产者实际合同再适配，不要求E2为页面重写恢复逻辑。

计划过期同时消费结构化expires_at（epoch秒/毫秒或ISO）或expires_in_seconds/ttl_seconds；旧服务按已核600秒租期提示，服务仍最终校验。收到stale_plan/unknown_plan错误会保留错误码并要求重新预览；正常新计划清除旧提示。已提交计划单独要求新预览，不自动补发。刷新确认清理锁已释放后清除旧清理阻断并要求重新预览。

验证：JS语法通过。`simulation/outputs/D-017/20261107-05-recorded-status/`有25项实际Chrome状态/按钮检查、截图和manifest，包含E2 06-recovery-before已保存JSON快照；HTTP/fetch为隔离夹具，不导入E2/H、不开串口，也不算恢复/设备验收。临时服务与Chrome命令均已退出。恢复正确性仍以E2/H的新证据为准。
