# D-015 阶段2接手记录

2026-11-06。按`coordination/handoffs/M-018-stage2.md`接续原任务和预算；不重做来源审计，不改`SOURCE_AUDIT.md`及01号来源冻结副本。

## 已生效的工程取舍

- 采用miod `d4ba825cb2068301f7811e522c4cc44092796e1e`候选行为，名称为“作者候选实现的ESP-NOW适配”；最终TRO实验版本/原始数据关系继续未知。
- SOCP依正文集合A采用axis0/axis1入向/出向两组约束；目的跳过、sqrt方差按已核作者实现；输入参数显式给出，未校准不称物理QoS达标。
- 累计权重每500ms抽样并保持，首次命中结束；完整(src,dst)索引为显式修复。原Bernoulli文字、缺break探针、Linux内核未执行等边界保留。
- 原发送者/递增seq去重并转播；已有boot/TTL/容量/编码是承载适配；不加ACK提交或新可靠协议。
- 先推进A/B新MID配置和真实数据交付，不等待五板；两板结果不能证明多跳或移动恢复。

上述决定由M阶段2文件给出，D记录供操作页使用，不代替C独立审查。

## 本次消费的H冻结与设备记录

| 输入 | 版本/证据 |
|---|---|
| 显示FREEZE | SHA256 `2d72ee784757d881a6b77108bf886e5e6e0591934c94693d5baee0330e4da9aa` |
| module_id | `mid-display-v1-b24c8b169a99853226218df2130c028a8f1b648db2d1f3dd6428a6c8d2724ec0` |
| 核查 | 27项冻结文件hash本次全部匹配；包括6项生产文件。仅hash/文档核查，没有重新运行H程序 |
| 状态 | H原冻结为`frozen_for_read_only_E1_integration_host_verified_only`，独立对象尝试曾WinError623；随后E1实际目标链接已交付见下节，新显示实物仍待H证据 |
| 显示操作 | 六页；PRG40ms只切页；缺失字段保留未知；MID源UNCONFIRMED，目的DEST RECEIVED；帮助由E1真实CLI提供 |
| A | MAC `90:da:72:48:a4:f8`，当次COM7，原USB location1-2；旧ANN/OLED证据保留 |
| B | MAC `90:da:72:48:a5:cc`，当次COM8，ROM核S3/4MiB；应用/备份及新MID按H后续固定交付核对 |
| C–E | 未连接/未绑定，保留未知 |

连接状态以`hardware/mid_baseline/BOARD_INVENTORY_20261106_AB.json`及对应LABELS更新为准；原`BOARD_INVENTORY.json`是显示冻结27文件中的历史清单，保留不改。D不操作设备，也不把A重枚举说成本次重新读取A MAC。

## 初次阶段2交接安排（历史）

E1正式冻结时需定向通知D：接口、包/源码hash、真实CLI/help及完整事件样例、适用A/B身份、构建证据、限制。D按指定版本核hash并补操作页，不读取E1正在编辑的实现作为最终合同。H完成有限A/B后，由其向E2/C/M交接实际证据，D据冻结结果更新“实际运行/未验证”页；新OLED像素观察、I²C成功和RF交付分开。

本次指南guide-0.2先补齐H显示、A/B状态和M取舍；未提前编串口命令。完成正式操作页后，D按本轮用户授权主动通知C/M并携带文档冻结hash，不只落卡。没有交付变更不催办、不轮询、不后台等待。

## E1检查点2正式包接手

E1已定向交付`package-01`，D核包manifest SHA256 `d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683`、E1 FREEZE `95e7499f8e5c1469af4a36b29b52e5522a44bf9e19a17497df559dd58d686f40`；52件包文件长度/hash、13件E1源码hash、H生产6件hash均匹配。INTERFACE hash `689b8cc1d4f96e805563c2e0459029ad02e033a32d487537b32e36b16f201bf2`，build为`mid-v1-99e77eba7e472bd687ea18321d6ac566e9e8b21d764431e1b42ec7fee945c2f3`。D未重跑目标编译或打开设备。

据此补齐guide-1.0 [package-01完整操作页](USER_GUIDE_PACKAGE01.md)，`USER_GUIDE.md`改为当前入口；guide-0.1/0.2原字节仍在01/02号证据。包括真实write_flash @flash_args、A/B info身份、本次A boot共同绑定、bridge/publish参数、配置实际采用/有效下一跳、双向send、stats、OLED及stop排空。明确publish和其他采集器不能同时占A端口；EXPECTED_EVENTS是预期合约样例，无实板观测。

E1已经实际求解E2的A/B假设输入，network_update SHA256 `db11092bb00a3b80ef76dbf30eea15cb9d5755836a7bd58b52e8d8d2944e79c2`；D核hash与双向流定义，未重复求解。E2先前disabled/native=null草案不直接执行，须按最终native配置与C对同包的就绪结论由H执行。后续H/E2/C固定A/B结果到达后再回填实际统计/显示观察；本操作页不提前填成功或放行结论。

本次完整输入核验、文档固定副本/hash及公共manifest存`simulation/outputs/D-015/20261106-03-package01-guide/`。文档交审后一次通知C/M，带完整指南和证据hash，不增加轮询或后台等待。
