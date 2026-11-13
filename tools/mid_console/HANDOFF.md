# E2-018交付

最新8766 cleanup恢复已完成：新PID22756/session72727，GET状态busy=false/run_available=true/active_run_id=null。run8fa45eb1b05e9c6e25c9ae0b仍failed，原错误/结果、C→A→E选择、已消费plan ID保留，recovery_history独立记录H正向receipt，未发送或重发业务。来源与迁移前后完整GET为simulation/outputs/E2-018/20261107-12-recovery-deployment/。落盘运行5条/已消费plan5个，旧版无导出接口的未执行预览不冒称保全，需重新预览。以后原子持久状态和精确run恢复，不靠重启清空锁。主卡最新段及MIGRATION_PLAN.md列明边界。

H已核重连后A/B端口对调并按MAC更新为A7/B10/C12/D9/E11，全体stop/queue0/闭口；不是凭COM认身份或确认持续硬件坏。恢复页/recovery/，H固定路径新鲜receipt经源hash/原失败绑定/真实A状态/全部stop证明验证，缺失继续保护。07/08恢复测试和10原34项回归通过，无新增RF，待C/M增量接收。

用户双击实板入口由H新增于tools/mid_hardware/console/打开实板控制台.cmd及launch_console.py；E2只读入口后补充README，未改H文件、未重复运行--check或开页面/服务。已有8766硬件服务直接打开，否则委托原server --hardware --port8766 --open；仍仅显式UI发送、实验锁不变。原START_CONSOLE.cmd默认预览保留。M-019第5对已消费，完整最终数据为simulation/outputs/E2-017/20261107-17-final-results/DATASET.json，不再将其标为待接入或重跑首对。

最新实板入口：http://127.0.0.1:8766/ ，H已用--hardware启动并保留session72482。H在M-019全体stop后释放保留，实际页面各发一次hops4/count3与MID/count3；E2只读新原始记录独立核6条同nonce源接纳、完整TX/中继RX+TX/目的rx_local与payload：A→B→C→D→E三条、B→D三条，全部目的收到。逐包身份/原行及UI字段映射见simulation/outputs/E2-018/20261107-05-hardware-intake/intake.json。所有表参与板最终stats的radio/stopping/locked_until_reset为false，H报告全部端口关闭。H两次完整执行上界总8.594秒，非PHY airtime；E2无新增RF。

页面操作由H实际CUA完成，E2未重跑浏览器/硬件；H证据simulation/outputs/H-007/20261107-02-browser-hardware-acceptance/。默认8765仍为预览，双击启动器也默认预览；实板实例用上方8766或START_CONSOLE.cmd --hardware --port <空闲端口>。自动结束排空已有新实板证据；手动中止、超时中断及服务退出时清理仍未做实板专测，不扩大本轮额度。模型仍为assumed-five-v1，不能称实测无线最优。任务保持review待C/M。

以下为硬件验收到达前的交付记录，其中“未验证”以本段最新更新为准。

可用入口：http://127.0.0.1:8765/ ，当前preview模式。双击本目录START_CONSOLE.cmd可重启；已有服务占用8765时直接打开页面或指定--port 8766。实板需H在M-019空闲后用--hardware启动，不靠页面自行解除实验保留。

生产者已接：D同源页面和/replay/、E1 PlanLibrary真实SOCP/恰好k跳/手工链、H status/execute/stop Event与H-007输出目录。完整字段见INTEGRATION.md。服务启动器优先使用现有SDK Python（pyserial），独立规划worker使用E1-016虚拟环境；不安装依赖、不碰固件。

最终34项服务检查全过：simulation/outputs/E2-018/20261107-03-table-readiness/checks.json。记录包含真实HTTP、E1实际规划与隔离的主机并发/清理夹具；RF执行0。实际JSON样例为同目录four-hop-response.json与mid-response.json。同plan并发8次只执行一次；其他plan忙碌拒绝；停止只设同一个Event；任何参与板停止/排空缺失都保留busy。H会启动network_update全部节点，因此E2门控所有node_set，不只预期链；请求源用作status的publisher，支持无A子集。

Chrome实际浏览器操作已验证页面→HTTP服务→E1规划：MID返回optimal、多候选权重和假设模型来源；切换恰好4跳返回A→B→C→D→E及not_used（未使用SOCP）。页面显示H实验busy、发送按钮禁用、没有实际路径/目的交付。浏览器画面由CUA工具实际捕获展示；未将D离线截图冒充这次在线操作。详见simulation/outputs/E2-018/20261107-04-handoff/BROWSER_CHECK.md。

未验证：H实板执行、实际逐包路径、物理stop/超时排空及服务关闭时实板清理。此轮没有调用H execute，无线包0，未解除M-019保留。H沿M-020额度在实验空闲时从控制台做两模式各≤3包、≤60秒验收；C只核增量与H结果。本卡交审不替代独立验收，不把预览optimal外推成链路性能或测量模型。

进程：最终预览服务session68322保留监听127.0.0.1:8765供用户打开；无设备worker、后台轮询、聊天轮询或额外实验。规划/检查进程均已退出。未做Git写操作，保留其他角色工作。跨聊天通知未重试此前自动审批拒绝；本地任务卡及本文件为交接入口。
