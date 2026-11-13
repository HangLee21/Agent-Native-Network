# 2026-11-07五板执行入口

H实读标签：`hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json`，结构为`labels`。A=90:da:72:48:a4:f8，B=90:da:72:48:a5:cc，C=90:da:72:48:a4:e0，D=90:da:72:48:a5:20，E=90:da:72:48:a6:98。端口提示不作为身份；DE逻辑标签按实际MAC登记，不猜物理字母。

新增`tools/mid_baseline/validation/five.py`不改旧三板分析器/结果。不要求重验旧包或新审批，统一包由E1交H直接按M授权部署；下面工具仅离线生成命令，原始采集可先行，分析器不得阻塞设备。

## H接入

刷后五板保存本统一build的实际info-A.json至info-E.json（完整mid.serial.v1 command_result，idle、实际MAC/boot），放一个目录。E1交新包及12组实际SOCP资产后运行：

```powershell
python -B tools/mid_baseline/validation/five.py materialize --package <E1统一新package目录> --assets <含INDEX.json的cases目录> --case AB --infos <H五份实际info目录> --labels hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json --run-id <H新run> --output simulation/outputs/H-005/<run>/plan.json
```

函数同CLI：`five.materialize(package, assets, case, infos, run_id, labels, chain=None)`，infos可按实际MAC或A–E索引。新包的build/manifest从该包读取，不再写死package-01；调用包内原bridge/pack，不另造数据协议。不重复遍历旧包hash。INDEX沿E1 ABC格式：cases含case字段；每例目录含network_update.json及solution.json。读取实际SOCP输出，要求五实际MAC/双流/optimal，不能使用合成身份或boot1示例bin。

12例顺序：AB AC AD AE BC BD BE CD CE DE chain_ABCDE chain_BADEC。前十每方向5包=100；两链每方向5包=20，合计120。最小AB并入首例，不重复发。每例实际A boot作为publisher_boot，控制序号按INDEX序号分段（1001+100*case索引开始三份1秒间隔发布），源业务seq由固件生成；若A重启重新读info/物化。一个场景两流，不同时安装20方向。保持每源500ms间隔、16byte不同编号payload、阶段排空1.5秒、stop/final stats动作，单run最多60秒，总12run/720秒；缺失包如实记，不为100%补发/追加run。

`actions`沿原H execute_native结构：所有五板start→A配置→全体config_applied/required_routes→全体baseline stats→双向各5 send→全体stop/状态确认→全体final stats；每command等nonce/ok，异常finally_actions只stop，不新建ACK、自动复位、重试。H需将自己的采集入口参与者/MAC/build/调用替换为该通用输入，不能继续硬编码ABC或旧native.PACKAGE_HASH。不在E2工具打开任何端口。

受控case自动从chain_后缀解析ABCDE或BADEC；也可显式`--chain A-B-C-D-E`。要求实际SOCP配置的八条有向转发边严格匹配双向四跳链，若解不符则明确拒绝，不事后屏蔽gateway。A-C等直连禁边是输入模型逻辑约束，不是RF隔断或覆盖收益。ABC仍对等，两个case内部角色并集覆盖ABCDE。

## 采集与逐跳分析

H先完整记录native.jsonl、各板raw.bin、计划和实际context，schema/nonce/boot/时间窗及base-final stats沿原native合同；context绑定本新包manifest及全部五板覆盖/stop。可直接采集，不等分析代码或文档审查。

```powershell
python -B tools/mid_baseline/validation/five.py audit --plan <实际plan.json> --log <实际native.jsonl> --context <H不可变context.json> --output simulation/outputs/H-005/<run>/five-analysis.json
```

分析先复用端点身份/coverage/计数/stop门控，再按plan.paths逐条核：源tx_submit→第一中继；三个内部节点各有同origin/origin_boot/seq/dst的rx_relay、tx_submit且next_hop为下一节点；目的rx_local。每段原文件/行号进hop_evidence，任一段缺失或身份错配不称完整四跳。源tx_queued不是实际提交，MAC成功不是目的交付。RTT/PHY重试/airtime未知；实际数据到位后E2只分析一次交C/M/D。

## 当前证据与依赖

4项增量synthetic检查通过：12场景120包/160byte配置/实际参数boot编码、两链完整且内部角色并集覆盖五板、逐项缺源提交或内部接收/提交不能判通过、错误SOCP路径不偷偷改表。01轮测试因Windows路径含MAC冒号错误保留，改E2测试目录名后02通过；兼容H实际labels结构后03最终通过。没有重跑三板、求解器或固件套件，没有RF值。

E1真实资产现已到位并通过一次物化兼容检查：统一包`.local/mid/E1-016/package-03`（build mid-v1-a9a060af8512b126b7a8679d85bf5070803bb5b9796b442f030cfb124dca42ad），12组目录`simulation/outputs/E1-016/20261107-02-five-real`。命令中`--package`与`--assets`可直接使用这两个实际路径。不重复旧52件或固件检查。

E2输出`simulation/outputs/E2-016/20261107-04-real-asset-compatibility`用实际新包/12组解和明确synthetic info测试了接口，12例各三帧160byte、两条链均匹配。该目录所有OFFLINE_ONLY计划含假启动标识，禁止部署；H必须使用自己刷后五份实际info重新物化。真正部署不等待分析器、文档或新审批。
