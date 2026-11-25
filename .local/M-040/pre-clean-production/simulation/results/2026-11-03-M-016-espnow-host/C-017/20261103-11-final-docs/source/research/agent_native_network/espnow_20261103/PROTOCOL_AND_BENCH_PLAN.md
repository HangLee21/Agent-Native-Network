# 五板ESP-NOW协议与静态台架计划

2026-11-03。现在可运行同核心协议harness、已绑定设备的有限串口台架工具，以及采集后的来源核验、自动分析和指标追加。当前代码为E1_lifecycle_v4、E2_analyzer_v2和H_capture_v5。硬件未到，ESP目标编译、刷机、五板无线和性能均未验证；完整独立验收进度以[C-017](../../../coordination/tasks/C-017.md)、[M-016](../../../coordination/tasks/M-016.md)为准。精确运行边界见[协议接口](../../../firmware/agent_native/INTERFACE.md)和[v2分析API](../../../simulation/results/2026-11-03-M-016-espnow-host/E2-015/analyzer-v2-source/ANALYZER_API.md)。

## 1. 五板承担什么

五块EoRa-HUB-400TB使用同一固件产物，通过各板身份和运行配置区分角色。五块都是对等网络节点，可以在不同run担任源、目的或中继；没有必须一直在线的中心板。电脑负责供电、绑定、配置与日志收集，不作为无线消息的隐含转发路径。断开记录电脑是否影响网络需另做有界验证，不能由“对等”命名推定。

ESP-NOW提供邻居之间的单跳发送，上层负责发现、转发、去重、可靠事务与状态合并。它与原生IP、802.11s及LoRaWAN网关分开。本轮承载使用ESP32-S3侧ESP-NOW，不以LR1121的LoRa宣传参数填写本系统测量。[厂商产品页](https://www.ebyte.com/product/2472.html)列出LR1121/ESP32-S3，具体到货板版本、USB通路及引脚由硬件核对后登记。

按从任务到承载的L5–L1组织实现与证据；这是本项目功能分层，不是OSI编号：

| 层 | 职责与合同 | 台架需要看到的证据 | 当前状态 |
|---|---|---|---|
| L5 固定任务/业务 | 固定源目的、负载、期限、事务或状态类别 | 签发清单与唯一业务ID、完整终态 | 已有有界bench；无LLM驱动任务调度/独立任务模式 |
| L4 端到端事务与状态 | 独立事务、端点ACK、有限重试；按(origin,boot,key)保留最新状态与本地到期 | 接收唯一消息、重复/超时/确认、状态版本记录 | 同C核心host已验证；无跨重启exactly-once或持久提交，CANCEL为best effort |
| L3 多跳与路由 | RREQ洪泛记录路径、RREP反向、DATA/ACK源路由及ERROR失效处理；有限TTL/去重 | 每跳事件、端点接收及源端confirmed | 五逻辑节点host链路与丢失事件已验证；无线/动态路径性能未测，无路由优化算法 |
| L2 邻居与链路管理 | HELLO发现、有界记录与传输结果；通道/peer由ESP适配处理 | 控制帧、邻居/路径状态、发送回调及拒绝原因 | 核心已有实现；ESP实际peer/回调行为待目标编译及实板，无加密配对 |
| L1 ESP-NOW承载/板级适配 | ESP-IDF候选工程、回调入队和单owner任务调用核心 | 原始帧长度、回调、固件/构建身份 | 源码已交付；ESP目标未编译，UART/USB/内存/天线与RF待实板 |

本节按冻结代码列出能力，串口bench收发不能替代各层验证。五板验证功能路径和测量工具，百节点服务域仍是另立合同的规模研究。

## 2. 模式与启动边界

当前固件mode只报idle/active，上电idle，info/stats不启动射频。arm只建立本机绑定run的有限互锁，不发无线；start在有效arm期间启动发现，bench显式启动协议并产生有限业务。测试、组网、任务是用途层次，不是三个已实现的串口模式名；L5任务调度仍属后续业务层。先arm并start接收/中继，单独给源发bench不能唤醒idle中继。

所有五板保持相同协议版本、构建来源与无线配置。每板node_id与boot_id分别记录，重启前后不得只按seq去重。未知对端、帧长/版本错误、缓存满、TTL/期限耗尽及重试上限都要留下明确终态。状态合并只在声明的键和版本规则下进行；未定义的功能不能靠上位机生成预期事件补齐。

## 3. 已冻结的串口最小接口

UART console为115200、8N1，UTF-8逐行JSON。允许启动/IDF日志混杂，主机只处理`schema="ann.serial.v1"`的JSON对象。最终固件请求上限512 byte、不含换行；H客户端按包含换行≤512 byte保守限制。v1仅支持flat对象、ASCII字符串值、非负整数和布尔，不支持Unicode转义/嵌套对象或数组；重复键、非法转义、尾随JSON、NUL/超长整行及未知命令明确报错，随后恢复行边界。nonce必填，1..48个`[A-Za-z0-9_.:-]`字符。

以下是合同示例，不是本机实际握手结果：

```json
{"cmd":"info","nonce":"probe123"}
```

```json
{"schema":"ann.serial.v1","event":"info","nonce":"probe123","firmware":"ann-espnow","protocol":1,"node_id":"aa:bb:cc:dd:ee:ff","boot_id":"...","build_id":"...","chip":"esp32s3","board":"unverified","mode":"idle"}
```

核nonce、firmware/protocol、node_id、boot_id、build_id与预期绑定记录。`chip=esp32s3`或`board=unverified`不能单独证明板型为400TB。info实际可报idle/active；上例只是idle示意。控制命令回nonce，异步事件nonce=null。stop停止协议/bench、清队列并disarm；arm需精确node_id/run_id和1..60000ms duration，start需相同有效run；它们是操作互锁，不是认证。bench完整请求和状态边界以[冻结INTERFACE](../../../firmware/agent_native/INTERFACE.md#serial-v1)为准，H客户端采用更严格的捕获窗与参数范围，见§7.1。

bench必须有限：≤60秒、count≤1000，先低负载，`stop`可取消。`frame_bytes`指传给ESP-NOW的数据字段总长度，包括上层协议头，v1合同≤250 byte；`payload_bytes`仅为该字段内业务正文，不是同一个量，也不包括完整PHY空口开销。官方ESP-NOW同时有v1/v2长度能力，本项目v1合同不会因此自动扩至1470 byte。[ESP-IDF v5.5.1帧格式](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/network/esp_now.html#frame-format)

最终事件身份必须区分`node_id+boot_id`（当前记录节点）与`origin_id+origin_boot_id+seq`（原始事务）。tx_submit/tx_result在同run内按`node_id+boot_id+tx_attempt`配对；tx_attempt是本节点本boot内提交序号，不是RF重试数。frame_rx仅代表接收并解析wire帧，不是唯一应用交付；rx或核心echo且unique_receive=true才是首次端点交付；confirmed说明源收到端点ACK。日志溢出有计数，但溢出后不能声称事件完整。

echo响应是新的反向事务，有自己的origin身份。payload前8 byte是原请求boot:uint32和seq:uint32（小端）；echo_correlation是非交付关联记录，必须与同源、同boot的generated连接，才算源时钟RTT。same_source_boot=false或缺生成记录时留unknown。t_us来自毫秒单调时钟乘1000，不是微秒精度RF测量；echo与correlation不能计两次交付。完整示例见[最终golden](../../../firmware/agent_native/golden/serial-v1.jsonl)，其[provenance](../../../firmware/agent_native/golden/provenance.json)明确为host原始合成日志，不是板上证据。

### 3.1 当前帧与核心边界

ANN v1按小端显式序列化，固定头112 byte、CRC32，最大数据报250 byte/正文138 byte；不发送C struct内存，不实现分片。头保存magic/version/type/flags/TTL、路径长度/索引、origin/目的、origin boot/seq、剩余寿命、状态键、正文长度/类别、最多8个路径节点和CRC。CRC是误码检查，不是身份认证。类型为HELLO/RREQ/RREP/DATA/ACK/ERROR/CANCEL；精确offset见[Wire v1](../../../firmware/agent_native/INTERFACE.md#wire-v1-and-core-boundaries)。

表容量16、源pending事务8、发送/事件队列32；每源boot去重64序号滑窗，63秒无活动后失效，RREQ去重400ms。更老序号拒绝、不回ACK，活跃stream不会被静默淘汰；满表/队列显式拒绝或计数。每事务至多3次发现、3次DATA尝试，500ms重试间隔，源寿命≤60000ms。ACK丢失后同身份重发，窗口内目的重ACK不重复交付。接收节点重启或窗口到期不保证持久防重放；新boot才可重置源序号。

状态按(origin,boot,key)和seq合并，旧版本不覆盖新版本；不保证不同随机boot的全局新旧顺序。CANCEL尝试取消未完成事务并设墓碑，不撤销已交付效果、不承诺分区期间远端删除。剩余寿命扣本地驻留，未知空口时间/跨板时钟误差使严格全局截止保证尚不成立。无加密/密钥配置、持久应用提交或路由优化。以上是可执行原型的当前边界，不等于实板性能结论。

生命周期修订将源deadline设为exclusive：now_ms≥deadline即到期，即使receive先于tick，迟到RREP/ACK/ERROR也不能复活或确认。到期/确认清理对应未发送的本地DATA/RREQ，出队再核pending存活；成功cancel先移除精确事务的未取出本地DATA/RREQ，保留其他队列顺序和best-effort CANCEL。已交给adapter/调用者的副本仍不能撤回，远端/在途弱保证不变。

## 4. 如何判交付与测性能

`tx_submit`只表示提交尝试；发送API或回调成功只说明对应层成功，不证明最终节点交付。[官方发送说明](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/network/esp_now.html#send-esp-now-data)明确MAC层回调与应用接收的边界。端到端成功须由目的端唯一消息及其身份链确认，多跳每次尝试分别记录。

| 量 | 必要来源与分母 | 没有来源时 |
|---|---|---|
| 协议PDR与应用完成率 | 分析器以核心accepted generated唯一事务为分母，仅receiver_log_complete=true才算PDR；expected_generated不符时保留缺项。应用全部签发/拒绝另配计划/终态，不能以核心接纳分母替代 | 覆盖未确认/身份歧义等按metric_status留null，不用回调成功数替代 |
| 协议payload goodput_bps | 目的唯一payload byte×8/实测窗口，扣112 byte ANN头，payload内echo关联8 byte仍包含；仅接受receiver_local_window或host_monotonic_controlled_window | null；不用count×interval或首末成功包间隔，此量不称语义有效goodput |
| RTT与rtt_p95_ms | 同源同boot的generated→echo_correlation配对，nearest-rank P95只对成功echo子集；missing echo与样本数同时报告 | 缺关联/boot不同留unknown；不跨板减时间，不把成功子集P95当全部请求P95 |
| range_m | 明确场地、距离测量方法、天线/摆位、配置与成功判据 | null；不从RSSI或厂家标称距离推算 |
| 重试/空口费用 | 区分应用重发、逐跳提交、MAC回调及驱动可见字段，真实RF重试/airtime需实际可见来源 | unknown/null；若另给估计须明示模型与evidence_kind，不能称实测 |
| 恢复与状态合并 | 指定失联/返回事件、首次交付与持续恢复判据，事务与可覆盖状态分列 | not_measured，不能从主机fixture推无线恢复 |

H冻结工具的实际测量台账为`ann.hardware.measurements.v1`，在`metrics`下逐项登记value/status/reason/source；六项为range_m、pdr、goodput_bps、rtt_p95_ms、rf_retries、airtime_s。以下为其中一项的结构节选，完整已保存记录见[H首次枚举台账](../../../simulation/results/2026-11-03-M-016-espnow-host/H-001/20261103-02-enumerate-only/measurements.json)：

```json
{"schema":"ann.hardware.measurements.v1","evidence_kind":"not_measured","metrics":{"pdr":{"value":null,"status":"not_measured","reason":"hardware_not_available","source":null}}}
```

主机fixture及合成事件永远用`evidence_kind=synthetic`，存独立目录，不填入真实硬件测量表。无板、工具缺失、目标编译未做、目标编译失败及无线未测是不同状态。主机单元测试通过不能改写其中任一项。

## 5. 自动检测与主动台架的四个条件

电脑必须在线且检测进程实际运行。默认只做一次OS串口枚举，不打开串口、不猜板型、不安装驱动或刷写。只有配置中已绑定到预期设备、并明确允许probe的串口才可发送无射频副作用的info；核nonce及协议身份后才登记ready。端口名变化需复核绑定，不能只按COM编号沿用。

ready只表示身份握手满足条件。主动bench还需要独立armed合同：设备集合/绑定、固件构建、无线配置、参数、次数、截止与唯一输出目录已冻结，当前运行有明确激活条件。缺板、绑定不符、非测试固件、未armed、响应不匹配或资源保护停止，均不得触发bench或自动续跑。

H工具支持H-002的`--once`入口，单次≤60秒。既有H聊天的每小时heartbeat已建，ID为h-eora，当前PAUSED；H-002单次预检已完成并review停写（opened_ports=0、waiting_hardware、六项null），后续状态以主卡/应用为准，调度须最终验收及阶段提交后启用，当前没有自动检测运行。H-002只允许枚举或显式已绑定info probe，不触发bench。没有板记waiting_hardware、保留null；新检测追加证据，不覆盖旧状态。最终工具行为随H冻结核对。

## 6. 从静态台架到上车

以下各步均为未来硬件合同，当前执行0次；后续须冻结每步设备、次数、期限、低负载和输出，再运行。

| 顺序 | 最小验证 | 进入下一步所需证据 |
|---|---|---|
| 0 设备与固件核对 | 板型/批次/接口/供电/天线检查，逐板绑定，确认同一固件；在授权单板上做有限info | 五板身份记录，无猜测引脚或未核刷写参数 |
| 1 两板单跳 | 低负载单向接收、关联echo、stop与非法参数处理 | 原始发送/接收/超时链、真实计数与终态；不以fixture代替 |
| 2 五板对等发现 | 相同固件，角色交换、邻居出现/老化、重启boot变化 | 五板均可参与，无固定中心依赖的证据；控制开销留证 |
| 3 静态两跳与替代中继 | 选源/中继/目的及旁路板，核实际逐跳路径；退出当前中继后观察终态/重选 | 唯一源身份、多跳转发、目的接收与失败完整关联。软件允许列表产生的逻辑两跳须单列，不能称物理遮挡证明 |
| 4 事务/状态 | 有界重试、重复/乱序/重启、状态替换与独立事务并存 | 事务不被合并丢失，重复不重复交付，过期及队列满可解释 |
| 5 上车 | 静态合同通过后再记录供电、安装、运动/场地与干扰条件 | 使用新run，不把移动与静态样本直接混合；无线及任务合同可追溯 |

两跳不由TTL值或“走了中继”的提示判定。若同室五板可直接互听，必须说明使用何种可复现配置限制直达或何种物理条件验证，保存每跳日志；主机不代替板上转发。五板尚不能回答百节点竞争、维护状态或服务域问题，后者沿[网络框架](../NETWORK_RESEARCH_FRAMEWORK.md)另立仿真/规模任务。

## 7. 编译、刷写与实现状态如何登记

E1完整代码及主机证据已冻结，构建命令见§7.3。ESP-IDF候选固定v5.5.1、target=esp32s3，ESP目标实际状态为not_performed；现有主机构建成功不能替代目标编译。H只在PATH范围未找到idf.py/交叉编译器，不据此断言整机无SDK。flash offset、板型/USB映射及实际flash/PSRAM仍待实物核，不猜填。

刷写留在到货并核实板型/引脚/flash参数之后，须符合明确的设备操作授权；本轮不刷机/擦除、不接未绑定串口、不安装驱动或全局工具。精确刷写操作由已核固件和硬件说明派生，当前不提供可能覆盖未知固件的命令。

| 交付 | 本文已核内容 | 后续需要M冻结的内容 |
|---|---|---|
| E1固件/协议 | 生命周期修订已冻结，12场景6200断言、164新增边界检查和3个原反例通过，接口/wire格式保持 | ESP目标构建、板上接口/RF行为；与H/E2最终集成 |
| E2独立验证/分析 | 独立v4核心20项通过，分析器v2冻结，44项自测及C封装互验1项通过 | 最后H独立互验/C终审状态见权威任务卡，主机结果不代表RF |
| H检测/测量 | H_capture_v5已冻结12文件；有限采集→自动分析→有来源指标追加已实现，35项主机测试与17号C Capture互验通过 | 无板，真实指标仍null；到货后须按绑定/armed合同执行并满足证据门槛 |

### 7.1 已冻结的H工具命令与配置

以下命令已核H_capture_v5，工作目录为仓库根目录。**本文没有执行这些命令**；到货操作须先核相应任务卡允许、绑定及armed合同。H-002自动调度尚未启用，任务状态以主卡/应用为准。`ACTUAL-*`配置与`UNIQUE-*`目录需替换为实际冻结值；输出必须是所选任务根的直属、全新run目录，不覆盖或嵌套旧run。

默认一次只读枚举，不打开串口：

```powershell
python -B -m tools.espnow_hardware.hardware_tool --task-id H-001 --once --output simulation/outputs/H-001/UNIQUE-CHECK-ID
```

到货后人工逐板确认板号与端口，使用[空绑定模板](../../../hardware/eora_hub_400tb/bindings.example.json)另建真实配置。每条绑定需id、port、node_id、allow_probe、physically_confirmed、binding_basis，并按枚举固定USB身份字段；预登记MAC来自可信逐板初始化记录，没有MAC时不能由该工具自动探测未知板。CH340或COM名称不是板型证明。全部填写的身份字段须相符；无USB序列号时可明确登记location或完整hwid，但仍属于人工绑定。随后才可info握手：

```powershell
python -B -m tools.espnow_hardware.hardware_tool --task-id H-001 --once --probe --bindings hardware/eora_hub_400tb/ACTUAL-bindings.json --output simulation/outputs/H-001/UNIQUE-PROBE-ID
```

工具核随机nonce、schema、firmware=ann-espnow、protocol整数1、chip=esp32s3、预登记MAC、非空boot/build/board和mode=idle；host-synthetic不能通过真实芯片握手。ready后板型仍unverified。只读Windows枚举fallback不能握手；缺pyserial会明确失败，不自动安装。已绑定open前请求DTR/RTS=false，OS/驱动瞬时电平及是否复位尚未实物验证。

对一个已绑定设备的独立stats或stop需显式probe/device，不提供任意命令透传。仅standalone stop允许身份/nonce都合格的active info，收到关联stop回应且状态合格才记stopped；普通probe/stats/bench仍要求idle，错误身份不发stop。端口或采集文件close异常逐项记录，继续其他清理/落盘，cleanup_failed返回失败。两命令分别用新输出：

```powershell
python -B -m tools.espnow_hardware.hardware_tool --task-id H-001 --once --probe --bindings hardware/eora_hub_400tb/ACTUAL-bindings.json --device board1 --command stats --output simulation/outputs/H-001/UNIQUE-STATS-ID
python -B -m tools.espnow_hardware.hardware_tool --task-id H-001 --once --probe --bindings hardware/eora_hub_400tb/ACTUAL-bindings.json --device board1 --command stop --output simulation/outputs/H-001/UNIQUE-STOP-ID
```

台架计划由[disabled模板](../../../hardware/eora_hub_400tb/bench.example.json)另建；armed默认false。真实计划需`schema=ann.hardware.bench.v1`、armed=true、唯一run_id、2–5个device_ids、一个sender_id和一个不同的receiver_id，echo为布尔值、max_runs=1。H客户端按公共接口约束头112 byte，非echo frame_bytes为112..250，echo最小120；这些仍需与E1最终实现核对，不能据客户端校验声称板端已验证。

H计划还限制count=1..1000、interval_ms=10..60000、capture_seconds=1..45，且`count×interval_ms ≤ (capture_seconds−1)×1000`并≤60000。固件接受interval_ms≥1、按`(count−1)×interval_ms`核span及剩余arm时间；H是更保守的客户端。输出末级目录必须等于run_id。到货满足明确armed合同后，命令为：

```powershell
python -B -m tools.espnow_hardware.hardware_tool --task-id H-001 --bindings hardware/eora_hub_400tb/ACTUAL-bindings.json --bench hardware/eora_hub_400tb/ACTUAL-bench.json --output simulation/outputs/H-001/EXACT-PLAN-RUN-ID
```

工具先核全部绑定、逐板握手，再发送带nonce的arm(node_id/run_id/duration_ms)，逐项确认；对非发送板start(run_id)，最后向发送板bench(run_id/dst/count/interval_ms/frame_bytes/echo)。arm有效期为capture_seconds+5秒，最长50秒。开始或异常只要尝试过arm，就向全体已打开板发nonce stop并检查回应；未确认记stop_unconfirmed，不能宣称全体已停，板端还须自己限时终止。该编排不需要手工绕过客户端直接发arm/start。

入口内部截止55秒、合同上限60秒，原始串口累计≤2MiB；无余量停止、不补跑。两至五板串口采集不等于已证明五板多跳。`serial.jsonl`保留host_tx/device_rx、主机时间与原事件。bench结束后自动收尾、核覆盖、分析及追加，详见§7.5；独立`--log`仍只hash/计数，不作实测导入。

H-002未来激活后的仅枚举入口如下。每小时调度h-eora已建但PAUSED，当前未执行；已绑定probe可按最终规则添加，主动台架一律不由H-002触发：

```powershell
python -B -m tools.espnow_hardware.hardware_tool --task-id H-002 --once --output simulation/outputs/H-002/UNIQUE-CHECK-ID
```

### 7.2 当前H证据与未测边界

H_capture_v5的12件文件hash与M冻结相符，[最终冻结锚点](../../../simulation/results/2026-11-03-M-016-espnow-host/H-001/20261103-20-final-h-freeze/freeze.json)为`2e7ada3487c8e202c764680bc93b7ae6e3e4c5a420b5d2aff88643d7a7838d56`。[最终35项主机测试](../../../simulation/results/2026-11-03-M-016-espnow-host/H-001/20261103-18-final-v2-regression/stderr.txt)通过；[17号run](../../../simulation/results/2026-11-03-M-016-espnow-host/H-001/20261103-17-actual-c-capture-v2/result.json)实际编译冻结C host、运行echo，将原始C日志送入H Capture和v2分析。结果为synthetic_capture，未写实测更新；17是run编号，不是17轮无线实验。D未重跑这些命令。

H早前一次实际OS枚举为waiting_hardware、打开0；后续没有真实串口或无线操作。PATH检查未发现idf.py/交叉编译器，只说明该范围的工具状态，ESP目标未编译。14项等早期H回归、v1分析暂停及各次失败均保留为历史，不作最终功能状态。

当前自动计算/追加代码已经接入，正向实测路径仅在受控主机测试中检查；无板所以真实measurements仍全部null。原measurements.json保留初始状态，测量证据通过新增measurement_updates.jsonl追加，不能覆盖旧值或用synthetic填实测。距离、RF重试、airtime没有真实观察就持续null。最后独立互验/终审及任务是否允许运行，见[H-001](../../../coordination/tasks/H-001.md)、[E2-015](../../../coordination/tasks/E2-015.md)、[C-017](../../../coordination/tasks/C-017.md)与[M-016](../../../coordination/tasks/M-016.md)。

### 7.3 E1主机复现与ESP只构建入口

以下命令按E1冻结runner/README核对，D没有执行。E1-014处于review，重跑须先有允许执行的实时任务/预算；示例不恢复旧预算。仓库根目录使用现有`.venv`解释器与CMake/Ninja/GCC，不自动安装：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B firmware/agent_native/run_host_checks.py --output simulation/outputs/E1-014/UNIQUE-HOST-RUN-ID
```

runner拒绝已存在目录，保存任务卡/源码快照、manifest、失败命令、构建及原始JSON。每子命令≤120秒、累计构建/测试≤600秒、输出≤100MiB；保护停止不自动重启，不开串口、不运行ns-3或模型。`result.json`的host_passed只说明同核心主机验证。

当前冻结exe为`simulation/outputs/E1-014/20261103-09-lifecycle-fixed/build/ann_host.exe`，06 exe只属修复前历史。CLI支持`--scenario chain|ack_loss|echo|state|expiry|cancel|error|reboot|bounds|continuous|wire|serial|all`；runner还运行原反例与生命周期检查两个exe。`--console`读stdin逐行JSON，EOF退出，无真实传输，每输入行推进10ms合成时钟，不是墙时台架替代。新证据应在获准run内用runner保存，不写旧目录。

ESP工程在`firmware/agent_native/idf/`，候选SDK v5.5.1；在另行获准且完成工具链准备后，拟用只构建命令：

```powershell
idf.py -C firmware/agent_native/idf -B UNIQUE-ESP-BUILD-DIR build
```

此命令未执行/未验证成功，不自动下载SDK。target固定esp32s3，拒绝其他显式target。源码默认UART0/115200、owner任务stack 12KiB；ANN_CHANNEL范围1..13、默认1，实际合法通道及所有节点一致性须到货核，不将默认值当已测配置。USB通路、Flash/PSRAM与板型仍未核。build_id按源码hash生成，board仍unverified；没有flash/erase命令。

ESP适配源码把回调入队，由单owner任务调用非线程安全核心；同时只保留一个SDK发送待回调。缺回调或回调队列溢出会停止本地协议；停止时若仍有未决回调，禁止再启射频直至重启，避免迟到回调归入新提交。源码已交付，实际驱动时序、内存适配及停机行为待ESP目标和实板验证。

### 7.4 E1当前验证与冻结依据

[当前主机结果](../../../simulation/results/2026-11-03-M-016-espnow-host/E1-014/20261103-09-lifecycle-fixed/result.json)的12类原场景实际执行6200条断言，另有164条生命周期边界检查，以及late_ack、late_rrep、cancel_unsent_cached_data三个原反例通过。6208是[06修复前](../../../simulation/results/2026-11-03-M-016-espnow-host/E1-014/20261103-06-line-framing/result.json)动态执行计数，不继续当当前计数，也不相加作新样本。100条低并发事务、ACK丢失去重、重启/容量/wire/串口仍为同核心synthetic主机验证，不是无线性能实验。

[07历史检查](../../../simulation/results/2026-11-03-M-016-espnow-host/E1-014/20261103-07-freeze/checks.json)与06旧快照/golden对应；golden格式和来源保留。当前[FREEZE.json](../../../firmware/agent_native/FREEZE.json) SHA-256为`3b028fb77103ad011a92e0fdb7f34d4065a940806240ad570f7f30e21c2d908f`，INTERFACE为`ee87f1e1a2c6f134b306582a0d2c003a9cdf91038032b132c80ab744f8b3e32e`；M的active_freezes.E1指向E1_lifecycle_v4，22项hash已匹配。早前f38bee...冻结及42.718秒累计只对应当时检查点。D未重跑；目标编译/RF仍未做。

### 7.5 自动分析与实测追加入口

[ANALYZER_API](../../../simulation/results/2026-11-03-M-016-espnow-host/E2-015/analyzer-v2-source/ANALYZER_API.md)与[ANALYZER_FREEZE](../../../simulation/results/2026-11-03-M-016-espnow-host/E2-015/analyzer-v2-source/ANALYZER_FREEZE.json)规定`ann.analysis.v1`，当前实现版本为v2；仅Python标准库，读取文件/返回字典，不开串口、不执行固件、不写H目录。M已冻结四件文件并核hash。[44项分析自测](../../../simulation/results/2026-11-03-M-016-espnow-host/E2-015/20261103-15-analyzer-v2-regression/result.json)及[实际v4 C日志/H封装互验1项](../../../simulation/results/2026-11-03-M-016-espnow-host/E2-015/20261103-16-v2-v4-capture-context/result.json)通过，均为synthetic_host_tests、无硬件测量。早前36项仅属v1历史，不与v2相加。完整独立验收状态见[C-017](../../../coordination/tasks/C-017.md)与[E2-015](../../../coordination/tasks/E2-015.md)，不由文档测试数代替。

用importlib加载`tests/espnow/analyze_logs.py`，调用`module.analyze_files(config_path, log_paths, manifest_paths=())`。E2自己的CLI形状如下，输出位于已有manifest且获准的新E2 run，analysis.json不得已存在；示例未执行：

```powershell
python -B tests/espnow/analyze_logs.py --config ACTUAL-ANALYSIS-CONFIG.json --log ACTUAL-SERIAL.jsonl --manifest ACTUAL-CAPTURE-MANIFEST.json --output simulation/outputs/E2-015/EXISTING-APPROVED-RUN/analysis.json
```

H应调用函数，在H获分配的新输出保存，不写E2根。配置含run_id、source_node_id、destination_id、mode、evidence_kind、expected_generated、receiver_log_complete、measurement_duration_us、duration_clock；mode只接受raw_no_retry/reliable。当前固件bench为可靠事务，没有raw bench命令，分析器可标raw不代表固件或实板已实现/运行它。反向echo有独立origin，须指定原source，不把echo计入原请求分母。

输入支持ann.serial.v1原行或H `direction=device_rx,event={...},evidence_kind=...` envelope，忽略host_tx/非协议启动日志。每文件≤10MiB、每行≤16KiB；重复键/NaN不算有效证据，坏JSON使覆盖未确认。unique_receive若存在必须是JSON布尔；hardware_measured不接受缺该字段的legacy接收兼容。重复generated即使字节相同也标身份歧义，该身份排除RTT并保留missing/invalid计数。保留clock_order_warnings与callback_binding_issues。tx_submit status0是即将调用传输，只有显式accepted才填driver_accepted，其余留null与已知子集。

配置/日志/capture context须不可变。硬件分析要求evidence_kind=hardware_measured、H-001/status=hardware_capture_unanalyzed捕获上下文、hardware_serial envelope及明确boot；所有H捕获context的run_id须与配置一致。每份context必须含log_sha256映射：键为每个输入日志`str(Path(log).resolve())`的绝对路径，值为该文件原字节SHA256，覆盖全部输入。缺run/冲突run、缺映射/日志或错hash均拒绝；synthetic及其他任务/状态manifest不构成硬件计算依据，文件标签也不代替物理绑定/nonce。

不要传随后会更新的RUN_MANIFEST作不可变capture来源。分析后仅将metric_status有效的真实数值追加测量，source关联分析及原始hash，未知量继续null；无硬件保留hardware_not_available/source=null，不虚构计算。

H_capture_v5已实现自动调用：台架前读baseline stats，结束时全体stop、final stats及排空，关闭串口与Capture后写不可变capture_context.json及analysis_config.json，再调用已核active分析器；前后复核E1/E2/输入hash，未知版本或漂移拒绝，不回退旧版本。上下文核每板boot、event/queue overflow、接收端delivered增量与唯一rx、坏JSON/残行及全体stop回执。实测窗口用host monotonic，含串口控制/停止/排空延迟，不是PHY计时。

分析成功只会将reliable模式、hardware_measured且证据足够的有效指标写入新的measurement_updates.jsonl；source含analysis、原始日志、context、配置及分析器hash。缺源/生成数不足、损坏日志、接收计数不符、停止未确认或清理失败不追加有效实测；无窗口时goodput留null，无有效echo时RTT留null。synthetic输出进入独立synthetic目录，永不生成实测更新；once/probe不触发台架或虚拟测量分析。check.json、capture_context.json、analysis.json、measurements.json及可能的measurement_updates.jsonl共同说明结果；没有追加文件时先查analysis/metric_status和coverage_reasons，不把文件缺失补成数值。

H-002使用`hardware/eora_hub_400tb/bindings.local.json`（Git忽略），配置不存在只枚举，存在且明确allow_probe才可probe，不猜绑定。每小时heartbeat h-eora当前PAUSED，待验收/预检/提交后启用；状态以[H-002主卡](../../../coordination/tasks/H-002.md)和应用为准。主动台架始终另需armed任务，不由heartbeat触发。

证据原字节正在汇入[M-016主机归档](../../../simulation/results/2026-11-03-M-016-espnow-host/README.md)，[索引](../../../simulation/results/2026-11-03-M-016-espnow-host/ARCHIVE_INDEX.json)映射原路径/hash。目录内是源码、日志和manifest等文件，文件数量不是测试数量；当前仍收集中，未把归档收集写成最终验收。

## 8. 来源

官方资料核读日期2026-11-03：[EoRa-HUB-400TB产品页](https://www.ebyte.com/product/2472.html)、[ESP-IDF v5.5.1 ESP32-S3 ESP-NOW](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/network/esp_now.html)、[同版本官方例程](https://github.com/espressif/esp-idf/tree/v5.5.1/examples/wifi/espnow)。官方文档用于核单跳API、长度与发送回调边界；本仓库上层帧、串口语义、测试及板型绑定以实际冻结实现为准。
