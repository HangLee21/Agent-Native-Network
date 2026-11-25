# M-023 立即可接入：新指定跳数/时延对照

E2可按schema分派，**旧MID入口pair.py及旧结果均保留**：

```python
from simulation.mid_link_console.runner.routing_pair import run_pair
index = run_pair(settings, output_dir, cancel=None, progress=None)
```

settings由H`simulation.mid_link_console.settings.routing`产生，schema=`mid.routing.settings.v1`，src/dst/hops(None或1..4)/both_directions直接消费，不猜起终点、不强开反向。CLI参数仍`--settings --output --cancel-file`；相同既有E1-016 venv可执行，无新依赖/端口。output_dir全新，settings/scenario快照和INDEX/status/manifest布局沿旧；**两臂目录/arm为fixed、latency_aware，不是旧adaptive**。E2/view应按INDEX.runs路径读取，不把新策略再标MID。可不用CVXPY求解，但依赖导入沿旧环境，不重装。

这是新软件简单路径对照，不是MID/SOCP改变了目标：初表由同输入t0候选传播+32B序列化总时延最小选出，同分初次字母序；运行时每1秒接收滞后.5秒的状态，按此快照枚举无环可行链，恰好k边（None允许1..4）；同代价1e-12秒内保留源当前已安装链。图预览候选不能作为真实走法。不可行返回空path/明确drop，不降跳、不改成TTL上界。

只在到达观测后实际计算，计算模拟.2秒、实际枚举壁钟另列。源端是该run主src所在控制器：本地在config_publish时安装，其他源（反向开启）必须等有限逐边排队/传播/成功后config_install，失败不会悄悄装表。中央控制器对当前已安装源表有理想状态知识；图状态仍是滞后观测，不传未来。相同路径不重复发布，恢复同分保留备用链，避免无谓切回。

每个源包生成时拷贝**完整简单链+path_version**，后续转发严格按其链和索引，不查看新表来接尾；任何重配置不会拼接两条路径。旧在飞包可能仍走旧失效链并真实丢弃，新表只影响其后生成的包。actual_path由每个实际接收追加，不是直接复制候选；只有终点且到齐末索引才产生destination_rx。TTL8仍仅安全上限。

新增实际事件：candidate_paths/plan_start/plan_end包含observed_at和候选；config_publish/config_install给有效时刻/路径；generate包含locked_path,path_version,planned_hops；hop_rx/relay/tx_attempt/destination_rx给actual_path及actual_hops。TX事件中path_index表示即将到达的目标索引，检查当前node与next_hop请用locked_path.index(node)+1；RX/generate的索引是本节点索引。每条tx和arrival仍有transit_id/实际序列化与传播时间。网络途中失败/有限边队列/无ACK/去重沿CustomEngine，没有硬件、服务或新MID空口协议。

D请在新面板显示“时延感知简单路径（新对照）”，原MID明确是速率/成功率的SOCP，不能更名。单向默认120包/60秒，反向开关才240。结果中固定链/新策略按每包源目的/实际路径/时刻展示，不能以候选图替代已收到包。

**已可查看的新结果**在`simulation/outputs/E1-021/20261107-01-routing/`：normal、two_hop_failure/delay、three_hop_failure/delay，各自INDEX及原始事件。断链例固定80/120、时延感知117/120；两个升时延例均120/120，但22..38秒生成的实际目的包平均时延：2跳固定822.5ms/新82.5ms；3跳固定863.75ms/新123.75ms。新策略实际ABC→ADC，ABEC→ADBC，源安装21.2秒，新生成包21.5秒起用备用；40秒恢复后同分不切回。这是软件结果，非RF。

`20261107-02-boundaries/PROOF.json`逐包核所有目的actual_path==locked_path、简单且恰k边，TX沿锁定边，生成版本与当时已安装源表一致，计划不预知；两臂相同输入/初表/源计划。另有bidirectional实际两向240生成、严格3跳在2跳图无路则0交付。检查脚本最初把TX path_index误解为源索引，失败记录保留，修正验证后通过，未因此改运行事件/重跑旧数据。其后仅补了反向当前已安装链的同分状态选择及不限跳无路文案，不改变上述单向结果。

服务、8767热更新及浏览器操作由E2/D执行，E1未启动HTTP/实板。任务卡E1-021可直接消费此交接，不等待再次求解或新冻结。
