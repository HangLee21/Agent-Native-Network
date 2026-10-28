# E1-010入口

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
