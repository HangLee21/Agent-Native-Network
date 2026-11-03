# ann.analysis.v1：H接入合同

本接口接收文件并返回字典，不打开串口、不执行固件、不写H目录。实际C测试/固件及当前阶段状态见VALIDATION.md；本文件只定义分析API。SHA256由E2主卡局部冻结给M，之后本文件和analyze_logs.py停改，依赖仅Python标准库。

## 调用

以importlib.util.spec_from_file_location加载冻结的`tests/espnow/analyze_logs.py`，调用：

```python
result = module.analyze_files(config_path, log_paths, manifest_paths=())
```

配置示例（示意，不是实测）：

```json
{
  "run_id": "one-unique-run",
  "source_node_id": "00:00:00:00:00:01",
  "destination_id": "00:00:00:00:00:05",
  "mode": "reliable",
  "evidence_kind": "synthetic",
  "expected_generated": 10,
  "receiver_log_complete": false,
  "measurement_duration_us": null,
  "duration_clock": null
}
```

mode只能raw_no_retry/reliable，分别输出。当前E1 v3/v4协议bench属于可靠事务，没有显式raw bench命令；分析器支持raw标记不代表固件或台架已实现/运行该模式。多个origin生成（例如反向echo）必须指定source_node_id；原请求分母不包含接收端自动生成的反向echo。

CLI仅供E2自己的新run：`python -B tests/espnow/analyze_logs.py --config CFG --log SERIAL [--log MORE] [--manifest CONTEXT] --output simulation/outputs/E2-015/<已带manifest的run>/analysis.json`，拒绝覆盖。H调用Python函数后在H获分配的新输出写结果和追加测量，不使用E2输出根。

## 输入与不可推断项

支持ann.serial.v1原行，或H serial.jsonl的外层`direction=device_rx,event={...},evidence_kind=...`；host_tx与非协议启动日志忽略。重复JSON键/NaN不作有效证据；损坏JSON使接收覆盖未确认。每文件≤10MiB、每行≤16KiB。

`node_id+boot_id`是logger，`origin_id+origin_boot_id+seq`是协议事务。rx/echo仅unique_receive=true的端点接收算交付；frame_rx不是端到端成功。unique_receive存在时必须是JSON布尔值；0/1、字符串、null均记issue并排除该行，不填PDR/goodput。false不证明交付，也不作为legacy echo的RTT。仅synthetic旧fixture允许缺字段rx，或缺字段echo作为同源同boot的旧RTT标志；hardware_measured禁止这两项兼容。duplicate是去重接收观察，不重复goodput。origin boot缺失且跨源重启seq冲突时保持歧义。

generated在E1合同是核心接受的事务产生；不包含未接受的无seq尝试。expected_generated给冻结的应有数，不匹配时不隐藏失败或少量日志而宣称完整PDR。源级所有签发/拒绝统计仍须配合H原计划/终态计数，不能用此核心接受分母替代应用全体尝试。

tx_submit status0是即将调用传输，不能算driver已接受；只有显式accepted才填driver_accepted，其余给null及原因/已知子集。tx_result status1/0为link成功/失败，负值属于错误或未知，不当端到端交付。tx_attempt只按node+logger boot匹配本地提交/回调并去重复，不是RF重试或应用尝试次数。

echo是独立反向事务的端点接收；RTT只取echo_correlation中的request_origin_id/request_boot_id/request_seq，与同源同boot的generated时钟配对，same_source_boot须true。不相减两节点时间。t_us为毫秒乘1000，不能宣称微秒RF精度。创建时刻较早的排队事件可能晚于TX输出；保留clock_order_warnings，RTT仍需非负同源间隔。

同一run/origin/boot/seq重复generated时，保留首行与重复行来源，标记身份歧义，连完全相同的重复行也不自动去重。该身份全部echo不计有效RTT，计入invalid_echoes和generated_without_echo。ambiguous_generated_identity_count、identity_evidence.generation_ambiguous和metric_status.rtt_p95_ms.excluded_ambiguous_identities给出排除范围。其他无歧义身份仍可形成有效成功子集；没有有效子集时RTT为null，reason=ambiguous_generated_identity。

receiver_log_complete须明确true才能算PDR。goodput窗口须来自receiver_local_window或host_monotonic_controlled_window的实测时长，不能以count×interval或第一/末成功包间隔替代。goodput定义为目的端唯一协议payload bit/窗口，扣112-byte ANN头，但payload内的echo相关8byte等元数据仍包含，不能改称语义效用。距离、单向时延、RF重试、PHY airtime无实测输入则null。

## 来源与输出

返回schema=ann.analysis.v1，含generated_unique、driver_accepted/known/unknown、link_callbacks_*、destination_unique_rx_observed、duplicates、PDR/goodput、成功echo子集P95、missing echo与identity歧义、issues/clock_order_warnings/callback_binding_issues。metric_status逐项记录可算状态或null原因；RTT用nearest-rank P95，失败echo不删除。identity_evidence列生成、目的接收、echo的源文件和行号；source_logs/source_manifests/source_config附SHA256，另给analyzer_sha256。

硬件计算配置evidence_kind=hardware_measured，须H capture manifest（task_id=H-001,status=hardware_capture_unanalyzed，run_id与配置一致）和hardware_serial envelope、明确logger/origin boot。所有传入的H capture上下文都须同run，缺run或冲突run拒绝；其他任务/状态的manifest可以作补充来源，但不能支持硬件计算。内外任一synthetic均禁止升级实测。板卡绑定/真实串口与nonce握手仍由H保证，文件标记不构成物理认证。

H不可变capture context还须包含`log_sha256`对象：key为每个传入日志的`str(Path(log).resolve())`绝对路径，value为该文件原字节SHA256。每份H capture context均须覆盖全部传入日志；缺映射、缺日志、错hash或分析前日志变动均拒绝。该要求只约束hardware_measured；合成源码/构建manifest可继续按原格式传入。示意：`{"task_id":"H-001","run_id":"one-unique-run","status":"hardware_capture_unanalyzed","log_sha256":{"D:\\...\\serial.jsonl":"<64 hex SHA256>"}}`。

H应在捕获结束后先保存**不再改写的捕获上下文manifest**，然后作为manifest_paths传入；不要传一个随后还会更新的RUN_MANIFEST造成结果中的来源hash失效。raw log、分析配置亦不可在计算后改写。分析结果保存到新文件后，按其evidence_kind与metric_status仅对有效实测数值追加测量，source指向分析及原始hash；未知量继续null。无硬件时仍not_measured/hardware_not_available/source=null，不调用计算填虚拟值；合成互验结果仅存synthetic目录。未来台架真正执行后可算项应实际追加，不能永远只留未分析null。
