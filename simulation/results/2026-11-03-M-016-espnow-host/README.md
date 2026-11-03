# M-016 主机实现与独立验证证据

本目录保存到货前的协议代码、主机测试和审查证据。没有无线实测数据。最终验收状态以 [M-016 核验记录](../../../coordination/reviews/M-016-verification.json)和 [C-017 审查](../../../coordination/reviews/C-017.md)为准。

| 当前证据 | 来源 | 结论 |
|---|---|---|
| 同一 C 核心主机执行 | E1-014/20261103-09-lifecycle-fixed | 12 场景、6200 断言，另 164 生命周期断言及 3 个原审查反例通过 |
| 独立真实 C/console 检查 | E2-015/20261103-13-final-core-contract | 20 项通过，含 100 条连续事务与旧副本重放 |
| 分析器 v2 回归 | E2-015/20261103-15-analyzer-v2-regression | 44 项通过；C 另作 8 项独立 API 检查 |
| H 采集与分析主机工具 | H-001/20261103-18-final-v2-regression | 35 项通过；17 号运行保存实际 C → H Capture → v2 API 互验 |
| 独立实际 H Capture 互验 | E2-015/20261103-17-final-H-capture-independent | 6 项通过；C 另作 7 项 H 检查 |
| 到货检测入口预检 | H-002/20261103-01-preflight | 退出 0、打开串口 0、waiting_hardware、六项实际测量全 null |

各行是不同套件，不能累加为射频样本。实际 C 指桌面编译运行相同协议核心；不代表 ESP32-S3 目标构建、无线调用或板卡通过。旧版 6208 断言、v1 分析器以及修复前反例均保留为历史，不代替上述当前版本。

## 归档与复现

- ARCHIVE_INDEX.json 将原 simulation/outputs 路径映射到本目录，记录复制时的 SHA-256 和字节数。复制保留原字节，原输出未移动或删除。
- E2-015/analyzer-v1-source 是撤回版本；当前接口在 analyzer-v2-source。H-001/final-v5-source 保存最终实现快照；后续仅 README 文档修订另记，代码版本不混用。
- 不归档生成的可执行文件、构建缓存和无关本机串口清单。manifest 保留二进制摘要；本机清单摘要列在索引的 local_only_sources。ESP 源配置 sdkconfig.defaults/Kconfig.projbuild 已补入对应源码快照。
- 原 manifest 的路径/字段未改写为归档路径。早期 H 只有日志与源码 hash 的版本不由当前源码猜补。旧 manifest 缺项及不一致由 E2 RUN_INDEX 的补充映射说明，保留原字节。
- 累计执行 ledger 是复制时快照；最终累计账本另存，不能用后续追加覆盖早期归档。审查产生的失败、修复及后续通过各自留存。
- 源码与执行入口见 [固件](../../../firmware/agent_native/README.md)、[独立测试](../../../tests/espnow/VALIDATION.md)、[硬件工具](../../../hardware/eora_hub_400tb/README.md)及[台架说明](../../../research/agent_native_network/espnow_20261103/README.md)。复现使用新 run-id，并先取得对应任务卡的执行范围。

真实 PDR、Goodput、RTT、距离、RF 重试与 airtime 依赖后续硬件来源；本目录 synthetic 数据不得填入实测台账。
