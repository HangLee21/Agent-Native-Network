# E1-010：P2模型与事件入口准备

2026-10-28，E1独立聊天 `01a16824-294e-7eb2-85eb-d98b7a8748f1`。工作副本 `D:\Multi-Agent Network`，接手分支 `codex/baseline-reproduction-20261023`，HEAD `72855ef8dbde54a090e67c17c5af9ae1e23c5d29`。保留M及其他角色的现有修改；仅写本任务卡分配范围，无Git写操作、子代理、新聊天或跨聊天发送。

## 当前取得的结果

已经实现离线P2事件入口，完成16项检查、双节点fixture及6项来源身份检查。首次A0资源预检未过；M在网络构建结束后另授权一次续行，第二次正式预检通过，随后完成隔离依赖安装、API导入及13项模型文件取得。准备用时556.766秒、累计下载2,048,806,781 byte，均在原额度内。A0入口随后发现空闲RAM回落，在worker启动前停止。真实生成调用、训练和无线仿真仍为0，未验证真实模型加载、视觉输出或协作。

fixture是固定脚本，不作模型自主行为证据。两节点各有独立私有文本和64×64合成纯色PNG，通过request/response形成2条报文，5次脚本调用、完整到达2次、显式消费1次，总实际序列化UTF-8 payload为411 byte。没有无线头部、逐跳、MAC重试或空口时间，这411 byte不能当实网成本。图像编码字节分别保存；响应引用图像时仅发送文本与引用，不把未发送的PNG字节计入报文。

## 本机盘点和执行条件

早期证据为 `simulation/outputs/E1-010/20261028-04-final-fixture/inventory.json`；M检查点后的正式预检见 `20261028-09-A0-preflight/inventory.json`、`preflight.json`，实际时刻见文件及manifest。

| 项目 | 本轮实测 |
|---|---|
| CPU | AMD64 Family 25 Model 116 Stepping 1，16逻辑CPU；未通过受限CIM取得营销型号/物理核心数 |
| RAM | 16,342,147,072 byte物理内存；09首次预检1,960,558,592 byte未过；12续行预检2,560,176,128 byte通过；14加载前检查1,996,738,560 byte又低于2GiB门槛 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU，8188 MiB总显存；初测4865 MiB空闲；正式预检6,207,569,920 byte（约5.781GiB）空闲，通过2.5GiB门槛；驱动576.02 |
| 解释器 | 仓库`.venv/Scripts/python.exe`，Python3.11.5；pyvenv.cfg启用system-site-packages |
| 已有包元数据 | torch2.3.1+cu121、transformers4.42.3、Pillow10.4.0、hub0.23.4、safetensors0.4.3；另查accelerate0.32.1、torchvision0.18.1+cu121 |
| 可用空间 | 初测D盘约128.8GB空闲；不能代替实际下载预算 |
| CIM查询 | CPU/OS/GPU三项均返回“无法从客户端中访问CIM资源”；已改用环境CPU标识、标准库Windows内存API和nvidia-smi，不宣称CIM通过 |

上表的包版本主要来自importlib.metadata；未把“有安装记录”写成模型可用。没有修改共享`.venv`、系统包或驱动，没有结束其他进程。A0前须重新盘点，当前低空闲RAM不支持直接宣布安全加载。

## 实现和事件边界

| 文件 | 已实现内容 | 尚未覆盖 |
|---|---|---|
| `simulation/edge_agent_entry/runtime.py` | 私有输入、独立context/收件箱、显式生成/发送/完整到达/消费/结束；严格JSON工具检查；调用/墙时/字节预算；失败原文记录 | 不实现无线、多跳、发现、版本迁移、取消/可靠重试、完整架构ANI |
| `fixture_config.json`、`cli.py` | 明确脚本backend、合成PNG编码及IDAT解码、UTF-8实际字节、SHA-256、事件JSONL、运行配置及失败 | 不识别真实场景、不给视觉正确性或自主协作结论 |
| `event_schema.json` | 固定v1外层字段、事件类型、父事件ID、两种backend标签、逻辑与墙时时钟 | details为事件类型扩展字典，尚未逐工具建立完整JSON Schema；本轮只测必需键/类型集合与父事件顺序，未用完整外部JSON Schema验证器 |
| `model_backend.py`、`model_worker.py` | 单节点可见context转提示，局部PNG输入；只读local_files_only、禁远程代码；128token/180秒进程上限，stdout/result/版本/内存日志 | 未实际导入新运行时或加载权重；不能据此声称模型兼容或格式可靠 |
| `a0.py` | D来源锁/M主卡快照核对、逐文件流式哈希、资源门槛、跨重跑最多4次attempt账本、总墙时、首次失败停止 | 只有M同卡检查点和D冻结来源后可执行；哈希核对不能自行产生授权 |
| `preflight.py` | 检查M检查点、D锁hash与13文件总量，重新盘点RAM/VRAM；不足则保存失败并在取得前停止 | 不下载、不解析完整轮子依赖、不尝试加载；资源门槛不是实测峰值内存 |
| `acquire.py` | 一次官方PyPI固定版本解析/下载和隔离覆盖安装，D白名单取得/摘要核验，600秒/2.5GB上限，逐文件计量与失败保存 | 不重试、不取得整仓/ONNX或新torch；本轮无模型生成；完整取得不证明实际加载 |
| `common.py`、`test_runtime.py` | 独占新输出、公共manifest、源码快照、只读盘点；16项隔离/预算/边界检查 | 没有物理设备隔离或恶意Python backend安全沙箱；backend边界用于正确性而非对抗不可信代码 |

本地合成图像记录 `provenance=generated_solid_color_compatibility_fixture`、实际PNG长度和SHA-256。外部证据引用必须是本地输入或已完整到达的消息ID；后端不能借日志取得全局私有内容。请求/回复/body在实际序列化完成后计费。fixture采用逻辑时钟，0.25秒是工程假定，不是实测网络时延。真实A0独立调用只验证格式，不把固定轮转包装成模型自行选的交互。

16项检查覆盖：私有上下文隔离；backend修改副本不污染节点状态；到达前不可响应/消费；父事件链与重复消费；非法远端引用和原始输出保存；调用/字节/墙时预算；UTF-8长度/哈希；过期不可见；非法JSON无暗中修复；事件键和因果父序；finish前显式consume；输出范围和拒绝覆盖；模型子进程失败不回退fixture；模型超时与调用上限。模型子进程两项用标准库mock，实际模型调用为0。

## 输出和失败记录

所有目录位于 `simulation/outputs/E1-010/`，新入口拒绝覆盖；每个运行均保存公共manifest字段、源码/配置快照及状态。未生成历史结果替代品。采纳归档由M后续安排。

| run-id | 实际状态和证据 |
|---|---|
| `20261028-01-offline-checks` | 首版14/14通过，`checks.txt`、`result.json`、manifest及当时源码 |
| `20261028-02-fixture` | 首版双节点fixture通过；输入PNG、input_manifest、events、result、inventory及源码 |
| `20261028-03-final-checks` | 加入模型失败/超时边界后16/16通过，无真实模型前向 |
| `20261028-04-final-fixture` | 对应当前离线入口的双节点fixture；5次脚本调用、2报文、411 byte、消费1 |
| `20261028-05-command-preflight-failure` | 构造负例的临时命令误用默认GBK读UTF-8配置，随后缺配置失败；没有进入runtime。保存准确原因及修正，不计作入口检查通过 |
| `20261028-06-expected-guard-failure` | 修正临时命令编码后，故意引用未到达的`n1:local`；入口按预期失败，退出1。保存failure traceback、原输出事件、result；生成/发送/消费均0 |
| `20261028-07-freeze-checks` | 修正覆盖环境账本的UTF-8读取并核真实前向计数后，16/16通过；源码快照保留 |
| `20261028-08-freeze-fixture` | 同一双节点fixture再次完成；用于最终离线源码版本核对，无新增模型样本 |
| `20261028-09-A0-preflight` | M授权后正式预检：空闲RAM不足，`blocked_resource_preflight`，入口退出码2；保存M主卡/来源锁快照、库存、依赖计划及failure；没有模型调用或文件下载 |
| `20261028-10-final-static` | 最终9份Python源码AST解析通过，成功fixture的19事件父引用可重建，10份公共manifest字段齐全；保存最终代码哈希和源码快照。清单字段`runs_at_check_time`为检查当时状态，当前静态检查自身manifest当时仍为running，完成状态以它最终manifest为准 |
| `20261028-11-source-identity-fix` | C-013初审P2修复后的6项针对性检查全部通过；含5项冻结tokenizer身份的同大小替换/自报SHA攻击检查，无下载/推理 |
| `20261028-12-A0-resume-preflight` | M在构建结束后授权的唯一新正式预检通过；RAM2,560,176,128 byte、VRAM6,393,167,872 byte，尚未取得或前向 |
| `20261028-13-acquisition` | 取得13项模型文件、六项增量包及元数据，总下载2,048,806,781 byte、556.766秒；隔离安装及模型API导入成功，所有SHA已知文件/五项Git blob核验通过 |
| `20261028-14-A0-local-model` | 来源/文件校验后，加载前RAM降为1,996,738,560 byte，`blocked_before_forward`、退出1；未创建worker调用目录或attempt账本，真实生成0 |
| `20261028-15-continuation-verification` | 核已取得记录/预算、独立覆盖包与原torch加载路径、原219归档完整性；没有重新资源盘点或加载模型 |

第05项是临时命令失误；正式CLI原本已显式读UTF-8，未因此修改研究入口。第06项是有意的保护检查，不能把其失败状态重写为正常任务成功，也不进入模型行为成功率。

复现命令（尖括号须换成新目录名，禁止复用已有输出）：

```powershell
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.test_runtime --output simulation/outputs/E1-010/<new-checks>
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.cli --output simulation/outputs/E1-010/<new-fixture>
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.cli --config simulation/edge_agent_entry/invalid_fixture_config.json --output simulation/outputs/E1-010/<new-expected-failure>
```

## 真实A0的来源、环境和待检查点

当前只使用官方[SmolVLM2模型卡](https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct/raw/main/README.md)及[Transformers4.51.3 SmolVLM文档](https://huggingface.co/docs/transformers/v4.51.3/en/model_doc/smolvlm)核对接口。官方示例的图像输入、AutoProcessor/AutoModelForImageTextToText是实现参考，不代表本机兼容。本适配选eager attention、fp16、禁图像自动放大，避开未安装flash-attn；真实可行性尚待验证。

D首阶段已交review停写；本窗口随后只读其冻结 `SOURCE_LOCK.json` 和 `SOURCES_AND_LICENSES.md`。模型revision为 `7b375e1b73b11138ff12fe22c8f2822d8fe03467`，锁文件SHA-256为 `139330b3c5ba0468b06999e0b238a999c21cd6d10f1f106fe03b21d2601503c1`。13文件合计2,034,856,030 byte，权重发布方SHA-256为 `b9bfd456c9472c0acd5719d6e514c4b859891af205ee1a736552fd3497b8b0c3`；不是E1本地权重复算结果。模型卡声明checkpoint为Apache-2.0，独立LICENSE文件缺失的事实及边界沿D记录，不自动推成许可阻塞。

09预检因RAM未过停止，保留当时下载0和仅有依赖计划的事实。随后M明确授权构建结束后续行，12预检通过，13实际取得13模型文件和六项增量包；模型合计2,034,856,030 byte，依赖包体及官方PyPI元数据合计13,950,751 byte，累计2,048,806,781 byte，尚余451,193,219 byte下载额度。没有重下torch、ONNX或数据集，没有多轮下载重试。

本轮实际建立 `data/agent_native/E1-010/env`，以`--system-site-packages`只读复用已有torch2.3.1+cu121、torchvision0.18.1+cu121；pip仅写新环境、本卡缓存及临时目录。覆盖版本为transformers4.51.3、tokenizers0.21.1、hub0.30.2、safetensors0.5.3、num2words0.5.14、docopt0.6.2，已实际导入torch/transformers和模型API。15的模块路径证据显示torch来自原系统site-packages，transformers/tokenizers/safetensors来自新环境；pip日志明确没有卸载环境外旧包。不下载数据集，合成PNG不作为真实感知证据。

取得时逐文件保存官方固定URL、长度、SHA与所选轮子元数据；普通Git文件另外核D的blob身份。权重本地流式SHA与D发布值匹配；13模型文件的本地SHA在 `13-acquisition/model_files_verified.json`。源文件位于本卡data/model，不纳入结果归档。13的导入检查触发了原环境可见的TensorFlow可选路径，未用于模型推理；后续PyTorch worker显式设置USE_TF=0/USE_FLAX=0。六包安装及模型API导入通过不代表整个模型加载通过。

本轮已在data目录保存实际 `a0_config.json`，含固定repo/revision、来源锁hash、执行当时任务卡hash及M检查点原文、13项本地哈希和新环境/模型路径。取得13和A0入口14各保存配置/主卡快照。执行期间未为回填而改主卡，未出现hash自我阻塞；交review后的主卡变化不回写旧快照。以后恢复应由M重新检查资源并建立新的执行快照，而不把旧hash强行当当前状态。

本次已执行的预检命令为：

```powershell
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.preflight --source-lock-sha256 139330b3c5ba0468b06999e0b238a999c21cd6d10f1f106fe03b21d2601503c1 --output simulation/outputs/E1-010/20261028-09-A0-preflight
```

安全门槛暂取空闲RAM≥2GiB、空闲显存≥2.5GiB；这是保守的执行门槛，未测定精确模型内存需求。加载用safetensors/low_cpu_mem_usage，权重哈希按1MiB流读取，不把2GB权重一次读入RAM。每个worker至多180秒（含加载），一次生成≤128输出token，最多4次、累计≤720秒；失败即停止，不补无限格式重试。下一次A0须重新盘点资源，不为了满足门槛结束无关进程。

区分四个状态：来源已定位≠已取得文件；已取得并匹配hash≠运行时可导入；可导入≠完成一次视觉推理；一次兼容推理/JSON有效≠自主协作或任务质量复现。目前来源、文件取得/身份和隔离模型API导入已经通过；14在加载前资源检查停止，没有生成输出、格式结论或自主协作证据。后续A1/B1/B2/C仍需新卡。

## 交接

离线入口、取得流程、资源检查和元数据核对均已退出，无模型/网络或后台研究进程。14再次受阻于当时不足的空闲RAM，而非许可、hash回填或已证实的模型不兼容。文件和覆盖环境已具备，后续若M授权，只需按新资源/主卡快照恢复本地A0，不重复下载，不自行轮询或降低门槛。C-013复核后由M验收。

## C-013来源校验修复与阶段归档

C初审指出5项tokenizer文件只有冻结Git blob身份，而初版只比大小和配置自报SHA-256，不能阻止同大小替换。现由 `a0.verify_model_file` 在大小/本地SHA核对之外，流式计算普通Git文件的 `SHA1("blob "+十进制字节长度+NUL+原内容)` 并与D锁比对；无可信身份即拒绝。发布方SHA已知的正文（尤其LFS权重）继续核该SHA，不把LFS指针blob拿来核大文件。D锁及既有输出均未改。

6项新检查包括：原始普通blob通过；同大小替换且自报SHA同步改变仍拒绝；对锁中的added_tokens/merges/special_tokens_map/tokenizer/vocab五项逐个拒绝同大小替身；LFS已知内容SHA与指针分开；发布SHA不被自报值替代；缺少可信身份时拒绝。测试只用合成字节，不取得真实tokenizer或模型。命令：

```powershell
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.test_source_identity --output simulation/outputs/E1-010/20261028-11-source-identity-fix
```

M已采纳工程/预检记录作本阶段归档。归档位置为 `simulation/results/2026-10-28-E1-010-model-entry/`：`runs/`保存01–11各运行目录的原字节，含全部成功/失败manifest、配置/源码快照、PNG、事件、检查及预检记录；`entry-source/`是修复后的当前入口源码/配置/说明。`ARCHIVE_MANIFEST.json`逐文件登记源路径、归档路径、byte数及SHA-256，另有各运行成功/失败清单；原manifest不重写，原输出不移除。归档中的scratch为保护检查生成的合成字节，不含实际模型权重或环境。

上述原219文件归档代表C初审修复阶段，保持原字节；随后M另行授权的续行记录12–15另存增量归档和独立映射，不覆盖原映射或原manifest，不归档权重/环境。两阶段的运行/下载状态分别按各自保存记录解释。

续行增量路径为 `simulation/results/2026-10-28-E1-010-model-entry/continuation-20261028-A0/`，独立 `ARCHIVE_MANIFEST.json` 记录12–15原字节、当前源码及父归档manifest的SHA-256。取得模型/依赖在data目录保留，不复制进入结果归档。可复现的已执行命令为：

```powershell
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.preflight --source-lock-sha256 139330b3c5ba0468b06999e0b238a999c21cd6d10f1f106fe03b21d2601503c1 --output simulation/outputs/E1-010/20261028-12-A0-resume-preflight
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.acquire --preflight simulation/outputs/E1-010/20261028-12-A0-resume-preflight/preflight.json --output simulation/outputs/E1-010/20261028-13-acquisition
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.a0 --config data/agent_native/E1-010/a0_config.json --output simulation/outputs/E1-010/20261028-14-A0-local-model
```

这些是执行记录，不是当前可直接重跑的命令：输出已存在、取得目录已存在、主卡回填后hash已变，均应由新检查点生成新输出及配置快照。依赖取得的网络权限由已授权的工具执行通道提供，未发生自动审批拒绝或新增用户确认。
