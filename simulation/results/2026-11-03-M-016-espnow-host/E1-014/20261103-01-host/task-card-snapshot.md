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

- 已做：M建卡预留范围。
- 证据：待执行。
- 公共接口检查点（2026-11-03，实施前冻结）：firmware/agent_native/include/ann.h SHA256=d7da15f4d00639a88c8691b38599f7199b070322a7de00d89ebf0b06dba9b021；include/ann_console.h SHA256=e495a23a6a7dfa78e6ab8f54d5bb3b41c9c467439800633a20921304db49453e；INTERFACE.md SHA256=01451e3205b27ca88fd5de83c70b566943c0d6e4999e295c18369af666746f83。记录真实头文件/API、ann_host CLI及串口arm/bench/事件/wire合同，供M冻结给H/E2；当前仅接口冻结，尚未宣称CLI可运行/固件编译通过。后续实现保持该接口，必要变更另记hash交M。
- 未决：硬件未到，真实测量待后续。
- 下一步：按合同实现/准备。
- 进程：无。
- 审查/关闭：待C/M验收。
