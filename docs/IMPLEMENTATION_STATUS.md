# 实现状态（代码级审计结果）

2026-11-15 M-050：生产0b7f0b1已推送。用户实机运行已通过上传、私有Python/服务导入与dnsmasq语法检查，后被默认路由拦截，服务配置未完成。经用户明确授权专用直连且保留现有路由，安装器在dedicated确认后仅查询/提示/记录默认路由，不增删改；未确认仍拒绝，DHCP专口绑定且不下发网关/DNS、EUI核对保持。H三项针对性检查、C窄审通过限定软件范围；目标新版安装待用户重开原入口。证据simulation/results/20261115-M-050-dedicated-route/。

2026-11-15 M-049：生产4f1ee7f已推送。/opt安装预算保持128MiB，暂存改按实际压缩包+服务解包+8MiB余量动态计算（当前约16.42MiB），优先/tmp、不可用则/var/tmp；错误及白名单日志显示可用/所需值。SSH正常退出先client.close，超时仍可强制中止。H针对性主机检查与C窄审通过；用户旧日志未记录空间值，尚不能确定真实SPACE_TMP/10038根因，目标新版未重试。原失败未上传/安装，日志显示电脑配置已恢复。证据simulation/results/20261115-M-049-staging-space/。

2026-11-15 M-048离线候选交付：生产1816020已推送。用户实机确认Raspbian8/Jessie、armhf、libc6 2.19、systemd215，缺Python3/dnsmasq。现随包提供8,789,982字节私有运行时（27个签名索引包、80个ARM ELF静态闭包），不安装系统dpkg包或替换libc/systemd；单Paramiko连接完成预检/SFTP/安装，登录密码仅内存用于sudo，默认同密一次输入。依赖先验证再切服务，SFTP握手/I/O/传输均有超时，租约使用项目目录及明确账号权限。H主机/模拟验证、E2静态包检查、C针对性复核已完成，C036-03在此范围关闭。真实ARM运行、SFTP/sudo和完整网关安装仍待用户运行原SETUP_GATEWAY.cmd；不称已安装成功。证据 simulation/results/20261115-M-048-offline-deployment/。

2026-11-15 M-048阶段交付：生产 f81dbf6 已推送，将查询/传包/安装合并成单次SSH会话，依赖齐全时再进行必要sudo认证；POSIX预检实际Python路径/版本/标准库及系统、架构、相关包，缺依赖在解包前停止，白名单事实写本地日志，包mtime固定。H五项主机/隔离测试及C窄审通过有限范围；实际Windows交互与目标网关新版未测。用户上一轮SSH及上传成功，sudo找不到python3，安装器未启动；匹配运行时依赖包尚未交付。等待用户重开入口采集实际环境，不称网关安装完成。证据 simulation/results/20261115-M-048-runtime-preflight/。

2026-11-15 M-047：生产 816958f 已推送。初始化脚本等待临时地址 Preferred，SSH/SCP 连接超时5秒且只尝试一次，保存阶段/退出码/恢复记录，不保存密码；C窄审和非零状态修复通过。经用户明确授权及Windows UAC，单次实测192.168.137.200经以太网20可ping通、TCP22可连接，ARP B8-27-EB-32-E2-C1；之后已移除临时地址并恢复DHCP，无pending。此前超时根因未确定，未SSH认证、安装或修改网关；现场部署仍待用户运行SETUP_GATEWAY.cmd。证据 simulation/results/20261115-M-047-gateway-connection/。

2026-11-15 M-046：生产 c155295 已推送。网关初始化默认install，唯一符合条件的电脑有线口自动选；远端按目标IP、SSH_CONNECTION服务端地址和有线网口地址唯一匹配自动选。仅保留一次中文回车确认；null和非空输入取消，回滚经显式--rollback。密码说明提前且解释无回显，不保存密码。H少量交互/远端选择夹具与C窄审通过，真实SSH/安装/网络改变未执行。证据 simulation/results/20261115-M-046-simple-setup/。

2026-11-15 M-045：修复初始化脚本错误使用不存在的 ifType 导致有线网口被过滤。生产 e036077 已推送；改读 InterfaceType，保持物理/已连接/有线条件。实际 Windows PowerShell 只读识别以太网 ifIndex20，并排除 WLAN；分类夹具通过，C增量审查无本机误判阻断。证据 simulation/results/20261115-M-045-ethernet-detection/。未运行网关初始化或修改网络。

2026-11-15 M-044 脚本离线交付完成，生产 05d4ca6 已推送：新增 SETUP_GATEWAY.cmd 一次初始化/回滚，START_STUDIO 默认 remote，PC主动发现并核对网关、不绑定本机LoRa接收UDP。网关标准库接收服务采用systemd socket activation，限定专用接口、普通用户运行；DHCP不下发默认路由/DNS。E2真实本机回环、H假Linux/Windows及故障重试测试、C独立增量审查已完成。真实RHF/ARM/Python3.4、systemd215、DHCP、换电脑/断电/RF未实测，本轮未改变现场网络或烧板。证据 simulation/results/20261115-M-044-gateway-deployment/。

2026-11-15 M-043 浏览器续修已交付生产 222dce3：首次/复用入口统一显示 URL，Windows 默认调用失败时尝试备用方式，提示不再声称页面已展示。E2-036/20261115-12-browser-open 五项模拟分支通过，C 独立审查无阻断；M 实际调用系统默认 URL 处理器后检测到 Edge 窗口标题 AD-HOC · 动态组网与业务观测，未做截图验收。以太网现场只读为 169.254.173.200/16，与交接网关 192.168.137.200/24、回传目标 192.168.137.10 不匹配；本轮没有修改网络配置，自动配置仍为建议方案。

2026-11-15 M-043（生产 cf0d303 已推送，C 增量审查无当前配置阻断）：修复 START_STUDIO 在等待网关心跳时不启动完整页面的问题。接收服务 HTTP 就绪即可启动 Studio，未观察到匹配网关仍显示等待连接。随包 Python 的实际子服务临时端口验证通过：页面 HTTP 200、网关未观察到、控制禁用；系统浏览器打开调用成功，未作视觉截图或真实 RF 验证。证据 simulation/outputs/E2-036/20261115-11-offline-ui-fix/。仅改生产 app/start/launcher.py，用户旧实例保留，需关闭旧入口后重新打开。

2026-11-15 M-042：生产app/flash新增console.py，TTY原地限频刷新、非TTY简短输出，退出恢复光标/模式；工作流只新增discovered事件。证据H-022/20261115-10-console-panel，未改烧录算法。

2026-11-15 M-041：生产烧录适配器针对用户五板同报0x45修分区读取后会话重同步及ROM身份复核；进度区分设备序号/串口/阶段、已返回的传输块和最终镜像/启动读回。摘要保留原始错误与unknown，已识别设备失败不重复三轮插拔提示。H-022/20261115-09-session-fix的6项针对性主机回归通过，真实修复效果待用户自行重试，不代刷。

2026-11-15 M-040：部署源码仅app下22个运行文件，服务资源重新定位app/services/assets，固件三文件；运行时和第三方许可证随Git交付，不依赖系统Python。旧production目录仅保留主仓备份；实际最终根FLASH/START --dry-run均0，不代表真实设备或新布局完整回环通过。研究代码/证据仍在主分支。

2026-11-15：M-039实际本机候选包已装配。E1/31默认反馈OFF源码提交a101f8e，H/06身份汇总修复与双CMD dry-run、E2/08隔离实际服务回环、C035有限可测试交付判断均已留证。运行时仅本机随包，不纳入Git；真实WDT/RTC/NVS/RF未验。用户要求自行点击测试，M/H不执行实刷和现场启动。

M-039生产部署分支已初始化；一键脚本/数字ID/OLED/前端正在分配实施，尚未验收。E1主目录固件与E2控制服务冻结后同步生产，不从研发dirty目录隐式加载。当前不做真实串口/网关检测。

M-038：紧急稳定候选在独立firmware/flight_link与tools/flight_link实现，H-021负责唯一硬件通道和试点；尚待交付与实收。研究manet_core不会直接替换板上固件。

M-037新增阶段：新目录manet_core/manet_baselines/manet_eval承载成熟协议复现和新帧候选，当前为已分工未交付。旧uav_adhoc与LoRa结果冻结保留，不代表RF或30板验证。资源/时限按工程合同继续约束，旧4跳不是新方案上限。

## 2026-11-14 当前仿真阶段补充

最新：E1已复用真实固件C核心并交54次诊断矩阵，E2已交12例LoRa仿真；候选收益、模型、deadline和资源仍待工程验收。按M-036工程约定继续算法/模型修正、目标资源预算与大量测试；不能将旧几何原型状态当当前进度，也不能把诊断模拟当实机通过。

进度核对：E1已交几何原型（189快照），协议引擎/配对实验仍未完成；E2已交指标夹具，D/C完成初步资料和语义核对。M-036将原LoRa仿真部分转交E2独占新目录 simulation/uav_lora_control/，E1继续Wi-Fi；未产生新的无线性能结果。

M-036 已分配到既有 E1/E2/D/C：新 simulation/uav_adhoc/ 引擎、simulation/uav_adhoc_eval/ 场景统计、高速需求依据与独立审查。30 节点硬件未到场不阻塞，RHF2S008 网关已具备。首轮 5/25/50 m/s 及相对运动场景尚未执行，不能沿用旧仿真结果宣称通过。先纠正 pending/outbound 时间语义及下行调度理想化；不修改或烧录现场固件。详细交接发现见 docs/PROJECT_STATUS.md 顶部和 coordination/tasks/M-036.md。

状态定义：**【板】**已在真实硬件运行；**【编】**已编译进镜像、未实板验证；**【仿】**仅仿真；
**【未】**未实现；**【死】**代码存在但无调用点。

日期：2026-11-13。审计方式：读源码 + 编译 + 实板 `esptool flash_id` / `info` / `stats`。

## 1 Wi-Fi 控制面（ND）

| 机制 | 状态 | 位置 | 证据 |
|---|---|---|---|
| Hello 2–3 s、ACK 500 ms 限速 | 【板】 | `app_main.c` / `neighbors.c` | 五板 `control_hello_*` 计数单调 |
| 三态 LOST/HEARD/BIDIRECTIONAL、9 s/12 s | 【板】 | `neighbors.h` | `ND_CONFIRM_MS/ND_LOST_MS` |
| 只有双向可作下一跳 | 【板】 | `source_route.c:live()` | 单元测试 + 实板 |
| `ND_PEERS 32` | 【编】 | `neighbors.h` | 编译通过；实板 `route_core_bytes=27144` |
| **ESP-NOW peer 上限 20** | 【未】 | — | IDF 常量；**无对策代码** |
| 移动自适应定时 | 【仿】 | `sim_alg.py` | 固件无速度输入 |

## 2 Wi-Fi 数据面（SR）

| 机制 | 状态 | 位置 |
|---|---|---|
| `SR01` 60 B 头 / payload ≤160 / path[5] / TTL4 | 【板】 | `source_route.h` |
| RREQ 泛洪 / RREP 反回 / RERR | 【板】 | `source_route.c` |
| 200 ms 收敛窗口、候选选最短 | 【板】 | `source_route.c` |
| 路由缓存 10 s + `first_boot` 绑定 | 【板】 | `source_route.c` |
| 交付判据 `rx_local` + 字节一致 | 【板】 | `app_main.c` |
| 表容量 32/32/128/16/12 | 【编】 | `source_route.h` |
| 路由发现令牌桶 4/250 ms | 【编】 | `source_route.c:rreq_take` |
| 待发窗口 250 ms | 【板】 | 长链不足（已知） |
| 扩展环 RREQ | 【仿】 | 未进固件 |

## 3 LoRa 控制面

| 机制 | 状态 | 位置 |
|---|---|---|
| `LRN1` 44+20n+CRC、≤8 行、470 MHz | 【板】 | `lora_ref/runtime.c`、`port.c` |
| 10 s ±250 ms、无 ACK/重传 | 【板】 | `runtime.c` |
| 角色/频率 NVS 自启动 | 【板】 | 实测：复位/重新供电后自动恢复 |
| **8 上行 + 1 下行** | 【未】 | **硬件不支持**（单 LR1121） |
| 调度化上行（TDMA） | 【仿】 | `sim_gw.py`：0.67→0.95 |
| LRN2 / LRC1 | 【未】 | 仅设计（`docs/LRN2_LRC1_DESIGN.md`） |

## 4 移动感知（本轮新增）

| 机制 | 状态 | 位置 | 证据 |
|---|---|---|---|
| Mobility State 抽象 | 【编】 | `mobility.h` | 编译 + 主机测试 |
| 相对位置/相对速度 | 【编】 | `mobility.c:offset_mm` | 测试：100 m/20 m/s 精度 <1% |
| LET 三维求解 | 【编】 | `mobility.c:mob_predict` | 测试：解析值 11.0 s 与实测 10.8–11.2 s |
| 不确定性带 + 置信度 | 【编】 | 同上 | 测试：band 包住估计 |
| 风险三态 + 非对称滞回 | 【编】 | 同上 | 测试：升级立即、降级等 2 s |
| **置信度门限（防振荡）** | 【编】 | `MOB_MIN_CONFIDENCE` | 评估：稳定编队误报 596→0 |
| 链路质量 EWMA/ETX | 【编】 | `mob_delivery` | 测试：干净链路 ETX=1.00 |
| Shadow 记录 | 【编】 | `mob_shadow_line` | JSON 单行，短缓冲拒绝 |
| 评估工具 | 【已运行】 | `tools/mid_baseline/mobility/let_shadow.py` | S1–S6 结果见 `EXPERIMENT_PLAN.md` §4 |
| **接入 ND / 路由** | 【未】 | — | 本轮禁止 |
| GNSS/飞控真实输入 | 【未】 | — | 硬件接口未接入 |
| 节点间移动状态传递（ND02/MT02） | 【未】 | — | 只有 `MT01` 位置（无速度） |

## 5 硬件核查结论

| 项 | 结论 | 依据 |
|---|---|---|
| 芯片 | ESP32-S3（QFN56, rev v0.2），无 PSRAM | `esptool` / `CONFIG_SPIRAM not set` |
| Flash | **实测 4 MB**，但配置 2 MB | `esptool flash_id` vs `sdkconfig.defaults` |
| app 分区 | 1 MiB（余 9%） | 构建输出 |
| 镜像 | 952,640 B（含 mobility.c） | 构建输出 |
| LoRa 射频 | **单 LR1121**，收发互斥、单天线组 | `lora_ref/port.c` |
| ESP-NOW peer | 上限 20 | IDF `esp_now.h` |
| GNSS | **无驱动**；只有 `position_set` 注入与 `MT01` 单跳位置广播 | 代码审计 |

## 6 硬件阻塞项

1. **8 路并行接收不存在** → 需换网关硬件；在此之前按单信道 TDMA 设计。
2. **无 GNSS/飞控接口** → 速度/航向只能注入或回放，不能称实测。
3. **无实测 PDR-距离曲线** → `range_mm=120 m` 是几何假设，LET 不能当真实链路寿命。
4. **实板只有 5 块** → N=10/20/30 只能仿真，或分批拼测。
5. Flash 配置与器件不符 → 需改 `CONFIG_ESPTOOLPY_FLASHSIZE_4MB` + 自定义分区表（会改变烧录流程）。

## 7 本轮实际改动

| 文件 | 改动 |
|---|---|
| `firmware/mid_baseline/field_agent/mobility.h` | 新增：状态结构、LET/风险接口、阈值常量 |
| `firmware/mid_baseline/field_agent/mobility.c` | 新增：相对运动、LET、不确定性、滞回、阴影序列化 |
| `firmware/mid_baseline/field_agent/test_mobility.c` | 新增：26 项主机测试 |
| `firmware/mid_baseline/field_agent/idf/main/CMakeLists.txt` | 加入 `mobility.c/h`（编译检查；未被引用） |
| `tools/mid_baseline/mobility/let_shadow.py` | 新增：合成轨迹生成 + LET 评估 |
| `docs/*.md` | 新增七份规划文档 |

**未改动**：`app_main.c` 的路由逻辑、`source_route.*`、`neighbors.*`、
`lora_ref/*`、任何线上帧格式。**五节点基线的行为与上一版完全一致。**

## 8 回归验证

| 项 | 结果 |
|---|---|
| 主机测试 `test_mobility` | 26/26 通过 |
| 固件编译（全新构建目录） | 0 warning / 0 error，952,640 B |
| 构建 ID | `mid-lora-ref-v1-111f2d676bab352fdf0839e0e55614ea293dfe08568e6fab4ab36275a37a5f23` |
| 镜像 sha256 | `44d45eae6b5363c45797b1480f95e3f89cd4d9f2bad91895b4313a76f34e997d` |
| 链接器符号 | `nm` 查无 `mob_*` → **模块被链接器整体丢弃**，镜像字节与体积不变 |
| 五板运行基线 | 未在本轮重新烧写（mobility 无调用点，行为不变） |
| LoRa 拓扑 | 本轮未重测（硬件能力未变） |

> 说明：`mobility.o` 编译通过但未被任何代码引用，链接器按需丢弃，因此
> **固件体积与行为与上一版完全一致**。这是本轮刻意选择的接入方式：先证明模块可编译、
> 可测试，再在 P2 用开关接入 ND，避免在无验证的情况下改动稳定基线。

## 9 后续修订（同日，用户确认后执行）

| 项 | 状态 | 证据 |
|---|---|---|
| flash 改为 4 MB + 自定义分区表 | **已完成并实板验证** | app 分区 4032 KB（余 77%）；NVS 偏移未变，五板 group/ch/LoRa/autostart 全部自动恢复 |
| 事件输出改为非阻塞 | **已完成并实板验证** | 60 s 无人读串口：4/5 板块 `input_overflow_total` 增量 **0**（修复前 +30…+62） |
| E 板仍周期性溢出 | **未解决** | `uart_tx_drops=0` 排除输出阻塞；`send_callback_timeouts=9` 最高；处理耗时正常 → 待抓帧型分布 |
| 八通道网关 | **待采购** | 规格见 `LORA_GATEWAY_REQUIREMENTS.md` |
| 真实移动输入 | **仍缺失** | 无飞控/GNSS 接口；LET 继续只用合成/回放数据 |

当前板上固件：`mid-lora-ref-v1-2267bc60…`（见 `BUILD-20261113-4MB-notxblock/BUILD.md`）。
