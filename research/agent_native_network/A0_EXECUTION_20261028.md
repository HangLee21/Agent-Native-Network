# A0执行记录：模型加载与生成已跑通，JSON工具协议未通过

2026-10-28，Asia/Shanghai。框架阶段S03/A0，任务[M-014](../../coordination/tasks/M-014.md)。

**A0尚未整体通过：用户直接批准恢复后，模型完成3次CUDA/FP16加载与真实生成；红/蓝两输入各取得过正确颜色词，三次严格JSON工具协议均失败。** 累计4次worker启动、生成started/completed均3、113.968秒worker墙时，启动名额已用完。首次低RAM保护停止保留为历史；B0沿此前验收结果保留，本轮未运行网络实验，A/B尚未接通。

本报告采用M已冻结的[E1执行报告](a0_20261028/MODEL_RUN.md)、[恢复冻结清单](../../coordination/reviews/M-014-restart-freeze.json)和[新增E2核验](a0_20261028/VALIDATION.md)。**E2确认新增记录一致，严格JSON工具协议未通过；一致性核验不等于A0整体通过。** 首次E2核验只覆盖此前保护停止阶段，见§6；新增核验见§7。审查与最终验收以[主任务卡](../../coordination/tasks/M-014.md)为准。

## 当前结果：恢复后的三次真实生成

用户释放资源后直接回复“批准启动”，M已核实并在[恢复冻结清单](../../coordination/reviews/M-014-restart-freeze.json)记录授权来源。21:44:05只读检查可用RAM为6,678,323,200 byte；21:47:31新增一次正式启动检查，RAM为5,083,320,320 byte、VRAM为7164MiB，通过后沿原累计账本运行。总启动上限4次、每次256新token/180秒、累计720秒均未增加；正式预检累计3次，第三次有本次明确授权。14目录复用该预检，不另计第四次。

| worker / 证据 | 输入与提示 | 原始输出 | 原定颜色词评分 | 严格JSON / 合法工具引用 | 加载 / 生成 / worker墙时（秒） |
|---|---|---|---|---|---|
| 02，[12汇总](../../simulation/outputs/E1-012/20261028-12-A0-user-approved/summary.json) | 红图v0 | ` The dominant color is red.` | 正确 | 失败 / 无 | 3.688 / 1.859 / 29.672 |
| 03，同上 | 红图v1，唯一提示修订 | ` #FF0000` | 不通过：原规则只识别red/blue词 | 失败 / 无 | 3.312 / 0.922 / 25.328 |
| 04，[14汇总](../../simulation/outputs/E1-012/20261028-14-A0-blue-diagnostic/summary.json) | 蓝图v1 | ` blue` | 正确 | 失败 / 无 | 3.500 / 0.844 / 25.765 |

`#FF0000`在RGB写法中对应红色，主评分仍按预设颜色词规则保留失败。三次提示/输入与重复次数不同，不计算泛化准确率。原文、严格JSON解析和视觉分项分别保留，未把自由文本修成预写JSON。蓝图沿用v1，单输入诊断只补缺失输入，没有第三版提示；两个输入均运行过不等于A0通过，也没有产生合法协作工具调用。

表中加载段包含processor及模型加载过程，生成时间单列，worker墙时还包含解释器、依赖导入、预处理和退出；三次兼容尝试不作正式性能统计。

三次均为独立进程/私有上下文，单张中性文件名PNG，不含其他节点图像或期望颜色文本。原始PNG为64×64；实际`pixel_values=[1,1,3,512,512]`、`pixel_attention_mask=[1,1,512,512]`、`input_ids=[1,118]`。processor内部适配产生512×512视觉张量，不能按64px张量解释推理成本；源码摘录见[15记录](../../simulation/outputs/E1-012/20261028-15-restart-audit/processor-excerpt.txt)。

实际参数均在cuda:0、torch.float16，参数体积1,014,964,608 byte。加载期PyTorch已分配显存峰值1,022,361,088 byte；生成期已分配峰值1,145,682,944 byte，保留峰值1,166,016,512 byte。两阶段分别重置峰值统计，生成阶段包含常驻模型，不含加载瞬态；这些是PyTorch分配器统计，不能当整卡占用。worker记录torch2.3.1+cu121、Transformers4.51.3等实际版本，controller库存不代替worker版本。

恢复后三次系统可用RAM最低值为2,562,977,792 / 2,756,612,096 / 2,392,031,232 byte，最大相邻采样间隔0.281秒，无新保护停止；系统RAM变化不能当单worker峰值或固定容量成功保证。02/03/04均wait回收，[15进程核对](../../simulation/outputs/E1-012/20261028-15-restart-audit/process-check.json)中本次worker/controller PID均未存活，核查范围只限本卡。

最终[13工程检查](../../simulation/outputs/E1-012/20261028-13-two-input-checks/result.json)为37项通过，12源码对应11检查、14源码对应13检查，[15审计记录](../../simulation/outputs/E1-012/20261028-15-restart-audit/result.json)核版本/配置、原归档与ledger前缀。37项检查不等于37次生成。增量归档为[user-approved-restart-20261028](../../simulation/results/2026-10-28-E1-012-a0/user-approved-restart-20261028/)，208文件、10,496,164 byte；原296文件归档保留。当前MODEL_RUN SHA-256为`bbcc692d17a271988c33422816954f16d6a85e68450613bd397c11716effacbc`，恢复冻结清单为`2247e4f9200cd94cf3c2c2396ad430a87310a9e054e9d199ce443b673369b7b5`，D读取前匹配。

## 1. 从旧入口到本轮任务

此前M-012已取得固定SmolVLM及隔离环境，但在worker前停止，见[准备报告](PREPARATION_20261028.md)。本轮新增`simulation/edge_agent_entry/a0_task.py`，为E1-012独立核对实时主卡、输出/data范围和累计预算；`common.new_run`支持显式任务作用域，旧E1-010默认行为保留。旧模型与解释器只读复用，旧账本及manifest不改。

首次实现对应[08源码快照](../../simulation/outputs/E1-012/20261028-08-A0-monitored/source/a0_task.py)，恢复后的版本见[14源码快照](../../simulation/outputs/E1-012/20261028-14-A0-blue-diagnostic/source/a0_task.py)。模型仍为`HuggingFaceTB/SmolVLM2-500M-Video-Instruct`，revision `7b375e1b73b11138ff12fe22c8f2822d8fe03467`；[来源锁](preparation_20261028/SOURCE_LOCK.json)保持原字节。08及恢复后的12/14分别校验13项白名单资产，未重新下载权重、依赖或数据。

本卡原预算为最多4次worker启动，失败也计数；每次最多256新token、180秒，累计worker墙时720秒，串行执行；原正式预检最多2次，恢复时用户另批1次。固定两张64×64红/蓝合成PNG，使用中性文件名，提示不含期望颜色，评估器标签不传给worker。每次单图、独立上下文、最多一次提示修订；首次阶段只有第一个上下文启动，恢复后两输入均有真实生成，详见上表。

## 2. 历史：原预检、M新模式与首次保护停止

| 时间/记录 | 当时配置与测量 | 实际结果 |
|---|---|---|
| 21:22:23，03正式预检 | 原模式启动RAM门槛2GiB；可用RAM 1,939,304,448 byte，VRAM 4621MiB | 原门槛未满足，在模型校验/worker之前停止；原失败保留 |
| 03之后M明确修订 | 仅允许直接GPU、FP16、`low_cpu_mem_usage=True`、`device_map={"":"cuda:0"}`，禁CPU/disk offload；父进程监测系统可用RAM | 此模式的启动RAM门槛改为1.5GiB，显存门槛仍2.5GiB；低于512MiB或监测失效即停本卡worker并wait，禁止自动重试；原调用/时间预算不变 |
| 05只读实现核查 | 已安装Transformers4.51.3/Accelerate0.32.1代码具有meta初始化、单设备映射和按设备装载路径 | 只证明实现中存在该路径，不证明本模型实际加载成功；无worker/预检增加 |
| 21:28:30，08第二次正式预检 | 新模式RAM门槛1,610,612,736 byte；测得RAM 1,899,212,800 byte，VRAM 4610MiB | 新模式预检通过，保存新主卡、配置、源码和资源快照；这是本卡最后一次正式预检 |
| 21:28:34起，worker-01 | 重新核13模型文件身份后启动；父进程执行有界资源监测 | 实际worker 1次，尚无生成开始记录 |
| 21:29:07，保护触发 | 最后采样系统可用RAM 412,577,792 byte，低于512MiB；128次采样，最大相邻间隔0.266秒 | 记录`low_system_ram`，终止并wait回收本卡worker；墙时33.203秒，随后未重试 |

以上测量与授权按先后保留。第二次预检通过是因为使用了M明确批准的有监测模式，不是RAM已超过原2GiB门槛，也不是未经记录地放宽默认条件。父进程监测只在这一次有界worker执行期间运行，不是后台等资源或定时重试。

原始入口：[03原预检](../../simulation/outputs/E1-012/20261028-03-A0/)、[08配置及快照](../../simulation/outputs/E1-012/20261028-08-A0-monitored/)、[08汇总](../../simulation/outputs/E1-012/20261028-08-A0-monitored/summary.json)、[worker进程记录](../../simulation/outputs/E1-012/20261028-08-A0-monitored/worker-01/process.json)、[RAM曲线](../../simulation/outputs/E1-012/20261028-08-A0-monitored/worker-01/ram_curve.jsonl)。

系统可用RAM受全机并发变化影响，不能把全部下降归因于worker，更不能用它当worker进程峰值。2GiB、1.5GiB及512MiB都是执行/保护条件，本轮没有测得完整模型加载所需的最低RAM或GPU峰值。

## 3. 首次保护停止阶段的检查结果（历史快照）

下表仅对应08运行及首次冻结，不代表恢复后的当前状态；加载/张量/生成和显存峰值的新结果见报告开头。

| 检查项 | 本轮状态 | 证据与解释 |
|---|---|---|
| 新任务范围/累计预算/来源保护 | 有实现与最终工程检查 | [07结果](../../simulation/outputs/E1-012/20261028-07-monitor-final-checks/result.json)共35项通过：任务/预算/评分/门槛8项、父进程监测/持久停止5项、原因果运行时16项、来源身份6项；不是35次模型实验 |
| 固定资产身份 | 08重新校验通过 | 已知内容SHA与5项普通Git身份沿冻结来源；模型/旧env只读，下载0 |
| 实际worker启动 | **1次** | 账本记录reservation与finished，计费33.203秒；不是1次完成生成 |
| 生成started / completed | **0 / 0** | 无实际生成开始/完成记录，提示修订0；未获得答案 |
| 模型是否加载完成 | **无证据** | worker最后仅有初始`loading`，未写versions、model_loaded、prepared、generating。源码中初始save位于import torch前；这只定位检查点，不证明实际停止在导入前，也不能定位到处理器或权重装载子阶段 |
| 视觉与JSON/引用兼容 | **未评估** | 没有processor张量或原始生成；汇总中的默认`visual_correct=false`、格式解析失败不能当作一次真实视觉误判或模型格式能力失败 |
| 加载/生成时延与GPU峰值 | **未取得** | 33.203秒是worker总墙时，不是模型加载完成时延；本轮无可报告的加载或生成GPU峰值 |
| 保护停止与进程收尾 | 有父进程回收记录 | `worker_reaped=true`；worker PID49936及controller PID46488的后续查询无存活。全机CIM枚举被拒绝，未声称全机进程已检查 |

29、30、34、35项是不同实现版本的回归记录，不累加为独立模型样本。监测单测使用受控子进程替身，不能代替08的实际启动；两类证据分别保存。

## 4. 失败、预算与归档不改写

| 记录 | 保留方式 |
|---|---|
| 03原门槛预检失败 | 原目录、manifest和执行配置保留，不改成新模式通过 |
| 08保护停止 | 原始stdout、result、process、RAM曲线、卡/源码/配置快照与任务账本保留；不隐藏未生成的事实 |
| 09辅助证据检查失败 | 默认GBK读UTF-8账本失败，无worker；[failure.txt](../../simulation/outputs/E1-012/20261028-09-final-audit/failure.txt)保留，10改显式UTF-8后核对，不算模型重试 |
| 05/09/10辅助manifest | 检查后补记并明确标注，未知命令/时刻/依赖不猜填；不是完整运行时追踪的替代品 |
| 首次两次预检与一次worker | 当时两次正式预检已用完，剩3次启动额度不构成续行授权；随后用户明确批准人工恢复，保留原停止事件并沿原总预算，当前4次启动已用完 |

归档位于[2026-10-28-E1-012-a0](../../simulation/results/2026-10-28-E1-012-a0/)，[ARCHIVE_MANIFEST](../../simulation/results/2026-10-28-E1-012-a0/ARCHIVE_MANIFEST.json)登记296份文件、25,094,847 byte；[ARCHIVE_VERIFICATION](../../simulation/results/2026-10-28-E1-012-a0/ARCHIVE_VERIFICATION.json)是E1的归档一致性核对。原始成功/失败、源码/配置、账本与报告在归档内，模型与环境不入档。E2另作独立核验，见§6；D未重跑检查、模型或复制大文件。

旧M-012资产、旧结果和来源锁保持；controller/worker执行快照与累计账本在E1-012范围。首次worker未写出依赖版本，恢复后worker已记录实际版本，两阶段分别解释，不用controller库存替代。

## 5. 下一步：工具协议与输出适配

1. **明确工具协议及输出适配方案。** 现有模型已完成真实加载和简单颜色输出，主要缺项是严格JSON对象及合法工具引用。下一卡先审查工具schema、提示模板、模型输出与解析器的对应关系，决定按原协议修复提示/约束解码，或明确另立输出适配合同；原始输出、严格解析和适配结果分别保存。不得把事后包一层JSON当原协议已通过，也不回改`#FF0000`的原评分。
2. **另立有界兼容验证预算。** 本卡4次启动和一次提示修订已用完，不继续加载、改提示或等待资源。新任务复用已取得模型/env，冻结代码、输入、评分、真实512×512张量与资源测量口径；在独立上下文检查合法工具对象、引用及失败路径，保留全部原文。维持监测/停止条件；初始`loading`仍不能定位首次停止子阶段，分阶段检查点继续作为可观测性改进，不能据此把当前进度写成仍卡在加载。
3. **A0整体通过后再进入A1。** 冻结合法真实私有视角、客观根问题与评分，补模型多轮驱动；之后再把实际请求接入已验证B0做固定回放/反馈执行。当前A1/A2、A/B耦合、规模及机制收益均未验证，颜色词输出不替代协作轨迹。

总览S03标为“加载/生成已跑通，严格JSON工具协议未通过”。旧M-013的[模型映射](experiment_framework/MODEL_CHAIN.md)与[网络映射](experiment_framework/NETWORK_CHAIN.md)保持为此前快照，本轮新事实从本报告进入[实验框架总览](EXPERIMENT_FRAMEWORK.md)。

## 6. 首次独立核验与冻结输入（历史范围）

以下510项核验只覆盖首次保护停止冻结，不能沿用该结论覆盖新增11–15运行。新增核验已冻结，见§7；旧核验报告保存在[首次E2归档副本](../../simulation/results/2026-10-28-E2-013-a0-validation/payload/research/agent_native_network/a0_20261028/VALIDATION.md)。

E2只在M冻结E1后读取证据，完成1次正式标准库核验（额度1/2），退出0；[自动结果](../../simulation/outputs/E2-013/20261028-01-frozen-a0/validation.json)中510项记录一致性检查通过，失败0。510是文件/字段核对数，不是模型样本。E2前后核M清单596项hash一致，复核10个run、账本及296项E1归档来源/副本，未重新加载模型、运行E1回归或重读2GB权重。

E2随后完成[首次冻结源码人工复核](../../simulation/results/2026-10-28-E2-013-a0-validation/payload/simulation/edge_agent_validation/SOURCE_REVIEW.md)，核新旧任务范围、append-only预算、M两种门槛、监测kill/wait、输入/提示和生成标记。自动结果的`manual_source_review_required`保留当时原值，人工复核另存，不回写自动输出。两PNG经独立解码为红/蓝64×64，spec仅第一张、提示无预期颜色，context hash相符；这些只证明当时输入/记录关联，不证明08模型已处理图像。

核验结论与执行记录一致：2次预检、1次worker/33.203秒、128次RAM采样、保护后无新预检/启动，生成started/completed为0。加载、张量、JSON、引用及红蓝语义均未建立/未测，没有把空输出默认false计为误判。03旧manifest缺`config_sha256`的事实保留，用M冻结与归档关联配置；05/09/10辅助manifest后补，未知字段不猜填。E2未发现需要E1修复的证据矛盾，不将此结论等同A0通过。

E2证据另归档为[17文件清单](../../simulation/results/2026-10-28-E2-013-a0-validation/ARCHIVE_MANIFEST.json)，与E1原始执行、自检分别保存。C-015/M验收进度从主卡读取。

| 输入 | SHA-256 / 范围 |
|---|---|
| M-014首次E1冻结清单 | ebd13fd8df0b5dddb0236211a87154d286860054d3c4a208ee75a51eed13cc06；[清单](../../coordination/reviews/M-014-freeze.json)包含10个run、源码、账本、失败及归档 |
| 首次E1 MODEL_RUN.md（旧归档快照） | d4cef9d2c755ecf55c0ed0c5f3ae76d90f734eb63a41fd54912d26a08beaf213；对应首次读取，不是当前报告hash |
| 08 summary / process | df95bc4b3715dab6b444ff07fa9005acc62fffc98f43e7cfa01a1e6fc81749df / 90087d7014f273e751a1d2e05f05fa852813768aaefcd38a04c0df9b5a530295；选定冻结记录核对 |
| 归档manifest | 532dd1cef8aca97b6e4ec180fe77b27db6e9687455eb9ab6d8a4d0a0f6b3d6c2 |
| 归档verification | 672e4cd0611705e52fe2e756663b1ed89acaddc3cd431566e84df98c59415813 |
| E2 VALIDATION.md | 3945878e9745e0ebd182ee42a0e19cbce97f1963780d1b4b707afff11017e279；M通知冻结后D匹配读取 |
| E2自动核验 / 人工复核 | 8230e2a2374631de4d3130c79c52cd19b258751a5f7b3878bd7b46b88316acf4 / 0491ae4b8381a17875330414de74dbf46ca100b515a346aa973ee2ccbe958365 |
| E2 17文件归档manifest | 70327fecbd2e1f1bfb7f61555d1d06a74fb755babeaf02ea1bf82ee7474c2b07 |

本报告由D做文档整合与选定冻结记录的只读核对，执行由E1完成、独立核验由E2完成；D本轮模型/下载/训练/仿真均0。后续审查与验收入口见[E2-013](../../coordination/tasks/E2-013.md)、[C-015](../../coordination/tasks/C-015.md)、[M-014](../../coordination/tasks/M-014.md)，状态以实时主卡为准。

## 7. 恢复阶段独立核验与最终交审

M确认E2恢复阶段completed/review后，D匹配读取新报告与[源码人工复核](../../simulation/edge_agent_validation/SOURCE_REVIEW_RESTART.md)。E2第2次正式核验退出0，[自动结果](../../simulation/outputs/E2-013/20261028-02-user-approved-restart/validation.json)中1519项记录一致性检查通过、失败0；994项E1冻结指纹执行前后相符，覆盖15个run。两次正式核验额度2/2已用完，1519及此前510均为记录检查数，不能合并成模型样本。

E2核对唯一用户批准恢复、新增一次预检、原ledger字节前缀、累计4worker/3生成与原预算；重核旧296项E1归档、新208项增量及旧17项E2归档。12↔11、14↔13源码版本对应，保存的37项工程检查未重跑；不加载模型、不重读2GB权重、不重新枚举全机进程。

独立复核确认三份原文、两输入像素/私有上下文与实际512×512张量对应；红/蓝颜色词正确，#FF0000仍按原主评分失败，三次严格JSON与合法工具引用均未通过。真实CUDA/FP16加载和生成已有实证，资源与时延按测量范围解释。未发现阻断性的授权、预算或证据矛盾，A0整体仍未通过，下一卡处理工具协议及输出适配。

新E2证据保存在[19文件增量归档](../../simulation/results/2026-10-28-E2-013-a0-validation/restart-20261028/ARCHIVE_MANIFEST.json)，708,421 byte，原根归档/首次输出不改。D逐项核19份副本的长度及SHA相符；未重跑核验器，也未将E2全量994项核对写成D自己的执行。

| 新增冻结输入 | SHA-256 |
|---|---|
| E2 VALIDATION.md | 9f19a4640c91c907d9b3bd140e234d1971d9b902087ffb6d9fadc3bca34cc25b |
| 第二次validation.json | 6616befc38fa75a634951e26d560de44043e553262b0eb739f82d91c0c22ec88 |
| SOURCE_REVIEW_RESTART.md | f514645113cc6df8d732409593ad98aaacb9a0f6173bec6355486891794bbf95 |
| E2增量ARCHIVE_MANIFEST.json | 49d79bcfc17da1a5349551cabb6837174b60529a8724ed78cef3bc564c0536de |

D据上述冻结完成报告及总览整合，交review停写，等待C-015独立审查与M验收；不自行关闭任务或增加实验。
