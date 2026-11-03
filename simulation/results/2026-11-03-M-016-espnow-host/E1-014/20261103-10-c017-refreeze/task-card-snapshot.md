# E1-014 | 可主机验证的协议核心与ESP32-S3固件

- 状态：running
- 负责人：E1（唯一）
- 更新：2026-11-03，Asia/Shanghai
- 基准：d8325a230ce41943f43528c6a0c9552949e07abe；开始工作区干净
- 工作副本：D:\Multi-Agent Network
- 权威卡：coordination/tasks/E1-014.md
- 可写路径：firmware/agent_native/**；本卡；simulation/outputs/E1-014/**
- 写入保留：M已核相关既有卡done、无活动保留冲突；本卡范围预留，review前不释放
- 预算：主机开发/单元/协议事件测试每命令≤120秒、累计执行≤600秒；不启动真实无线/模型/旧ns-3实验。输出≤100MiB；超时或资源保护停止后留证交M，不自动重启保护停止。

## 当前要求

用户已购买EoRa-HUB-400TB×5，要求既有E1/E2/D/C加H实现到货前代码与通信协议，硬件测量留null并在到货后自动检测补充。采用ESP-NOW单跳承载，上层实现对等发现、多跳、可靠事务/状态合并；先静态台架再上车。当前没有硬件，不声称无线实测或ESP目标编译通过。保留全部历史。禁止模型运行、旧仿真续跑、刷机/擦除、打开未绑定串口、驱动安装、修改全局环境。允许官方资料读取和本任务隔离的有限主机测试；实际窗口执行，不使用子代理。读START_HERE、角色、本卡及coordination/handoffs/M-016-contract.md。各自仅写分配路径；不得读其他窗口活动稿，依M冻结后集成。Git写由M串行。新运行输出simulation/outputs/<任务ID>/<唯一run-id>/，拒绝非空目录，附RUN_MANIFEST来源字段；冻结源码hash。无硬件失败和缺工具记清，不能用fixture成功代替固件/无线成功。完成回填review、hash、进程停止，等待C/M。

## 交付与验收

实现可移植C协议核心和ESP-IDF工程、ESP-NOW适配与串口JSON控制。必须提供真正可执行的发现、有限TTL/去重的按需源路由RREQ/RREP/错误处理、多跳转发、端到端接收确认/有限重试/幂等、状态latest合并和到期/取消处理（明确实现边界）。五节点本机事件驱动逻辑harness直接运行同一核心而非另写假模型。边界：bounded tables/queues、来源boot+seq去重、ACK丢失重试、节点重启、不依赖全局状态。host CMake/编译入口与真实测试记录；ESP32未编译需标明。优先先冻结公共头/CLI/串口合同并交M，H/E2据此接入，然后完成实现。ESP-IDF固定5.5.1为候选版本，核官方API；无SDK时不大规模下载安装，交可构建工程和缺项。固件上电idle，info不启动射频实验；显式start/bench才发测试。

## 检查点

- 已做：公共接口先冻结后实现portable C99协议核心、CMake主机CLI、同核心五节点事件harness、严格串口JSON/绑定arm/有限bench、ESP-IDF v5.5.1候选适配工程。实现HELLO、RREQ/RREP、TTL/循环抑制、源路由DATA/ACK/ERROR、有限重试、状态latest/expiry及best-effort CANCEL，全部有界；具体弱保证与未实现项在INTERFACE/VALIDATION说明。
- 证据：最终主机运行simulation/outputs/E1-014/20261103-06-line-framing/，12类场景/6208断言（含5000无效帧输入）/3437条scenario JSON记录通过，另通过idle nonce/超长整行拒绝/NUL拒绝/CRLF恢复检查。100条低并发连续事务全部端点确认；ACK丢失重试不重复交付；源和接收节点重启均检查。不是6208次无线样本。构建/测试子命令累计42.718秒、每命令<120秒，输出最终8,258,784 byte<100MiB；无保护停止、无后台继续。
- 公共接口检查点（2026-11-03，实施前冻结）：firmware/agent_native/include/ann.h SHA256=d7da15f4d00639a88c8691b38599f7199b070322a7de00d89ebf0b06dba9b021；include/ann_console.h SHA256=e495a23a6a7dfa78e6ab8f54d5bb3b41c9c467439800633a20921304db49453e；INTERFACE.md SHA256=01451e3205b27ca88fd5de83c70b566943c0d6e4999e295c18369af666746f83。记录真实头文件/API、ann_host CLI及串口arm/bench/事件/wire合同，供M冻结给H/E2；当前仅接口冻结，尚未宣称CLI可运行/固件编译通过。后续实现保持该接口，必要变更另记hash交M。
- 未决：硬件未到，idf.py/SDK缺失，ESP目标未编译（not_performed），UART/USB/板型/内存适配/真实回调行为及PDR/距离/吞吐/RTT均未测；真实测量null、reason=hardware_not_available、source=null。host fixture不能替代ESP/RF通过。無持久去重/加密配对/分片/远端原子取消/严格跨时钟截止保证；这些边界不是硬件已验证功能。
- 接口修订检查点（M要求连续100条事务）：include/ann.h加入有界per-origin/boot 64序号滑窗bitmap及取消bitmap，避免每消息消耗live seen槽；明确ann_submit参数名/返回/seq_out。新头SHA256=`1a39ed4df19f0bfa63ca3da213ff5bc23c7047beaea23020e61e82ae5558e309`，原头hash仅属最初检查点，不能继续当最终ABI。ann_console.h及wire布局保持原样；实现中tx_attempt为发送节点本boot内的提交编号，不是RF重试计数。03主机12类场景通过，含100条低并发连续事务及旧序号拒绝；最终INTERFACE/golden日志将明确源boot与本地boot及echo关联。
- 下一步：M向H/E2传递下方最终hash和golden语义（初版ann.h ABI已变，console header和wire未变），交C独立检查；E1 review停写。已交付代码不是等硬件才实现的空接口；到货后目标编译与有界实板验证由后续明确卡执行，本卡不刷机、不打开串口。
- 进程：全部主机编译/CLI/事件测试子进程已同步退出；无模型/无线/旧仿真、串口、烧写或永久轮询进程启动。未启动任何自动硬件检测，H自行负责其范围。
- 审查/关闭：待C/M验收。

## 最终冻结（覆盖初版接口hash用于集成）

- firmware/agent_native/FREEZE.json SHA256=`f38bee27cec54b9ea6e5627db4036f6b3a7aff4100b306a94051825450dbd251`，19项最终交付文件hash及对应主机exe/manifest身份；不声称ESP目标编译通过。
- include/ann.h SHA256=`1a39ed4df19f0bfa63ca3da213ff5bc23c7047beaea23020e61e82ae5558e309`；include/ann_console.h SHA256=`e495a23a6a7dfa78e6ab8f54d5bb3b41c9c467439800633a20921304db49453e`。
- INTERFACE.md SHA256=`2ab28e7cd849a4c768be94d22b6ea5c187029db192369dfbd19ced23e61fe282`，写明ann_submit所有参数/返回/seq_out，当前日志节点boot与origin_boot分别定义、tx_attempt本节点本boot内编号，link callback不等于端点ACK；echo原请求boot/seq在payload前8字节，无远端时间戳，只可同源同boot关联生成日志求RTT。
- golden/serial-v1.jsonl SHA256=`1fe7634db59c512987be068e3205e521a726bc0cc112733c7ca2e03fdc221178`；12条verbatim synthetic日志，有golden/provenance.json的原始行号/摘要，不是硬件证据。
- 07静态冻结检查：simulation/outputs/E1-014/20261103-07-freeze/，14个编译相关文件与06执行快照一致、golden逐行原样及echo同源boot关联检查通过，最终文档/头/源码副本保存于source/。此运行无新增协议/模型/硬件执行。
- 01首编译的-Werror缩进警告失败保留；02–06每次新目录及对应代码/日志/manifest保留。没有删除失败、覆盖历史输出、改其他角色文件、安装SDK或Git写操作。
