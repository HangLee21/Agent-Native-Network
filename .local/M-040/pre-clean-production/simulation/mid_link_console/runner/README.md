# 可编辑链路执行器：E2/D接入点

```python
from simulation.mid_link_console.runner.pair import run_pair
index = run_pair(settings, output_dir, cancel=None, progress=None)
```

`settings`直接采用H的`custom.get_defaults/normalize_settings`结构，不能由前端另造范围或单位。标准库JSON对象传入，output_dir必须全新；先校验再创建输出。首次实际MID求解需现有`.local/mid/E1-016/venv/Scripts/python.exe`及其CVXPY环境，进程CPU线程2。由E2在独立子进程/工作线程调用，不阻塞8767请求/页面；后端一次只允许一组，设备/串口没有参与。

子进程入口：

```powershell
& '.local/mid/E1-016/venv/Scripts/python.exe' simulation/mid_link_console/runner/pair.py --settings <服务本次保存的设置快照.json> --output simulation/outputs/E2-020/<唯一run> --cancel-file <本run的服务端取消标志>
```

成功退出0；失败/取消退出2。`cancel`也可threading.Event或无参数callable；CLI仅在E2指定标志存在时取消，不自行轮询服务/设备。每个事件调度检查取消，正在求解需等当前有界solve返回，必要时由E2进程超时管理。progress回调给arm/t_s/duration_s，只是实际执行进度，不模拟动画代替结果。服务自行验证请求/Host/Origin和新run路径，不向用户开放任意文件参数。E2服务监听8767和启动器、D界面/浏览器验收均非本库实现范围。

输出：settings.json（完整归一化冻结草稿）、scenario.json、INDEX.json、RUN_MANIFEST.json；fixed/adaptive各有events.jsonl/context.json/planner_inputs.json/summary.json。每次运行根run_id是目录名；raw事件run_id含settings hash/seed/arm。INDEX.status为running/complete/failed/cancelled，取消可能只有第一臂部分数据，不能当完整配对。图/指标必须读对应run快照，编辑草稿或恢复默认不改旧结果。归一化默认/恢复本身不调用run_pair、不产生run。

复用M021原Engine/MID求解与固定表、0.5秒下一跳保持、队列/去重/TTL/有限控制安装语义，未修改旧引擎。新类只扩展设置环境、排程/传播、不可行初表和取消。全断网初始求解失败用空表+initial_no_table和逐包no-route丢弃返回完整0交付结果，不assert崩溃。后续不可行仍保留上一表。

每边delay_ms作用数据和控制传播，序列化额外；在开始该边服务时冻结本次传播值，已飞行帧不因草稿/后续时延变化被追溯拉长。tx_attempt/control_tx和arrival事件均给transit_id、service_start_s、serialization_s、propagation_delay_s、scheduled_arrival_s，实际到达满足arrival-start=serialization+propagation。等待队列另计，不能将传播误作总端到端时延。

途中失败不仅看收尾：检查整段服务开始至到达间的所有边/离线干预边界；任何零服务/离线则in_flight_failure，即使到达前恢复也不能复活帧。连续非零PDR用同一draw与途中最低概率判断，不能额外抽一次概率。源持续生成和两臂初始/设置/种子/外生键一致。跨不同草稿同seed也用稳定editable-five-v1随机命名空间，避免改时延同时悄悄换初始路由抽样。

规划器仍优化capacity×PDR的稳健速率裕量，不优化传播延时。因此delay-only变化影响事件到达但不制造新的路径改进；观察日志仍记录时延，路由变化检测只看原模型速率/PDR/节点输入。限制沿原模型：独立边服务器，不模拟RF争用/半双工；传感为延迟.5秒的理想中央带外视图；不是实板或容量标定。

默认60模拟秒，每向2pps32B，排空最多20秒；duration实际范围以H catalog为准。summary.generated/source_planned/到达before_end/late分开。传播最长2秒/边时，未决包不能在终止时补造交付。事件t_s均模拟时间，solve_end的真实壁钟与模拟.2秒计算延迟分开，缓存说明沿原引擎。

本次实际运行示例：`simulation/outputs/E1-020/20261107-01-settings-check/`下default、single-delay、two-edits，各有独立真实run和固定/重规划两臂。default两臂234/240；仅D→B在20..40秒从10ms改300ms仍234/240，但两臂各37个可匹配的D→B数据到达均后移0.29秒。two-edits另加AC/CA断开，固定174/240、重规划226/240。这些是软件结果，非预录曲线/RF。PROOF.json还核两臂同设置/初表/源计划、断开后在到达前恢复仍杀死在飞帧、全断网0交付、取消保留partial状态。前三例后只将无效设置校验移到创建目录前，事件算法未变；各run manifest保留其当时runner hash。

任务卡E1-020含交接路径。自动审批拒绝了向E2发送接口消息后采用授权卡/文件交接，未换工具绕过。E2/D可立即导入并在正常8767入口运行新默认/自定义两组，不需重审M021/硬件。E1没有冒称浏览器或HTTP验收完成。
