# E2-015独立协议与日志验证

当前准备依据：M-016-contract v1及M冻结的ann.h、ann_console.h、INTERFACE.md。E1 src/ESP适配仍活动时不读取、不编译。没有硬件、不开串口，不安装依赖，不运行模型或旧ns-3。本目录是E2独占验证文件，不写firmware/H工具/研究报告。

- `CASES.json`先冻结正常、分区、替代路径、重复ACK、取消、到期、重启、队列、raw/可靠、串口联锁与硬件null用例；实际C核验等M完整冻结。
- `wire_reference.py`独立按公开112-byte little-endian/CRC32合同生成/解析字节；自身round-trip和破坏检查只检验参考工具，未替代E1实现交叉测试。
- `protocol_properties.py`只审计归一化黑盒事件；分区仍允许无效发射，禁止伪造成功交付；重复/终态/队列分别检查。v1不承诺跨接收重启/去重过期exactly-once，测试按明确接收epoch限定。
- `analyze_logs.py`接收文件，不打开设备。仅解析ann.serial.v1；配置必须声明run、目的、raw_no_retry或reliable、证据类型和接收日志完整性。driver接受、link callback、目的唯一接收分列；goodput只计唯一协议payload、扣112-byte头，未知测量窗/接收覆盖保持null。RTT仅同一源node+boot时钟的generated→echo；无同步不算单向时延，未回echo保留分母。origin_boot缺失且seq跨源重启复用时拒绝猜身份，PDR保持null。
- `validate_measurement_record`校验未测字段null和source=null，fixture不得写硬件测量登记。工具只能检查声明/记录一致性，不能靠JSON认证实物。

有限主机测试入口：

```powershell
python -B -X utf8 tests/espnow/run_validation.py --output simulation/outputs/E2-015/<新的唯一run-id>
```

每次子进程≤120秒，全卡累计≤600秒；持久ledger保留名额，异常中断按保留上限收费；超时/输出超限保护后不自动再跑。输出根拒绝覆盖、附公共RUN_MANIFEST、卡/合同/源码快照。当前阶段result明确actual_E1_core_compiled=false；失败和跳过均保留，不用准备测试冒充C/固件/无线通过。

公共头给出ANN_FRAME_MAX=250、HEADER=112、payload≤138、路径≤8、pending≤8、out/event≤32、table≤16、source lifetime≤60000ms、最多3次发现和3次数据尝试。bench按合同总长112..250，echo120..250，显式arm匹配node/run才可start/bench，finite≤60s/count≤1000；host身份必须host-synthetic，不能伪装esp32s3。bench参数本轮不发送。

公共接口尚待实现冻结才能确认：串口rx/echo如何明确origin boot、tx_submit/tx_result状态编码与echo时刻语义；ann_submit未命名参数和函数成功/失败返回值。E2不自行猜测这些细节，缺项回填自身主卡由M协调。完整冻结后新增真实C黑盒驱动/测试，用实际核心函数与独立参考字节交叉核对，并明确编译器/命令/测试节点/故障注入和所有限制。软事件丢包不是RF试验；主机编译不等于ESP-IDF目标编译。

M随后单件冻结ann.h v2（1a39ed4df19f0bfa63ca3da213ff5bc23c7047beaea23020e61e82ae5558e309），ann_submit参数与接受0/拒绝-1或-2已明确；完整src/串口实现仍待冻结。H v2独立检查完成后H进入修复，test_h_frozen默认显式skip，防止读活动源码；只在M重新完整冻结后授权启用。第03轮前置文件缺失错误及纠正后的04/05结果均保留。

## 给H的分析API（候选，实际E1日志互验后最终冻结）

`analyze_logs.analyze_files(config_path, log_paths, manifest_paths=()) -> dict`只读输入、不写任何H文件，返回`ann.analysis.v1`；H可将结果追加到自己获分配的新输出。CLI为`python -B tests/espnow/analyze_logs.py --config CFG --log SERIAL [--log SERIAL2] [--manifest H_RUN_MANIFEST] --output simulation/outputs/E2-015/<已有manifest的新run>/analysis.json`，拒绝已有文件。支持H serial.jsonl的device_rx/event envelope并排除host_tx。

配置必填run_id、destination_id、mode（raw_no_retry/reliable）、evidence_kind（synthetic/hardware_measured）；receiver_log_complete须明确true才算PDR，measurement_duration_us须来自receiver_local_window或host_monotonic_controlled_window才算goodput。不得把count×interval当实测窗。实际bench若只支持一种模式，另一种标未实现，不能更改配置标签假装测过。

输出分generated_unique、driver_accepted、link_callbacks_*、destination_unique_rx_observed、duplicates、PDR/goodput及成功echo RTT；`metric_status`逐项给unavailable理由。`identity_evidence`关联源/目标/echo日志文件与行号，source_logs/source_manifests/source_config保存SHA256，并记录analyzer_sha256。无同步单向时延、未观测RF重试/airtime与range均null。硬件计算要求H capture manifest及hardware_serial envelope；synthetic不能升级。标记/文件一致性不是物理认证，板卡绑定与真实采集仍由H执行。
