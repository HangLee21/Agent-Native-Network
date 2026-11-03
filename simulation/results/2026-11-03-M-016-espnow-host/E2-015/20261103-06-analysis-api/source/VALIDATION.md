# E2-015当前验证状态

2026-11-03，实际E2独立聊天。当前是准备及H分段独立验证，**未编译/运行E1核心，未进行ESP目标编译或无线测量**。主卡running，等待M完整核心/串口事件冻结后继续，不轮询、不后台运行。

已实现独立日志分析器、wire v1参考编解码、黑盒trace性质检查器、硬件未测字段校验和12项协议用例设计。最新已运行版本见`simulation/outputs/E2-015/20261103-05-H-envelope-analysis/`：48项通过，失败/错误/跳过0；不是48项C测试或硬件样本。后续CASES只将100事务寿命强化至60000ms并要求第17和100条后重放旧live数据，用例设计不是已运行结果。

H_task_isolation_v2的8份文件与M冻结hash匹配，输入绑定见frozen_inputs.json。独立核查实际profile与examples保持board=unverified、hardware_available=false、bindings=[]、armed=false；实际measurement_ledger默认六项value/source均null。8项E2新增H检查覆盖host-synthetic不能登记实板、USB桥名称不能代替物理绑定、错误OS身份先拒绝、默认入口mocked enumeration下不打开任何串口/不填测量、任务根错误先拒绝。所有临时输出在E2 run目录；未调用H的实际枚举/串口或H-002。H已有14项只作来源，不记本轮重跑。

日志分析同时支持原始ann.serial.v1与H的device_rx envelope；排除host_tx，synthetic标签不得提升hardware_measured。按目的节点与origin+origin_boot+seq去重，不以driver接受/发送回调当交付；若来源boot缺失且seq跨源重启复用，保留身份歧义，PDR为null。RTT仅源节点同boot时钟，未知有效窗口不计算goodput，不推单向时延/RF重试/airtime/range。H当前仅采集/分类，**实际测量导入和分析自动接线尚未实现**，等待最终冻结事件映射及H后续集成，不能冒称已可自动实测。

运行历史均附公共manifest及源码/合同/卡快照：

| run | 结果 | 限制 |
|---|---|---|
| 20261103-01-preparation | 37项通过 | 独立准备工具，未测C |
| 20261103-02-strict-json-preparation | 38项通过 | 新增重复JSON键/NaN拒绝 |
| 20261103-03-H-frozen-independent | 38项运行、setup error 1 | 前置校验发现旧ann.h偏离冻结后，我仍启动测试，H冻结清单未生成导致FileNotFoundError；原错误/输出保留，不算H失败或通过 |
| 20261103-04-H-frozen-corrected | 46项通过 | 仅H冻结8份绑定，纠正错误依赖，不读E1活动实现 |
| 20261103-05-H-envelope-analysis | 48项通过 | H envelope/合成不能升级实测两个新增检查 |

五次累计子进程执行约2.266秒/600秒；无超时/资源保护停止，单命令≤120秒；无模型/训练/旧仿真/驱动安装/全局环境修改。输出都保留，没有覆盖原run。

旧公共头最初与v1冻结匹配，后检测hash变化即停止依赖该冻结的C集成。M随后授权单件ann.h v2，实际SHA256为1a39ed4df19f0bfa63ca3da213ff5bc23c7047beaea23020e61e82ae5558e309，与M一致；包含per-origin/boot序号窗及ann_submit参数/返回约定。**新src/最终INTERFACE未获完整冻结，仍未读取或编译。** 串口origin_boot、node boot/run归属、tx状态及echo时刻以最终合同为准，E2不猜。

待完整冻结：编译真实C、独立驱动正常/分区/替代路径、重复数据/ACK、取消/到期、源/中继重启、pending/queue容量、100条低负载连续事务并在live期重放旧副本；与独立wire参考交叉验证；按最终串口事件适配日志，再回review。GCC仅定位C:/Strawberry/c/bin/gcc.exe，当前没有编译成功证据。真实硬件数值仍null，不能用合成成功代替固件/无线成功。
