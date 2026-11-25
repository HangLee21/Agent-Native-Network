# ABC 三板接续说明（配置交接前）

2026-11-06，D-015 abc-0.3。按 [M-018-ABC](../../../coordination/handoffs/M-018-ABC.md)新增15分钟说明整理预算，原账本不重置。H真实ABC绑定/标签及E1三节点SOCP产物已定向交付并核hash；下文已补真实配置入口，**E2最终执行计划及C对应就绪结论到位后才由H执行**。guide-1.0原副本在03号目录保留，当前 [操作页勘误版1.0.1](USER_GUIDE_PACKAGE01.md) 仅改C指出的事件名；来源审计原字节保留，A/B可按其独立就绪结论先做。

## 接入变化和版本

用户已报告ABC均接入。H已按ROM MAC重新关联三板，固定侧记 [BOARD_INVENTORY_20261106_ABC.json](../../../hardware/mid_baseline/BOARD_INVENTORY_20261106_ABC.json) SHA256为`a3498aa190939d98b6992ddda9801056ccc792ec4ee601ee29a2ad1fd1477fe7`，D核hash一致：

| 板 | 真实MAC | 当次端口/USB位置 |
|---|---|---|
| A | `90:da:72:48:a4:f8` | COM9 / 1-1.2 |
| B | `90:da:72:48:a5:cc` | COM10 / 1-1.3 |
| C | `90:da:72:48:a4:e0` | COM11 / 1-1.4 |

三板均由H的13号ROM核查确认ESP32-S3/实际4MiB、安全flags0；此次正常复位、端口关闭，未刷MID或运行RF。D只核记录，没有设备操作。原COM7/COM8已经变化，**旧指南中的COM号仅是历史提示，不能直接用于本轮设备动作**；每次仍由H按MAC/USB重核。C原程序备份按该次交接正在执行，完整备份是否成功待H新固定记录，不能由ROM识别推断。

| 接手输入 | 本页当前记录 | 到达后补入 |
|---|---|---|
| H真实ABC绑定 | 上述侧记已核hash，三板MAC/当次端口/芯片/容量已确定 | C完整备份结果及后续应用身份另按H新交付核对 |
| 适用包 | 已核package-01 manifest `d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683` | C若需标签集成重建，记录新包/源码/build hash；保留package-01，不自动套用旧就绪结论 |
| E1三节点SOCP | 10号ABC-real四组固定输入/optimal输出/update已交，索引见下节 | E2执行计划选择的具体case及预算 |
| E2三板执行配置 | 未收到冻结可执行版本 | 对应包/配置hash、角色轮换、实际native命令、日志入口、包数/时序/RF预算 |
| C设备就绪 | 本页不代填 | 对具体包/三板配置的结论及适用范围；A/B可先独立通过 |
| H/E2实测 | 未收到三板实测证据 | 原始日志、唯一端点接收/转发关联、停止状态、显示观察来源及未测项 |

package-01中C字母缺省为`?`不等于设备不可辨认；真实MAC和节点标识仍须清楚。必要标签集成由E1在自己范围完成，不改H显示冻结模块。不能仅为字母映射拖住已具条件的A/B验证。

## 已交付的真实三板配置及命令

E1此次沿用原package-01，无新固件或接口；C以`?`加完整MAC识别。资产在`simulation/outputs/E1-016/20261106-10-ABC-real/cases/`，INDEX SHA256 `37d879827f6e50bd940737dccdee6ca82a79d410b4ac2957a06dc39826ff1f57`。每case的input/solution/update/离线编码四件hash由INDEX锚定，D逐件核验；E1报告四例均SOCP optimal，D只读核输出，未复跑求解。09号是合成身份准备，不能用于本轮设备配置。

| case | 业务 | network_update.json SHA256 |
|---|---|---|
| AB | A↔B两流，三节点可参与 | `64ee402f08dc90b2787fd22cb9a1adcb4fb24581615c90189ebc956c4165b132` |
| AC | A↔C两流，三节点可参与 | `238cf71f171d02fe5530d34a459a8daf0e1d99adee66ff5966e2397cf6f6eddc` |
| BC | B↔C两流，A仍是配置入口 | `da990cd13d8795a173f04e43237968046185120f523849a70ca5ab49528500b6` |
| AC_controlled_two_hop | A→B→C及C→B→A，逻辑禁直边 | `0bf19cf8d08ffa461f3ba6d48e25f01a1c3acf9c7e732a4d4d73bc74500d0448` |

普通case也要看实际next_hop，不预先称直连或两跳。受控case在输入图中将A-C的mean=0、variance=1，其他边mean=.8、variance=.0001，rate=.05/qos=.9；均为假设模型。E1在标准SOCP输出后核指定两跳链，未事后屏蔽gateway，不满足则拒绝。该输入限制的含义须随结果保留。

H直接标签文件`BOARD_LABELS_20261106_ABC.json` SHA256 `f16af2085ce37993a0a69c45d2af7091f3412390cf7165557ceda4c6b25cd264`，含bindings.A/B/C及D/E=null。E1实际运行用自库存派生的DERIVED_LABELS.json，SHA256 `668226cf74986d9d1f131e5441f7dd97bfc1dd73f7c4cfd32a82c27e96720231`；二者ABC值一致，文件hash因来源字段不同而不同，不能把H标签hash写成E1当次命令输入。新增`abc_prepare.py` SHA256 `4917cf17bc4574f7cebc06a75a3ae3b7b3fa027402470e4fa08360f654418b3b`，只是配置准备入口，复用原冻结Planner/bridge，不修改原13件源码。

**禁止直接发送OFFLINE_ONLY_config_boot1_seq1.bin。** 它们84bytes、固定boot1/seq1，只作编码检查。部署仍先按guide-1.0读取本次A的数值boot，三板共同start绑定该A boot；C自己的boot只用于C的数据身份。按E2计划选择`$caseName`（仅上述四个之一），`$firstSeq`为新的递增配置序号，`$midRun`为获分配的新空输出目录。真实CLI如下，D未执行：

```powershell
Set-Location -LiteralPath 'D:\Multi-Agent Network'
$midPython = 'D:\Multi-Agent Network\.local\mid\E1-016\venv\Scripts\python.exe'
$caseRoot = 'D:\Multi-Agent Network\simulation\outputs\E1-016\20261106-10-ABC-real\cases'
$caseUpdate = Join-Path (Join-Path $caseRoot $caseName) 'network_update.json'
& $midPython tools/mid_baseline/bridge/bridge.py $caseUpdate --publisher 90:da:72:48:a4:f8 --boot $aBoot --seq $firstSeq --nonce config-ABC --output (Join-Path $midRun 'config-command.json')
```

只将生成JSON送A。切case时整表替换，新的配置seq递增；不把四case合成超过两流的表。三板均有匹配配置的config_applied及相应有效route_selected后再发业务。C上的info应核node_id=`90:da:72:48:a4:e0`及原MID build，字母`?`不作为错误。send字段/stop排空/显示语义沿guide-1.0；例如AC或受控AC的源A最终dst是C完整MAC，中继是当前实际next_hop，不能把dst填成中继MAC。包数、payload、串口采集时序、是否周期publish均取E2最后冻结计划，不在本页自加场景。

## 三板的操作顺序

1. H重新核ABC身份并完成所需原程序备份；先沿已有A/B就绪路径验证，不因C加入重跑已通过工作。D只引用备份是否完整及摘要来源，不复制私有备份原字节。
2. E1/E2将真实节点编入SOCP配置。所有板可作为源、目的或中继，实验按配置轮换，不永久指定B为中继。当前实现最多2个同时存在的源/目的流，三板6个有向对需要分批配置；不能声称一张表含全部6流。
3. 仍读取实际publisher本次boot；参与节点共同绑定该publisher run。配置只从实际入口注入，按原发送者/boot/seq去重转播；每500ms的选路及按周期保持机制不变。真实参数和串口入口沿E1/E2冻结，不手写MAC、假boot或固定下一跳来替代Planner。
4. 先验证任意对端可发可收，再执行至多一次本轮新增的受控两跳功能检查。禁用直接边只能发生在明确记录的输入图中；若配置仍允许直连，必须按实际route_selected判断，三板在线不证明经过中继。
5. H同时保留三端原始日志，结束每板stop并核radio=false/stopping=false、进程退出和端口关闭。E2按固定原始结果核对，D再写实测页；未确认的停止或缺失日志保留失败。

RF总量仍是原最多6次、每次60秒、每源最多1000包、总6分钟，不因C加入翻倍；本页不另定发包量。具体次序、包数、有效配置和采集方式由E2/H冻结并计入原账本。

## 什么才算两跳证据

对同一数据身份`(origin, origin_boot, seq)`，至少保存：

| 位置 | 所需事件/字段 | 判定 |
|---|---|---|
| 源 | 实际tx_queued/tx_submit、dst、flow、实际next_hop | 本次选择和提交指向中继；CMD OK本身不证明发出 |
| 中继 | 同身份rx_relay及其转发tx_submit/next_hop | 收到并向目的转发；只收到不等于已转发 |
| 目的 | 同身份、dst为本机的唯一rx_local与payload | 本地交付；重复、缺失和失败单列 |

每条记录同时保留记录设备的node_id/boot_id/build_id与monotonic_ms；记录设备boot和数据origin_boot不能混淆。控制原发送者也不等于当前无线上一跳。MAC回调只算链路结果，无端到端ACK则源仍UNCONFIRMED、RTT保持null。

若输入图人为禁用某条直达边，结果名称写“逻辑禁边的受控两跳转发功能检查”。它不能证明真实RF直连不可达、自动发现遮挡、覆盖收益或原论文移动恢复。要描述是否实际两跳，以三端事件关联为准，不能只引用Planner意图。

## 显示和后续交接

保留现有六页/PRG只切页、异步单槽及有限I²C。目的DEST RECEIVED是目的本机观察，源LINK OK仍UNCONFIRMED；不为显示新增ACK/重传。新包的OLED像素、PRG实物观察与I²C READY分别记录，不能套用旧ANN的用户确认。

H已定向交ABC身份；D也已一次通知E1/E2将三板固定配置同次交D，三条H/E1/E2工具回执成功存04号证据。E1/E2冻结配置后，D据同版本补精确命令页；H/E2实际结果随后定向交D/C/M。当前不读取活动实现作为冻结合同，不轮询文件/聊天、不后台等待，也不自行完成整卡。
