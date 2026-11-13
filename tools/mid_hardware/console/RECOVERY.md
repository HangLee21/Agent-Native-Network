# cleanup_unconfirmed恢复交接

服务保持旧run失败，不能因端口关闭便断言设备已停止。用户业务不自动重发，旧计划/原始记录保留。

H实际读到A的MAC、当前boot、460800、info/stop/stats和queue0，且句柄关闭后，可运行recovery_receipt.py。它拒绝不完整/历史超过5分钟/非实际A/非idle的证据；将原run其他四板stop真和新A实核组合为mid.console.cleanup_recovery.v1。原始结果不改写，补充来源带路径/hash，automatic_business_resend=false。

E2负责让现有服务在消费上述实际证据后只释放该run的残留active，并单独记录cleanup_recovered。不得把原业务改成成功或自动再run。H不写E2服务文件，不通过进程注入改状态。现有服务没有热恢复入口时由E2给保留运行状态/用户选择的迁移方案，交M决定；不得直接重启丢历史。

2026-11-07的run8fa45eb1b05e9c6e25c9ae0b：03至06的无回复失败保留。用户再次重连后，07在旧COM10读到实际B；08按全部实际MAC重新映射，A现为COM7，B为COM10，五板均已实核停止并关闭。09派生当前A证明后生成了固定路径正向receipt；verified_at为2026-11-07T03:29:31.602857+00:00，消费仍须验证300秒时效，不能把历史证明当实时状态。M已指定E2唯一负责服务恢复，H不并行重启或清active，也不重发用户业务。
