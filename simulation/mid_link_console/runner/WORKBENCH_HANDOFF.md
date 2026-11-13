# M-024 快照与编辑真正进入运行

E2无需改H原始快照，也不能将H编译出的场景再交旧routing/custom编译器。新入口：

```python
from simulation.mid_link_console.runner.workbench import run_pair, execute_compiled
result = run_pair(measured_settings, new_output, algorithm="latency_aware")
# 如果后端已调用H规范化/编译，可直接使用：
result = execute_compiled(compiled_scenario, new_output,
    algorithm="compare_latency", settings=normalized_settings, source=snapshot_provenance)
```

`run_pair`直接使用H `settings.measured.normalize_settings/compile_scenario`；已有M022/M023函数不会重建覆盖实测基线。输出settings.json/scenario.json由同一输入取得，不能使用当前草稿重画旧结果。`execute_compiled`是高级接口，调用者负责传相符的H归一化设置及场景；实际边执行值以scenario.json为准。CLI沿原--settings/--output/--cancel-file，新增--algorithm（独立于H设置schema）和可选服务端--compiled-scenario。

运行环境也由MeasuredRoutingEngine/MeasuredMIDEngine直接调用H measured.state_at，不只编译时取快照；旧pair/routing模块原样保留。H状态求值目前委托同一底层函数，明确接provider不会改变已有新结果；未来快照环境扩展也不会走旧默认。

算法值与**实际执行**：

| algorithm | executed_arms | 意义 |
|---|---|---|
| fixed | fixed | 只运行固定初始链 |
| latency_aware | latency_aware | 只运行按延迟观测重规划 |
| compare_latency | fixed, latency_aware | 同快照/种子的配对比较 |
| mid | adaptive | 只运行原MID概率转发表 |
| compare_mid | fixed, adaptive | 原MID固定首表对照原MID重规划 |

INDEX记录algorithm、selection_semantics=actual_arms_executed、execution_mode、executed_arms，不会“运行两者却暗示只执行选中算法”。E2/D须用这些标签，MID fixed是固定概率首表，不是固定简单链。当前MID legacy入口只支持A↔B双向/不限跳数，其它组合在创建run前明确UnsupportedCombination；不得降跳或替换成时延策略并仍称MID。后续若扩MID端点须独立实现，不能仅改下拉框。

时延感知/固定链使用原RoutingEngine，支持src/dst、严格k/不限、单/双向及锁定整包链。实测服务/PDR逐方向基线及用户禁边/时延等都从H的编译场景读取；没有8.192/4.096kbps的重新硬编码。真实来源、采集时间/样本量和未知时延值应由H source metadata随图显示。服务率是当次注入负载下的历史观测，不是当前链路物理容量。时延null不能从跨板时钟推算，模型10ms要保持“模型值”标识。

`run_pair`用于8767软件工作台，没有串口/8766请求；硬件代理与实板约束由E2/H独立实施。编辑成功率/时延并不改变实板信道，不能将模拟参数当成对实板强制设置。运行前选好算法；恢复实测默认仅取H新默认对象，不触发run，也不覆盖原证据/旧结果。

验证先交`simulation/outputs/E1-022/20261108-01-baseline-integration/PROOF.json`：直接从H006真实2560bit/s服务量构造的接入fixture，不是H011正式快照，未测时延10ms仅模型。scenario.json是该程序化fixture的实际输入；after场景由程序改编译图，勿拿旧settings字段做正式H界面恢复验收。before为ABC，after断BC并加DC750ms后时延臂实际AEC，固定仍ABC；计数120→80及120→117。所有服务开始事件确实2560bit/s。单独fixed只生成一臂，严格跳数MID拒绝；这些是新软件运行，不是浏览器或硬件通过。

E2接入时view需识别measured schema或INDEX routing特征，按algorithm正确标注/提取hop_rx和actual_path；不能因schema不是旧mid.routing.settings.v1就错误当MID。服务端worker新增分派measured→本入口，原schema继续旧入口。源快照/图复位与网页同页交互由H/E2/D承担，E1等待正式H接口后补一次正常入口证明，不重复M023旧用例。

正式H measured入口已实际运行：`simulation/outputs/E1-022/20261108-02-official-measured/`含actual-default、before-2hop、after-edits、original-MID及PROOF。默认单latency_aware只120/120且走A-C；2跳编辑前两臂120/120走ABC，BC断+DC/CD模型750ms后固定80/120、新117/120且实际AEC。原MID支持组合用A↔B/both/不限跳数实际235/240，未伪装为简单路径。来源snapshot_id=H006-20261107-20directions-10pps32B，初始发送事件使用2560bps，时延仍模型值，H原快照不变。

8767正常API也已完成两次新作业：编辑前`20261108-133938-37cb4d1d6202`，编辑后`20261108-133940-780cb3093374`，均completed。读取服务实际view数据确认前ABC，后latency_aware实际AEC、fixed该窗无目的接收；服务选择latency_aware明确为paired_run_selected_arm_display（两臂都执行、选看一臂），与底层单臂选项不混淆。结果地址`/results/<id>/`；E1验证记录`simulation/outputs/E1-022/20261108-03-normal-api/{PROOF,before-job,after-job,reset}.json`。reset回到H默认，未触发实板。E1只验证正常HTTP/API，不冒称浏览器点选/同页UI已通过，D继续浏览器验收；E2无需再为这两组重跑求解。
