# E2/H cleanup恢复接口（2026-11-07）

当前故障run=8fa45eb1b05e9c6e25c9ae0b，原运行目录H-007/20261107-111428-console-8fa45eb1b05e9c6e25c9ae0b；E2已保存06-recovery-before完整GET快照。原run在info-A超时，未进入start/config/send，A stop未知、其他四板stop真、ports_closed真。不能仅凭硬件status USB/缓存info清锁。

E2提供POST /api/runs/<id>/recover {}，只对active指定run且worker已结束有效，运行/恢复互斥，重复recover幂等，新run隔离。失败记录/result/error保留；恢复证明独立追加。服务持久化运行并支持--restore-run导入已保存的故障快照，重启不能丢弃失败保护或重发旧计划。GET status reason区分cleanup_unconfirmed、console_recovering、console_run_active。

H生产者接口拟按 `recover(record, output, stop_event, on_event=None, timeout=30)->dict` 接入；record是服务保存的不可变public run，含run_id、output_directory、participants、result，HTTP不接收文件名或证明内容。output为H-007下唯一recovery目录。H在自己的HardwareLease内确认无旧worker/实验占用，给出目标run_id及独立证据。

H返回 `{run_id:<服务run ID>, safe_to_release:true|false, kind:'confirmed_stopped'|'prestart_no_side_effects', all_ports_closed:true, ...证据路径/hash...}`。confirmed_stopped必须所有participants的stop_confirmed={MAC:true}；prestart_no_side_effects必须effects_started=false且proof_complete=true（核原始host_enqueue/host_wire_chunk/host_tx，无start/config/send尝试，未遗漏部分写入；只允许info/stats/stop，端口关闭）。不能凭packets=[]或actual_infos={}单独证明prestart。

H将来execute结果也可附同格式 `cleanup_proof`，符合上述严格条件时E2自动释放该失败运行的active，仍以failed保留错误；缺证明继续cleanup_unconfirmed，不默认放行。H实际交付签名若不同，E2只做薄适配。E2不写H目录、不开串口、不刷写或重放send。H若已独立实读停止，也可由recover按原始路径消费其持久证据，不能让客户端提交自称已停。

本聊天跨窗口发送此前被自动审批以缺少直接人类授权拒绝；本次未绕过，按AGENTS第12条保存接口和任务卡。H/M可直接消费该文件，不把通知权限当作本地实现的阻塞。
