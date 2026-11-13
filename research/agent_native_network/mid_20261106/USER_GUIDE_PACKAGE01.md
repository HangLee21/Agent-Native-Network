# MID A/B 操作指南：package-01

版本：D-015 guide-1.0.1（C的D-doc-02事件名勘误），2026-11-06。适用于E1-016检查点2的下列精确包。D已核包/源码hash和真实解析入口；本页命令未由D在设备上执行。E1目标编译/离线镜像校验已交付，E2最终native配置、C设备就绪和H实板结果依各自固定交付核验。本页不是烧录放行记录。

## 1. 系统怎么运行

笔记本运行Planner，输入业务与位置/预测信道，解路由SOCP；bridge将结果编码为配置。A通过USB接收配置，再无线广播；其他节点按原发送者、boot和递增seq接受、去重、转播。每个节点每500ms为每个流选一个下一跳并保持。USB入口也能正常收发，peer业务路径不必经过入口。

当前先让已接的A/B验证双向配置、业务与显示对应，不等待C–E。两板直接通信不证明多跳、覆盖扩大或移动恢复；小车/定位/SDP运动后置。系统名称为“作者候选实现的ESP-NOW适配”，原TRO最终实验版本未知、模型未物理校准。依据见 [来源核查](SOURCE_AUDIT.md) 与 [阶段2决定](../../../coordination/handoffs/M-018-stage2.md)。

## 2. 核对包和设备

| 项目 | 固定值 |
|---|---|
| 包目录 | `D:\Multi-Agent Network\.local\mid\E1-016\package-01` |
| PACKAGE_MANIFEST.json SHA256 | `d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683` |
| E1 FREEZE.json SHA256 | `95e7499f8e5c1469af4a36b29b52e5522a44bf9e19a17497df559dd58d686f40` |
| INTERFACE.md SHA256 | `689b8cc1d4f96e805563c2e0459029ad02e033a32d487537b32e36b16f201bf2` |
| build_id | `mid-v1-99e77eba7e472bd687ea18321d6ac566e9e8b21d764431e1b42ec7fee945c2f3` |
| H显示FREEZE SHA256 | `2d72ee784757d881a6b77108bf886e5e6e0591934c94693d5baee0330e4da9aa` |
| A | MAC `90:da:72:48:a4:f8`；此前COM7/USB location1-2 |
| B | MAC `90:da:72:48:a5:cc`；此前COM8/USB location1-1 |

D此次核52件包文件的长度/hash、13件E1源码hash及H生产6件hash均匹配；证据在`simulation/outputs/D-015/20261106-03-package01-guide/PACKAGE_INPUT_CHECK.json`。后续包变更需新hash和相应审查，不沿用本页身份。

COM号只是提示。H每次重新核USB/芯片/MAC，确认实际4MiB原程序备份；B备份状态以H交接为准。C–E未绑定，显示`?`。设备动态记录见 [A/B清单](../../../hardware/mid_baseline/BOARD_INVENTORY_20261106_AB.json)。A原ANN+OLED和私有备份保留，新包启动后应变成上述MID build；旧OLED正常不能代替新MID实物确认。

固件配置：ESP32-S3、ESP-IDF5.5.1、PSRAM关闭、DIO40MHz、镜像header2MiB、信道6、UART115200/8N1。header2MiB不代表实物Flash只有2MiB，也不能代替4MiB备份。上电无线默认关闭。

## 3. H烧录前后的步骤

只有H操作串口/设备。先确认E2针对本包冻结的native计划，以及C对同一包/板型/场景的设备就绪无阻断结论。沿H原预算，先A再B，不需要等五板；本页不重置预算或增加实验。

H核包和备份后，以包内`HANDOFF.json`为准，在包目录运行对应命令。下面是该文件的真实命令写法，`$boundPort`必须由H赋成刚核实的当前板端口；D未执行：

```powershell
$midHardwarePython = 'D:\Multi-Agent Network\.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe'
Set-Location -LiteralPath 'D:\Multi-Agent Network\.local\mid\E1-016\package-01'
& $midHardwarePython -m esptool --chip esp32s3 --port $boundPort --baud 460800 --before default_reset --after hard_reset write_flash '@flash_args'
```

包内flash_args写三项：

| 偏移 | 文件 | SHA256 |
|---|---|---|
| 0x0 | bootloader/bootloader.bin | `49b1284cc1cb4b0a0c3e07365bd7218943fe27d7b191151439db0789280e6c34` |
| 0x8000 | partition_table/partition-table.bin | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` |
| 0x10000 | mid_espnow.bin，812640bytes | `37e714f7a364431cebff2ed236ee6d4084d751ee2f60b3c94be2cc8aafb4d435` |

保留包原样参数，不erase-all、不写eFuse、不force、不替换NVS。首板启动、CLI、OLED和PRG记录后再推广B。目标编译和镜像hash有效不能证明实物启动；失败保存原文，按H/C既定流程处理。

## 4. 串口基本规则和身份

每条命令是一行JSON，末尾换行；允许CRLF。必须有`cmd`和1–64个可打印ASCII字符的`nonce`。输入schema可选，示例统一填`mid.serial.v1`；输出schema固定为该值。单行最多1024bytes（不含换行）；重复key、尾随非JSON和超长行拒绝。一个端口同一时刻由一个采集器持有。

先在A和B各自的串口送一行；nonce可按板区分：

```json
{"schema":"mid.serial.v1","cmd":"info","nonce":"identify-A"}
{"schema":"mid.serial.v1","cmd":"info","nonce":"identify-B"}
```

匹配`command_result`中的nonce并检查`ok=true`、`firmware=mid-espnow`、正确`node_id`/`device_label`、上述`build_id`及各自`boot_id`。`boot_id`是数值；A、B各有自己的值。保留启动行和两端原始回应。编译写入的`board`字符串不是独立实物型号鉴定。

## 5. 绑定A本次启动并启用两板

从**本次A的info回应**取数值boot，记为`$aBoot`。A和B的start都使用A MAC和这个A boot；B自己的boot仍保留为B的事件身份，不能填作publisher_boot。以下PowerShell只生成待发送JSON，不打开串口；`$aBoot`须先由实际回应赋值：

```powershell
if ($null -eq $aBoot) { throw '先读取A本次info的数值boot_id' }
@{ schema='mid.serial.v1'; cmd='start'; nonce='start-A'; publisher='90:da:72:48:a4:f8'; publisher_boot=[uint32]$aBoot } | ConvertTo-Json -Compress
@{ schema='mid.serial.v1'; cmd='start'; nonce='start-B'; publisher='90:da:72:48:a4:f8'; publisher_boot=[uint32]$aBoot } | ConvertTo-Json -Compress
```

把第一行生成结果送A，第二行送B。各自检查`ok=true`、`radio=true`、`mode=wait_config`、`stopping=false`、`locked_until_reset=false`。start在busy/stopping/locked时拒绝，不自动重启或重试。

任一板复位后重新读身份；A复位还需按新A boot显式重新绑定所有参与板。stop/start保留板本地boot及数据序号，不把重启、重绑定与新配置序号混用。

## 6. Planner结果和配置注入

工作目录回到仓库根目录。Planner使用E1独立环境；bridge只打包，publish才开串口。新输出使用执行者获分配的新空run目录及RUN_MANIFEST，以下以`$midRun`表示其绝对路径，不写进已有结果。

E2给出的A/B双向输入已由E1实际求解，输出optimal；无量纲假设模型mean=.8、variance=.0001、rate=.05、qos=.9，**不是实测校准或QoS结论**。已交付update：

```text
simulation/outputs/E1-016/20261106-08-AB-planner/network_update.json
SHA256 db11092bb00a3b80ef76dbf30eea15cb9d5755836a7bd58b52e8d8d2944e79c2
```

该表包含A→B和B→A两流，保留完整源/目的/执行节点。E2最终计划须选明实际使用输入/输出hash，不手写固定下一跳绕过Planner。本页不重复求解。

配置原发送者必须是A，boot必须是刚读取的`$aBoot`，seq使用本轮新的严格递增非零uint32；`$firstSeq`由执行计划确定，不复用已接受序号。离线生成一条配置命令的真实CLI：

```powershell
Set-Location -LiteralPath 'D:\Multi-Agent Network'
$midPython = 'D:\Multi-Agent Network\.local\mid\E1-016\venv\Scripts\python.exe'
$abUpdate = 'D:\Multi-Agent Network\simulation\outputs\E1-016\20261106-08-AB-planner\network_update.json'
& $midPython tools/mid_baseline/bridge/bridge.py $abUpdate --publisher 90:da:72:48:a4:f8 --boot $aBoot --seq $firstSeq --nonce config-AB --output (Join-Path $midRun 'config-command.json')
```

仅将生成的JSON行送A；B从无线接受。`config_rx`只表示解码观察，可能随后被拒绝；应在A/B日志中看到相同原`origin/origin_boot/seq`的`config_applied`，再看到对应流的`route_selected`和非null实际next_hop。A的发送行或成功回应不证明B已应用。未具备这些条件时保存失败，不继续发业务。

若E2最终计划采用作者候选的1s周期配置发布，H可用真实`publish.py`。`$aPort`为刚核实的A端口，`$publicationCount`按冻结计划取1–60并计入同一RF预算；同端口其他采集器必须先关闭。使用已有物理Python（含pyserial），不临时安装依赖：

```powershell
& $midHardwarePython tools/mid_baseline/bridge/publish.py $abUpdate --port $aPort --publisher 90:da:72:48:a4:f8 --boot $aBoot --first-seq $firstSeq --count $publicationCount --output (Join-Path $midRun 'A-publication.jsonl')
```

该入口每1s用新seq发一次，先info核入口实际MAC/boot及active/wait_config状态；独占新日志，退出关闭端口。它只记录其持有端口的时段，不代替B采集；不自动start/stop，也不保证远端安装。H最终场景仍要停止两板。周期发布期间A端口不能再被另一个程序同时打开用于send；并发采集/业务时序按E2/H固定执行入口安排，不能临时抢串口。

如需新问题求解，真实Planner CLI仍为`planner.py <problem.json> --output <new-solution.json>`。输入必须显式节点/流、mean/variance及来源，或Nx2位置和全部N0/n/L0/a/b；两种信道输入二选一。只有optimal输出中的`update`对象交bridge，不能把完整solution外壳直接当update。当前最多5节点/2流、payload160bytes、无线帧250bytes，超界拒绝不分片。

## 7. 发一包并对应目的接收

双方应用配置且实际下一跳就绪后，H在A端口送：

```json
{"schema":"mid.serial.v1","cmd":"send","nonce":"ab-1","dst":"90:da:72:48:a5:cc","payload_hex":"6869"}
```

这是2byte的`hi`字段示例，nonce不是数据序号。数据seq由板端生成；实际台架payload和发包数按E2最终计划，不能把本例再加到预算外。A应有`tx_queued`、`tx_submit`及链路回调，B应有本地`rx_local`，其`origin`为A、`origin_boot`为A本次boot、`seq`与源事件一致、`dst`为B、payload匹配。源和目的设备日志中的`node_id/boot_id`各属于记录设备，不能与数据原始身份混淆。

反向由B送往A，使用已存在的B→A流：

```json
{"schema":"mid.serial.v1","cmd":"send","nonce":"ba-1","dst":"90:da:72:48:a4:f8","payload_hex":"6869"}
```

没有自动echo或ACK。单包受理、MAC成功、目的唯一接收分别记录；缺目的日志时交付未知。两端唯一身份按原始source/boot/seq对应，64项去重缓存是有界机制，不宣称无限历史exactly-once。数据进入队列时锁定当次实际下一跳，后续周期变更不改已排队项。

E2先前语义草案为双向各5包、间隔500ms、一次run≤24s；它的`enabled=false/native_commands=null`不直接执行。当前正式native方案到达后，由H按其精确hash/实际payload/时序执行，不混用草案和新接口。

## 8. OLED和统计怎么读

PRG稳定按下40ms只切页：状态→TX→RX→配置→计数→帮助；不发无线，不切模式。启动/复位时不要按住PRG。源的SUBMITTED或LINK OK仍配UNCONFIRMED；目的合法唯一接收显示DEST RECEIVED。配置APPLIED只表示本机采用；CMD OK只表示命令受理。`!`和最后发送故障保留，后续成功不清除。

数据seq/flow/配置seq以8位十六进制显示；`--------`为未知，未知MAC用`--:--:--:--:--:--`。stats的display_hw READY只表示首帧I²C事务成功，实物像素和PRG须另有观察记录；原H-004用户确认不能代替新版MID观察。显示默认帮助已由E1填成真实五行：

```text
JSON + nonce required
info / stats / stop
start publisher+boot
config frame_hex
send dst payload_hex
```

获取本地统计：

```json
{"schema":"mid.serial.v1","cmd":"stats","nonce":"stats-A"}
```

tx_queued/submitted/link_ok/link_fail统计不等于唯一业务包数或目的交付；控制TX也有串口提交/回调事件，但不增加数据OLED TX计数。实际交付用目的`rx_local`原始日志计算，重复接收单列。无端到端ACK，RTT保留null；不能用异机时钟差算单向延迟，不能从MAC回调生成目的成功或RF重传量。

## 9. 停止和失败处理

无论正常还是失败，H结束时分别向A/B送stop并保留对应回应：

```json
{"schema":"mid.serial.v1","cmd":"stop","nonce":"stop-A"}
{"schema":"mid.serial.v1","cmd":"stop","nonce":"stop-B"}
```

stop取消排队并等待当前in-flight回调排空，回应受理时可能仍`stopping=true`。按有限采集时序再读info/stats，确认两板`mode=idle,radio=false,stopping=false`；不能只凭stop的ok=true称已停止。采集器finally关闭端口、结束子进程，停止未确认则记录失败。

| 情况 | 保存和处理 |
|---|---|
| inactive_or_no_config / no_route_or_queue_full | 保存command_result和配置/route_selected/queue_depth；不把受理失败算已发送 |
| config_rejected或config_stale | 查A实际MAC/boot、双方绑定、原配置seq和完整帧；不借清状态掩盖旧序号问题 |
| publish入口身份不匹配 | 记录其拒绝，重新核设备及本次boot；没有发送的配置不计远端失败 |
| tx_link_fail | 目的仍未知，核目的原日志；回调失败不推出目的一定未收 |
| queue_timeout | 本地队列1000ms期限，单列本地发送失败 |
| callback_timeout / input_queue_overflow / locked_until_reset | 记录原事件与统计；固件锁定到物理复位，无自动重试；复位后重核boot和绑定 |
| stop未完成、原始采集缺失或身份/build不符 | 停该场景、保存失败，不能补造接收或宣称功能完成 |

最终保存实际包/配置hash、两端启动身份和原始事件、计数及日志窗口、停止状态、OLED观察来源和未测null。电脑汇总日志属于监测证据，说明使用USB还是无线及其成本。A/B后续实测报告由H/E2/C交付，本页不预填成功率或实物通过结论。
