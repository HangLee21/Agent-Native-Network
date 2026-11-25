# E1-012：A0有监测加载尝试与交接

更新：2026-10-28，Asia/Shanghai。负责人E1；有界执行结束后交review，待E2/C独立核验、M验收。

本轮完成独立任务入口、累计预算与资源监测检查，并实际启动1次模型worker；A0未完成，生成started/completed均0。worker在33.203秒后触发低RAM保护，最后记录仍为`loading`，没有模型加载完成、图像张量或生成结果。保护停止后没有重试。

## 实际执行与资源证据

第一次正式预检在21:22:23（UTC 13:22:23）记录空闲RAM 1,939,304,448字节（1.806GiB），低于原2GiB门槛；显存4621MiB。控制器在模型校验和worker启动前停止，03目录原样保留。M随后在主卡明确授权新配置：直接GPU加载、FP16、low_cpu_mem_usage=True，父进程每不长于0.5秒监测系统RAM；仅此模式将启动门槛改为1.5GiB，低于512MiB或监测失效即停止本卡worker，禁止自动重试。调用和时间预算没有增加。

第二次也是最后一次正式预检在21:28:30通过：RAM 1,899,212,800字节（1.769GiB），显存4610MiB；配置变更说明、新主卡/源码/配置快照均保存在08目录。13项模型资产身份核验通过后生成两张输入，21:28:34启动worker。父进程采样128次，最大相邻间隔0.266秒；21:29:07最后采样可用RAM为412,577,792字节（约393.5MiB），低于512MiB，记录`low_system_ram`并等待worker结束。系统可用RAM曲线包含全机并发变化，不能把全部下降归因于该worker，也不是worker进程峰值RAM。

| 项目 | 结果 | 证据目录（均位于simulation/outputs/E1-012） |
|---|---|---|
| 初版入口回归 | 29项通过 | `20261028-01-scope-checks/` |
| 增加启动RAM保护后的回归 | 29项通过 | `20261028-02-scope-checks/` |
| 原门槛正式预检 | 受阻；worker 0、前向0 | `20261028-03-A0/` |
| 修订前检查 | 30项通过 | `20261028-04-final-checks/` |
| 已安装加载实现静态核查 | 7份源码/元数据摘要及摘录 | `20261028-05-static-loader-check/` |
| 监测逻辑初检 | 34项通过 | `20261028-06-monitor-checks/` |
| 最终代码检查 | 35项通过，失败0、错误0 | `20261028-07-monitor-final-checks/` |
| 有监测A0 | 1次worker，33.203秒；低RAM保护停止；前向0 | `20261028-08-A0-monitored/` |
| 证据辅助检查失败 | 默认GBK读取UTF-8账本失败；无模型调用 | `20261028-09-final-audit/failure.txt` |
| 修正后的最终证据核对 | 源码/配置/账本/曲线一致 | `20261028-10-final-audit/result.json` |

最终35项含8项任务边界/预算/评分与资源门槛检查、5项父进程监测及保护停止后禁止重启检查、16项原有因果运行时检查、6项来源身份检查。监测单测使用受控子进程替身，不属于真实模型调用；08另有一次真实启动及RAM曲线。多组回归不是独立模型实验。

全任务账本为`data/agent_native/E1-012/worker_ledger.jsonl`：2次formal_preflight（首失败、次通过）、1次worker_reserved及finished。worker启动1、生成started 0、completed 0、worker墙时33.203秒、提示修订0；下载/训练/新网络仿真均0。

## 冻结入口与预算

新控制器为`simulation/edge_agent_entry/a0_task.py`。`common.new_run`新增显式任务作用域，默认E1-010行为保留；新入口不能写入旧输出根。主卡须为running并含本卡M检查点，D来源锁SHA须匹配。模型和解释器固定为`data/agent_native/E1-010/model/`及`data/agent_native/E1-010/env/Scripts/python.exe`，只读复用；旧任务卡hash与旧ledger不用于新预算。

最多4次worker启动（失败计入），每次最多256新token/180秒，累计worker墙时720秒。先保留名额再启动，中断未结算启动按全部保留时间计费。正式预检最多两次，第二次沿M明确修订保存配置变化；通过后的`--resume`也不能绕过持久记录的监测保护停止。每次启动前瞬时核RAM，worker加载前核显存；父进程监测仅发生在本卡有界worker执行期间，没有后台等待资源。

两张64×64红/蓝纯色PNG使用中性文件名，提示不含期望颜色，评估器标签不进入worker规格或文本。入口设计为两个独立worker、每次单图、各自私有上下文串行执行；视觉答案、严格JSON工具格式和引用合法性分别评分。最多一次提示修订，所有重试继续占预算。本次仅第一个上下文启动，两个上下文未完成，不能作为实际视觉识别或格式兼容结果。

`model_worker.py`增加可选直接CUDA加载、加载耗时、设备/dtype、加载阶段GPU峰值记录；默认旧加载路径保留。生成峰值在加载/预处理后重置统计，包含常驻模型与生成阶段分配，不能当成完整加载峰值。**本次没有取得任何加载/生成GPU峰值，也没有processor张量记录。**

worker只留下初始`loading`检查点，未写出versions、model_loaded、prepared或generating检查点。加载是否完成无证据，不能把33.203秒总墙时称为模型加载时延；不能把未生成回答时评分器的默认false解读为一次实际视觉误判。不能宣称A0通过、A1协作通过或A/B已耦合。

## 来源、版本与执行快照

05为启动前只读静态核查，未导入torch、未启动worker、未增加预检。隔离环境`pyvenv.cfg`设置`include-system-site-packages=true`，基础路径`C:/environment/python3.11`；隔离目录Transformers元数据4.51.3，基础环境Accelerate元数据0.32.1，满足本地声明的最低版本0.26.0。源码指纹与行号摘录保存于05。

本地Transformers `modeling_utils.py:3721-3733`在普通非DeepSpeed路径使用`no_init_weights()`与`init_empty_weights()`创建meta参数；`:3991`接受并取出`low_cpu_mem_usage`；`:4135-4141`在使用`device_map`时检查Accelerate。`:738-753`将根设备映射`{'':'cuda:0'}`用于`safetensors.safe_open(..., device=tensor_device)`，`:766-800`逐参数取片、转换dtype并按设备映射装载。其`integrations/accelerate.py:16-23,39-70`实现meta初始化。基础Accelerate `big_modeling.py:480-495`支持单设备dispatch并设置`hf_device_map`。这些证实已安装实现包含直接GPU加载路径，不保证本模型在当前主存余量下加载完成；08的最后状态也不能定位到具体导入、处理器或权重装载子阶段。

控制器为仓库`.venv`的Python 3.11.5；预检中的torch2.3.1+cu121、Transformers4.42.3等是控制器库存，不能当作隔离worker依赖快照。worker解释器路径已写入08结果，但未完成版本记录；静态元数据和历史导入记录不能替代本次未完成的运行时快照。

模型固定为`HuggingFaceTB/SmolVLM2-500M-Video-Instruct`，revision `7b375e1b73b11138ff12fe22c8f2822d8fe03467`；D来源锁`research/agent_native_network/preparation_20261028/SOURCE_LOCK.json`的SHA256为`139330b3c5ba0468b06999e0b238a999c21cd6d10f1f106fe03b21d2601503c1`。08运行重新核验全部13项白名单资产，权重SHA256为`b9bfd456c9472c0acd5719d6e514c4b859891af205ee1a736552fd3497b8b0c3`；SHA未知的普通Git文件沿可信Git blob身份核验，不用LFS指针hash比对权重正文。

Git基准`7f92debd36310a7d5e37ef52d23c019138284cdd`。保留M/E2并发文件，没有Git写操作。03保存原执行版本，没有改写原manifest。最终Python/JSON代码对应07检查及08执行源码快照；10核对二者摘要一致、当前源码匹配、08配置摘要正确。README在执行后补充监测模式说明，归档保留最终文件。05/09/10为只读证据辅助目录，其公共manifest在辅助检查后补记并明确说明，未知时刻/命令/依赖未猜填。

## 归档与交接

归档目录`simulation/results/2026-10-28-E1-012-a0/`，`ARCHIVE_MANIFEST.json`逐项记录来源相对路径、归档路径、字节数和SHA256，纳入本轮原始成功/受阻/失败记录、源码与配置快照、账本和本报告；不含模型/环境。归档核验见`ARCHIVE_VERIFICATION.json`。两份旧E1-010归档manifest摘要仍为`89c819d5b24537561e2fefdc4236abc7d6b06e47e251d5160089dd8cf4107c18`、`2aae3a4ae64505b794d1f9c8405d491f47454d2bad1bbd971087e4246947cab2`；本轮只核这些manifest字节，未逐项重验旧归档全部内容。

父进程记录worker PID 49936已wait回收（`worker_reaped=true`）；控制器已同步退出，随后按worker和控制器PID查询均未发现存活进程。全机CIM枚举被环境拒绝，不能宣称已检查全机无其他研究进程。

本卡两次正式预检已用完。虽然名额尚余3次、时间未用满，但保护停止已禁止自动重试，E1交review停写。恢复需要增加可用RAM余量，或另行验证更轻的运行时；没有测出完整加载所需空闲RAM或GPU峰值，不给固定容量成功保证。下一步由E2/C核验证据、M决定后续方案，不自动新建预检、等待资源或切换模型/设备。
