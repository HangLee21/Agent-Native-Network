# 竞争广播服务：实现与复核口径

2026-10-26，E1-007。服务及17项语义测试已完成，C服务预审通过，E2已完成60次固定业务回放并推进任务运行；最终验收由C和M完成。代码为[wireless_broadcast_service.py](../../simulation/wireless_broadcast_service.py)，使用[固定无线合同](WIRELESS_SERVICE_CONTRACT.md)的参数；任务执行由E2-007负责。本文件记录服务行为，不包含任务性能结果。

## 接口与输入

```python
service = WirelessBroadcastService(policy="fifo", seed=0, capacity_bytes=65536)
message_id = service.submit(now, source, recipients, kind, payload_bytes, key=None)
deliveries = service.pop_due(now)
next_time = service.next_event_time()
statistics = service.stats(now)
```

`policy`为`fifo`或`latest_state`。节点ID使用整数，正文使用不可变`bytes`。接收者按调用顺序去重，空接收者列表报输入错误。一次广播的帧时长与接收者数无关；每个成功接收副本有独立交付记录。`key`仅作为附加元数据保存，实际替换键从正文提取，旧执行器无需修改`publish`。

时间输入为模型单位，1单位=20秒。`pop_due`只返回已完整接收的正文，返回后不再重复返回；`stats`可推进事件但不消费交付。`next_event_time`在没有事件及待取交付时返回正无穷。返回字段沿用旧接口的`message_id/source/recipient/kind/payload/generated_at/delivered_at`；其中`generated_at`为本次提交时间，另列`enqueued_at`、正文的`information_generated_at`和整数`delivered_at_us`。重发保留原正文，所以能区分传输时延和信息年龄。

## 竞争和时间推进

每个源维护FIFO队列和独立退避计数。队头首次具备争用资格时，以字符串`E1-007|MACseed|source|本源队头激活序号`计算SHA256，取前8字节大端整数模16，得到0至15的退避值。键不包含任务条件、消息ID或全局插入顺序。碰撞后该帧结束，无ACK、重传或碰撞扩窗；下一个队头按相同规则取得自己的退避。

当前空闲段以最近一次信道恢复空闲的时刻加DIFS为时隙原点，初始原点为34微秒。新队头等待自己的DIFS，再向上对齐这一时隙网格，随后倒数完整空闲时隙。因而空闲中途入队最多增加一个时隙的对齐等待。多个队头在同一时刻归零时统一收集并开传，全部标记碰撞，不由Python遍历顺序选赢家。

信道变忙时，其他队头只扣除已经结束的完整空闲时隙，未满时隙不计；忙期间冻结剩余退避。所有重叠PPDU结束后，再经过DIFS恢复倒数。碰撞帧长度不同时，短帧完成可以释放本源缓存、激活下一队头，但必须等最长帧结束。正在发送的完整帧持续占用缓存。服务用事件跳跃推进至下一次开传或帧完成，长时间空闲不会逐9微秒循环。

入队资格向上量化到整数微秒，观测推进向下取整到已过去的微秒。整数事件转换为模型浮点时间再转回时，乘积若距最近整数不超过4个浮点ULP，则识别为同一整数边界；其他值保持ceil/floor区别。测试覆盖相差0.1微秒的观察、0.1微秒入队以及`next_event_time → pop_due`往返。

这一模型保留了同域竞争、冻结退避和广播碰撞。使用固定DIFS/时隙对齐、每队头重新抽取CWmin退避，不模拟完整802.11的post-backoff、EIFS、硬件接收链和信道误码。参数和支持范围见合同。

## 状态替换与队列容量

`latest_state`识别现有两类消息结构：自身状态按`(source,self_state,source)`分组、版本为`state.seq`；现场快照按`(source,task_scene,scene.task)`分组、版本为`scene.version`四元组。不能解析的正文按普通FIFO处理。调用者继续提供原执行器产生的完整快照。

同对象更新只替换尚未开传的记录，保留原队位；若为队头，同时保留退避和倒数起点。正在开传的帧保留，新版本入队等待。不同源、不同消息类型、不同任务互不替换。

每个对象保存已接纳版本的本地高水位。低于高水位的更新拒绝为`stale_version`；同版本不同正文拒绝为`same_version_conflict`。相同正文、版本及接收者的待发重复提交合并为`coalesced`，原记录继续排队。已经发过的同版本原正文可以再次入队，这就是周期刷新所需的发送行为。它不表明发送者知道前一次广播是否成功。

容量按每源65536字节计应用正文加64字节头部，包含在发帧。替换先扣待替换帧再检查新帧大小；新帧不能容纳时拒绝新帧并保留旧帧。应用正文超过1472字节以`frame_too_large`拒绝。所有拒绝、合并和替换仍保留消息ID、正文及来源，便于复算需求与实际发送的差异。

## 账本与统计

`ledger`保存`submitted/admitted/rejected/coalesced/replaced/head_activated/backoff_frozen/contention_batch/tx_started/tx_completed/delivered/channel_idle`。各条包含整数微秒和模型时间；提交项有原始正文十六进制、SHA256、语义键、版本、接收者、实际提交与入队资格时间。退避键、冻结前后计数以及每帧起止时间足以独立重建竞争过程。碰撞是观察账本信息，发送者只得到消息ID，不获得接收反馈。

| 字段 | 含义 |
|---|---|
| `demanded` | 所有合法调用提交数，包含随后拒绝、合并或替换的记录 |
| `accepted` | 曾经接纳入队数，包含后来被替换的旧记录 |
| `dropped/rejected` | 入队拒绝数；原因见`rejection_reasons` |
| `coalesced/replaced/collided` | 待发重复合并、被更新替换、已经结束的碰撞帧，分别计数 |
| `pending` | 当前排队与正在发送的帧数 |
| `delivered` | 完整成功广播数；接收副本另计`recipient_delivered` |
| `airtime_attempt_us` | 每个已开传PPDU在观察窗口内的时长之和，碰撞发射分别收费 |
| `channel_busy_us` | 上述发射区间的并集，重叠只计一次 |
| `attempted_frame_bytes` | 已经开始传输的完整帧尺寸总和，包含尚未完成帧；不能当作已发送部分字节 |
| `completed_service_bytes` | 已结束的帧尺寸总和，包括碰撞帧 |
| `latency_*` | 本次提交至完整交付的时延，按广播记录统计 |
| `information_age_*` | 正文原生成时间至完整交付的信息年龄，正文没有时间则不进入该统计 |

帧记录恒等式为`demanded = rejected + coalesced + replaced + collided + delivered + pending`，接纳记录满足`accepted = replaced + collided + delivered + pending`。`recipient_unmet`是需求副本减成功副本，包含排队、替换和拒绝，不能直接解释为无线丢包率。`collision_attempts`包含已经开传但尚未结束的碰撞帧；`collided`只计已结束的帧。

统计的空口时间裁切到观测时刻，不把未来完整帧时间提前计入。原始应用字节、帧字节、广播与接收副本分开保存。`latency_mean/p95/max`及`information_age_mean/p95/max`使用模型时间，并附对应`*_seconds`字段；分位数采用排序后线性插值。`by_kind`保存类型内提交数、状态计数和应用字节。缓存读入和任务决策价值仍由执行器的信息账本分析。

## 验证与复算

Python为仓库`.venv`的3.11.5，服务只依赖标准库。首轮16项测试全部通过；C预审后补充“短碰撞源下一帧等待最长PPDU”成为17项，第二轮全部通过。源码未因测试失败修改。测试覆盖单帧时长、实际到达、部分发射、同slot不同长度碰撞、冻结与忙时入队、两类latest、在发不可替换、版本与重复、缓存容量、帧上限、FIFO、长空闲事件跳跃、输入校验和提交顺序对称性。

历史命令：

```powershell
.\.venv\Scripts\python.exe -B simulation/test_wireless_broadcast_service.py --output simulation/outputs/E1-007/20261026-01-tests
.\.venv\Scripts\python.exe -B simulation/test_wireless_broadcast_service.py --output simulation/outputs/E1-007/20261026-02-tests
```

两个目录均已存在，复算必须选择新的输出目录，入口拒绝覆盖。每次输出含`manifest.json`（解释器、命令、源码hash、通过数）、`tests.txt`、`evidence.json`（逐场景完整服务账本及最终统计）和两份源码快照。第二轮证据已归档至[20261026-02-tests](../../simulation/results/2026-10-26-E1-007-wireless/20261026-02-tests/manifest.json)，源代码SHA256为`dbbd7909de51603f16ecc12f8756f369afe663f658a371b2261e505974398fc7`。

本任务共17类测试，没有运行任务策略。C服务预审已通过；E2使用冻结服务完成60次固定业务回放并推进既定任务矩阵。最终语义、结果与结论由C独立核验，M负责验收及汇总。
