# 8766已准备的保留状态迁移

目标run：8fa45eb1b05e9c6e25c9ae0b。旧PID24020没有热恢复/状态导出入口，不能通过正常API给它添加recover，也不能声称完整导出了全部内存预览。E2未用进程注入或直接改旧active。

可审查产物：simulation/outputs/E2-018/20261107-11-migration-bundle/，保存5条落盘执行历史、5个已消费plan ID；当前失败完整GET快照原字节保留，C→E/hops2/count1及实际预期链C-A-E保留。旧失败的完整内存NetworkUpdate未在H开始写plan前保存，明确标original_plan_available=false，不补造表；全部已消费计划只能返回原run，不可重新发送。旧版未落盘、未执行的临时预览无法导出，迁移后必须重新预览，不能假称零状态损失。

执行方案：先只读对照当前8766仍为同一finished cleanup失败、H锁空闲，并验证H提供的新鲜停止receipt；确认新旧source/result/hash一致。将迁移包state复制到.local/mid/E2-018/service-8766/state.json（目标须不存在，不覆盖已有状态），留migration-required标记防止以后空状态启动丢失保护。然后仅结束已确认没有设备worker的旧HTTP服务，使用原SDK Python在8766启动新版。新服务先恢复原active=cleanup_unconfirmed，不自动清锁。最后显式POST该run的/recover {}，消费H固定路径receipt；只有run ID/源hash/5分钟时效/实际A MAC boot build 460800 idle queue0/全部参与板stop/关闭均满足，且没有旧worker或新active竞态，才记独立recovery_history并将原run留failed、释放该active。不发send，不改原结果或H文件。

H实际接口为recovery_receipt.py生成的mid.console.cleanup_recovery.v1；新版E2 recovery.py只读固定.local/mid/H-007/recoveries/<rid>.json，在H的进程锁内验证。GET /api/status区分cleanup_unconfirmed、console_recovering和console_run_active；/recovery/为显式核对入口。新运行/恢复/停止/plan状态均原子保存，之后重启不会丢保护或重新激活旧plan。

验证：07主机9项、08接H凭据10项；10原有服务回归34项均通过。09在隔离8767预览候选实际导入失败快照，确认状态为cleanup_unconfirmed、选择保留、旧plan返回原失败且无重发，恢复页GET200；候选已关闭，未改8766。无额外设备/RF测试。
