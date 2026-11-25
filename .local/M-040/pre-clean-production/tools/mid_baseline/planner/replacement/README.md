# M-019 在线求解入口

仅主机工具，复用原 planner.py、bridge.pack 和 package-03。E1不碰设备，不改SOCP约束/板端ACK/路由执行。H负责持续发包和软件stop，E2负责配对方案及统计。

解释器：`D:\Multi-Agent Network\.local\mid\E1-016\venv\Scripts\python.exe`。工作目录仓库根目录，所有输出路径必须新建。此目录内 online.py 支持三个命令：

```powershell
& '.local/mid/E1-016/venv/Scripts/python.exe' tools/mid_baseline/planner/replacement/online.py model --labels hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json --windows <H窗口.json> --output <新model.json>
& '.local/mid/E1-016/venv/Scripts/python.exe' tools/mid_baseline/planner/replacement/online.py scenario --labels hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json --graph controlled --output <新scenario.json>
& '.local/mid/E1-016/venv/Scripts/python.exe' tools/mid_baseline/planner/replacement/online.py solve --request <本次request.json> --output <新求解目录>
```

model输入为窗口数组，或`{"windows":[...]}`。每条窗口：

```json
{"src":"A","dst":"C","window_s":1,"payload_bytes":32,"scheduled":10,"accepted":10,"rx_unique":10,"valid":true,"raw_source":"H本run原始日志及窗口引用"}
```

src/dst可MAC或已绑定字母。窗口须同一方向、不重叠、同一注入负载，缺失/溢出窗口不能用valid=true掩盖；无效则明确失败，不静默删样本。按`rx_unique*payload_bytes*8/window_s`计算bits/s，逐边样本均值/方差，至少两窗。H主机时间轴统计目的端唯一有效载荷，窗口开关、排空和时间边界需H/E2保持一致；到达时间窗口可能收到上一窗已接纳的包，因此不逐窗强制rx<=accepted或截断突发，总量/覆盖另由H/E2按完整身份与捕获区间核。10pps×32byte的满达服务只给2.56kbps注入负载下的观测，非饱和容量；样本方差也不是已校准信道不确定度或独立性证据。两臂正式每向2pps/32byte，request中demand=512 bit/s，不能缩成旧无量纲.05。若不可行返回infeasible，不偷增容量/缩小需求。

scenario生成5对交替顺序，固定/重规划使用同一initial表、模型、负载和外部事件。端点AB，初始ABCD在线、C/D在役、E备用；触发后C退出，ABDE存活。controlled两臂共同声明初始A-C-D-B、替换后A-E-D-B逻辑图。原SOCP对非边使用mean0及明确记录的方差惩罚，不修改求解后概率；若输出越过禁边或不形成期望链就拒绝。链路模型取观测系数，仅逻辑非边另外声明。natural则不屏蔽成员内任何观测边；天然直达/不发生中断应如实报告，不把它当成功替换。选择图后同一批5对不因结果变更，不挑样。

现场request示例（路径换成真实路径/boot/seq）：

```json
{"scenario":"<scenario.json>","model":"<model.json>","phase":"after","members":["A","B","D","E"],"arm":"replan","demand":512,"qos":0.9,"publisher_boot":123,"seq":101,"nonce":"pair1-after"}
```

initial时phase=initial、members=[A,B,C,D]；两臂共用该初始求解产物。after必须在外部C stop实际生效/E start后，用现场当前成员和模型调用；不读/等已退出C。固定臂after禁止调用worker，保留初始表。source boot/seq由H当前info给定，不投演示boot。E启动绑定同一当前A publisher；其他源调度不重启，记录连续源seq。新配置只等待ABDE真实config_applied/route_selected，不能把worker成功等同全网已应用。

H将solve命令交`subprocess.Popen`，保留stdout/stderr和退出码。不得在业务线程`subprocess.run/wait`求解或等配置门控；发送调度按60秒、每向2pps独立进行（每场240计划），no_route/命令拒绝也记失败并继续下一计划，不暂停/清空/补包。worker将problem/solution/update/command写唯一新目录，完成后原子发布result.json，含solve_start/end_host_monotonic和UTC。H可以异步任务/进程完成通知消费它，再发送command.json；求解失败或超时也保留源业务及原表，记录场景失败，不自动循环求解。H设备串口仍只由H同一控制器拥有。

每对初态还原为ABCD/E备用；必须确认C/D在触发前有真实数据承载，否则不做中继替换解释。事件记录包括计划触发/实际C stop/E start、solve起止、配置提交和每个存活节点应用、首个E中继和端点接收。设备本地时钟保留原值，恢复曲线用单一H采集时间，不能相减跨板时钟。模型/解/期望链均不是RF证据。E2最终给配对执行与指标，原RF20分钟预算不由此扩大。
