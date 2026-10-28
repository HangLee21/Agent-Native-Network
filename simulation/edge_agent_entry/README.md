# 本地模型与fixture入口

E1-012使用独立入口和累计账本，先读实时主卡 `coordination/tasks/E1-012.md`：

```powershell
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.test_task_scope --output simulation/outputs/E1-012/<new-check-run>
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.a0_task --output simulation/outputs/E1-012/<new-A0-run>
```

新入口只读复用E1-010的model/env，固定D来源锁，写入E1-012新目录。最多4次worker启动（失败计入）、每次256新token/180秒、累计720秒；未完成reservation按全部保留时间计费，不删除账本重置。正式预检最多两次，首失败后须有明确资源变化，通过 `--resource-change-note` 留证；失败时不得用 `--resume` 越过。`--resume`仅在已有通过预检时供有界运行时修复重入，仍沿同一账本计费。启动前另做瞬时RAM门槛检查，worker加载前核显存，均不轮询。

两个64×64纯色图使用中性文件名，期望颜色只在评估器文件中，模型文本不含颜色答案。每次独立进程与私有上下文，只给一张图；视觉识别、JSON格式和引用合法性分别评分。最多一次提示修订；direct CUDA加载与实际processor张量是否可用须以运行证据判断。当前执行证据见 `research/agent_native_network/a0_20261028/MODEL_RUN.md`。

M在03失败后新增有监测低RAM模式：`--monitored-direct-cuda`须匹配实时主卡修订，使用直接CUDA加载、FP16及低CPU加载，启动RAM门槛1.5GiB；默认模式仍2GiB。父进程按0.25秒间隔记录系统可用RAM，低于512MiB或监测不可用时仅终止并等待自身worker。保护停止进入持久账本，阻止后续自动启动；不因剩余名额继续运行。显存门槛仍2.5GiB。实际采样间隔和保护结果查`ram_curve.jsonl`及`process.json`，配置间隔不替代观测间隔。

以下保留E1-010历史入口说明及预算，不能用于扩大新任务范围。

资源改善后用户明确批准恢复时，E1-012主卡新增了本次人工授权，`--user-approved-restart --monitored-direct-cuda`仅可沿这一主卡记录使用一次，新增一次启动检查，原累计worker预算与保护历史不清零。普通`--resume`不能自行解除保护；新的保护停止仍会禁止启动。`--diagnostic-input 1 --resume --monitored-direct-cuda`可在同一预算、同一提示版本下只记录尚缺的固定蓝图，不把“已执行两个输入”当成两个输入都通过验收。具体执行以各次源码快照为准。

本次实测：64×64原始PNG经processor生成`pixel_values=[1,1,3,512,512]`，`do_resize=False`没有消除内部视觉编码适配步骤，不能称为64×64张量推理。真实加载和生成已完成，但严格JSON工具格式未通过，详见MODEL_RUN报告。

先读 `coordination/tasks/E1-010.md`。本目录包含离线fixture和待实际验证的SmolVLM本地适配器；二者不会相互回退。

离线验证（每次换新输出目录）：

```powershell
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.test_runtime --output simulation/outputs/E1-010/<new-check-run>
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.cli --output simulation/outputs/E1-010/<new-fixture-run>
```

`fixture_config.json`有明确脚本动作和0.25秒工程交付延迟，只用于检查因果隔离、完整到达、序列化和费用记录。合成图像是标准库生成的64×64纯色PNG，不是真实场景。图像私有输入大小与发送文本报文大小分别记；引用本地图像不等于把PNG发送到对端。没有无线、路由或自主智能体行为结论。

`Runtime`通过复制的单节点context向backend传递数据，不暴露全局消息队列、其他节点输入或评估器。消息完整到达才进入收件箱，远端证据须先consume才能在finish中引用。这个消费事件表示显式工具选择，不证明内容被模型正确理解。静态fixture不能证明真实模型自主性；A0也只验证加载、视觉输入、输出格式。

模型A0入口是 `python -B -m simulation.edge_agent_entry.a0 --config <task-local-config> --output <new-output>`。必须先有D冻结来源和M主卡检查点，再取得固定文件及隔离覆盖环境；当前命令本身不会下载。配置需含repo_id、40位source_revision、SOURCE_LOCK哈希、实时任务卡哈希、M检查点原文、task-local python/model_dir、模型逐文件SHA-256、minimum_free_ram_bytes及budget。SHA仅核版本，不能替代授权。

单次子进程含加载在内最长180秒，max_new_tokens≤128，任务内累计最多4次调用，累计worker墙时≤720秒；首次失败即停，重跑仍计task-local attempt ledger。每次A0调用为独立上下文，生成工具只解析和权限检查，不自动驱动下一模型；真实协作留A1。低内存门槛为至少2GiB空闲RAM/2.5GiB空闲显存，是保守执行门槛，不是已测模型需求。禁止为了过门槛结束无关进程。

共享 `.venv` 不可修改。`a0_requirements.txt`的六项覆盖包已安装到本卡独立环境，只读复用既有torch/torchvision，没有下载新torch轮子。`acquire.py`提供一次有界取得：官方PyPI固定版本、D模型白名单、逐文件大小/可信摘要、2.5GB累计下载及600秒准备上限；拒绝重复取得目录。它的导入检查只证明模型API可导入，不证明模型加载。实际下载、资源及生成状态以MODEL_ENTRY和manifest为准。

来源校验同时使用D锁定的可信身份：有发布SHA-256时核内容SHA；5项SHA未知的普通Git tokenizer文件另核 `SHA1("blob "+文件长度+NUL+文件原字节)`。LFS权重的Git blob是指针身份，不用于比对权重正文。针对性离线检查为 `python -B -m simulation.edge_agent_entry.test_source_identity --output simulation/outputs/E1-010/<new-source-check>`，不下载模型、不调用A0。

所有运行创建公共manifest、源码快照、配置、退出状态和失败。目录已存在或越出E1-010输出根时拒绝。更详细的实际硬件、输出和来源状态见 `research/agent_native_network/preparation_20261028/MODEL_ENTRY.md`。
