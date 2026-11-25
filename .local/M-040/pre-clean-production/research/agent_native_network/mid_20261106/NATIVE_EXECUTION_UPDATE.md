# AB/ABC原生计划与分析入口

2026-11-06，D-015。本页补充guide-1.0.1和ABC说明，优先采用E2检查点3的单套串口句柄actions，**不另开publish.py争用A端口**。E2固定文件hash已由D核对：FREEZE `65cedabf19e2b63547b3ff16ebd17ce1a8e91693b8ff7486857d5aea0cf4a166`；native.py `acb92c631734cbf38df120822bb4df0c3154c9e5e0f65f7af5bd39db4d922530`；[完整交接](../../../tests/mid_baseline/NATIVE_AB_HANDOFF.md) `ad515f18b6d3c1462cb742063f5436b2f5ada8bf79c5bf40e88f73f1c89ad108`。package-01、H显示和接口不变。

H在对应包/场景经C无阻断且身份/备份满足后执行。先保存刷后本MID包的完整info command_result：实际MAC/build/非零boot正确，idle且radio/stopping/locked_until_reset均false。C板字母?允许。`$infoA/$infoB/$infoC`为H保存的完整JSON文件，`$runId/$planOut`为H获分配的新run及新输出；在仓库根目录使用已有Python。以下命令D只静态核对，未运行：

```powershell
& $midPython -B tools/mid_baseline/validation/native.py materialize --info-a $infoA --info-b $infoB --run-id $runId --output $planOut
```

ABC则在同命令增加`--info-c $infoC --case $caseName`，case为AC、BC或AC_controlled_two_hop。入口自动核正式资产并按实际A boot编码；禁止投入E1离线boot1/seq1二进制。输出必须在H-005或E2-016的新任务输出目录，本页不调用到D输出范围。

| 顺序 | 每方向业务包 | run上限 | 配置seq |
|---|---:|---:|---|
| AB | 5 | 24s | 1–3 |
| AC | 2 | 15s | 101–103 |
| BC | 2 | 15s | 201–203 |
| AC_controlled_two_hop | 3 | 20s | 301–303 |

每case独立run/context，计入原RF最多6次/360秒总量，余量不足不追加。H按物化actions用同一套绑定句柄发送并采集：start；A在0/1/2秒三次配置；等全部参与者config_applied及有效route_selected（5秒不到则退出）；base stats；逐方向16byte编号payload、间隔500ms；stats/stop/final stats。每命令匹配nonce与ok；finally-stop，两秒内核radio=false/stopping=false/locked=false。无自动复位、重发或失败重试；板重启则重新info和物化，不沿用旧计划。

H保留原native事件和hardware_serial外层来源、实际日志窗口、全部参与节点coverage、base/final stats及停止状态。不要补造run_id/ACK/接收。事后审计的真实CLI为：

```powershell
& $midPython -B tools/mid_baseline/validation/native.py audit --plan $planOut --log $rawLog --context $contextFile --output $analysisOut
```

多份原日志可重复`--log`。context须有H任务/run/包hash、所有输入绝对路径hash、全部参与者coverage、capture_complete/hardware_measured和真实host_monotonic_controlled_window时长。缺失完整硬件context/身份/计数或停止条件时，PDR/goodput保持null；无ACK则RTT未知，RF重传/空口时长也未知。三端同origin/boot/seq/dst的源TX、中继rx_relay及指向终点的tx_submit、目的rx_local齐全才可报受控转发；逻辑禁边不证明真实RF断连，日志无TTL字段也不证明实测TTL变化。

E2的fake SDK/RTOS主机验证不等于RF。本页尚未消费H实测结果；C对应就绪结论仍须核具体版本，文档不替代放行。源MID保持目的未确认，OLED像素/PRG仍按H实际观察单列。
