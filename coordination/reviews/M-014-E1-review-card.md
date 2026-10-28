# E1-012 | A0新任务入口与真实模型运行

- 状态：review
- 负责人：E1（唯一）
- 更新：2026-10-28，Asia/Shanghai
- 基准：7f92debd36310a7d5e37ef52d23c019138284cdd；M开始时工作区干净
- 工作副本：D:\Multi-Agent Network
- 权威任务卡：D:\Multi-Agent Network\coordination\tasks\E1-012.md
- 可写路径：simulation/edge_agent_entry/（仅本卡唯一代码写入者，保留既有功能）；data/agent_native/E1-012/；simulation/outputs/E1-012/；simulation/results/2026-10-28-E1-012-a0/；research/agent_native_network/a0_20261028/MODEL_RUN.md；本卡
- 写入保留：M核对M-013各卡done、无活跃范围冲突，以上具体范围独占保留；确认停写/进程结束后释放。
- 依赖：M-013已验收；E2执行核验需E1冻结；D整合需E1/E2冻结；C按M冻结派发。
- 审查：C-015独立审查，M验收；执行者review停写，不自行done。
- 运行预算：真实模型worker最多4次启动（失败也占名额），每次最多256新token/180秒墙时，累计worker墙时720秒；串行运行。每次调用最多一张64x64合成图（记录实际processor张量）；固定两输入，允许一次提示/格式修订，实际调用全入账。预检最多两次，第二次仅在首失败后有明确资源状态变化时执行，不定时轮询。启动要求free RAM>=2GiB、free VRAM>=2.5GiB；不得终止无关进程。仅本轮新目录写入；下载/训练/新网络仿真均0；共享环境/旧env及模型只读。预算停止后回填，不无限续跑。

## 目标与范围

用户要求推进下一步实验，本轮落实框架S03/A0。适配旧任务绑定为明确的新任务卡/输出根/预算与只读资产入口，不能只改旧卡hash、删ledger或写旧输出。复用E1-010/model与env只读，保持D已冻结SOURCE_LOCK身份核验。完成真正加载、图像张量、生成、原始输出与工具合法性记录。实现必要的任务隔离/累计预算回归检查后运行A0。两个独立私有上下文的红/蓝64px合成图，无颜色文本泄露，真实视觉/格式兼容分别评分。保存实际生成调用数和worker启动次数、加载/生成时延、GPU峰值（注明测量范围）及错误。必要运行时修复或一次提示修订可在总预算内续行，全部失败留存；不得用mock/预写回答替代真实输出。源码/配置/卡快照与成功失败结果归档，不纳入模型/环境大文件。

## 输入与验收

读START_HERE、当前角色说明、CURRENT、本卡、EXPERIMENT_FRAMEWORK的S03与MODEL_CHAIN，按需读现有a0/preflight/common/model_worker/model_backend及M-012来源报告。执行前确认新输出目录不存在、保存公共RUN_MANIFEST与源码/配置/卡快照；原始失败及旧结果保留。主卡是实时权威；不得从worktree旧副本取状态。只沿已登记真实角色聊天，不建子代理/跨聊天发消息；Git写由M串行。模型资产与env只读复用data/agent_native/E1-010；来源锁仍用preparation_20261028/SOURCE_LOCK.json，不重新下载。

## 交接检查点

- 最后完成：独立E1-012入口/累计预算/来源核验适配；按M低RAM修订完成父进程监测，执行第二次正式预检及1次真实worker启动；低RAM保护停止后归档并冻结。
- 已验证证据：最终35项检查通过（07-monitor-final-checks）；08重新核验13项模型资产身份；10核对执行/测试/当前源码与配置摘要一致。两次正式预检、1次worker启动、生成started/completed均0、worker墙时33.203秒；无下载/训练/新网络仿真。
- 未决：A0未完成。worker最后仅有loading初始记录，加载是否完成无证据，未取得processor张量、视觉/JSON输出或GPU峰值；系统可用RAM曲线不等于worker进程峰值。需要更多可用RAM或另行验证轻量运行时，无未测容量保证。
- 下一步：E2/C独立核对、M验收与决定后续方案。两次正式预检已用完；虽剩3次启动名额，监测保护停止已持久入账并禁止自动重试。E1在review停写，不等待资源或后台续跑。
- 进程：本卡worker PID49936已由父进程wait回收；controller PID46488同步退出；10-final-audit/process-check.json按这两个PID查询均无存活。全机CIM枚举被拒绝，未声称全机进程已检查。
- 关闭依据：待C独立审查与M验收。

## E1执行与冻结证据

- 03第一次正式预检：2026-10-28 21:22:23，free RAM=1,939,304,448 byte、VRAM=4621MiB，原2GiB门槛失败，worker 0；原始目录保留。
- M明确修订后，05只读确认Transformers4.51.3/Accelerate0.32.1源码支持meta初始化及根device_map直接CUDA加载；静态支持不等于本模型实际加载通过。
- 08第二次正式预检：21:28:30，free RAM=1,899,212,800 byte、VRAM=4610MiB，1.5GiB有监测模式通过；新主卡、配置、代码和资源记录完整保存。
- worker-01：21:28:34开始，33.203秒后记录low_system_ram；128次系统RAM采样，相邻最大0.266秒，最后412,577,792 byte低于512MiB。worker_reaped=true，按主卡停止后无重试/提示修订。
- 失败保留：03资源失败；08保护停止与RAM轨迹；09只读证据辅助脚本GBK读UTF-8失败（无worker），10改显式UTF-8核对通过。05/09/10公共manifest为检查后补记，已明确标注，不猜填未知来源字段。
- 报告：research/agent_native_network/a0_20261028/MODEL_RUN.md。
- 原始目录：simulation/outputs/E1-012/；累计账本：data/agent_native/E1-012/worker_ledger.jsonl。
- 归档：simulation/results/2026-10-28-E1-012-a0/；296文件、25,094,847 byte，ARCHIVE_VERIFICATION.json记录全部来源与归档SHA256一致；无模型/环境。ARCHIVE_MANIFEST.json SHA256=`532dd1cef8aca97b6e4ec180fe77b27db6e9687455eb9ab6d8a4d0a0f6b3d6c2`。
- 归档中的03/08主卡快照为各自执行时版本；本卡最终交接和归档摘要在归档后补记，不将其伪装成运行时卡快照。源码Python/JSON最终版本与07/08一致，README在执行后补充模式说明并纳入最终归档。相关代码与文档停写，可供E2/C读取。

## M执行检查点

M授权E1-012在本卡新预算内执行有限A0真实模型兼容验证。固定模型revision与身份锁沿M-012已验收来源；本卡已明确启动/调用/token/时间、只读资产与新写入范围。E1完成入口适配及相关检查、当前资源达到门槛后可直接运行，无需再次等待M或用户许可。新控制器以本卡为准，旧E1-010尝试记录只读保留；新卡累计账本独立，所有新启动含失败占本卡名额。

## M有监测低RAM加载修订（03预检失败后）

03已保存free RAM=1,939,304,448 byte、VRAM=4621MiB，worker未启动。原2GiB是未校准的执行门槛，不能据其重复停止判模型不可运行。M只读safetensors头：489张量、507,482,304参数、存储F32，FP16参数体积1,014,964,608 byte（0.945GiB，不含运行时/激活），并核对Transformers4.51.3官方device_map文档及本地modeling_utils逐参数设备加载。参考https://huggingface.co/docs/transformers/v4.51.3/en/main_classes/model 。

在现有代码范围内授权一种明确的新加载配置：所有权重直接device_map={"":"cuda:0"}、float16、low_cpu_mem_usage=True，local_files_only且无CPU/disk offload；先只读核对现有accelerate兼容性，不安装/下载。新增父控制器资源监测，使用现有依赖或标准库Windows API，每不长于0.5秒记录系统可用物理RAM；低于512MiB或监测不可用时，立即终止并等待本卡自己启动的worker，保存最后状态/资源曲线，不动无关进程。墙时超限/OOM仍停止，监测触发后本卡不自动重试。不得声称此门槛等于实测峰值或完全保证无资源影响。

只有该直接GPU+父进程监测配置允许启动RAM门槛改为1.5GiB（1,610,612,736 byte）；VRAM门槛保持2.5GiB。默认旧模式仍2GiB。允许剩余一次正式预检核对这一配置变化，须保存新主卡/配置/代码及资源状态，原03失败保留。控制器自己的监测环属于这一次有界worker执行，不是后台任务或等待资源轮询。最多4次worker、每次256token/180秒、累计720秒与一次提示修订完全不变。通过必要监测/范围检查并满足新门槛后可直接运行；原子进程不活跃时才回填主卡或更新配置。若加载方案不受现有运行时支持，或新门槛仍不满足，保存明确结果并停写，不扩下载/设备/模型。
