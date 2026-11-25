# NATIVE-01最小修复交接

只修改native.py两跳证据判据：每个已收identity必须有源node的tx_submit，next_hop=required_relay，origin/origin_boot/seq/dst精确相同；source_tx_submit原文件行号加入relay_evidence。源排队、源MAC callback均不能替代。其他物化/包/场景/固件未改，H已许可执行无需等待本修正。

本轮仅test_native01.py的3项针对检查通过：完整四段链为true且保留源行号；分别删除源tx_submit、中继rx_relay、中继tx_submit、目的rx_local均false；源seq/boot/dst/next_hop错配均false。测试是明确SYNTHETIC/OFFLINE_ONLY反事实标签，未导出假硬件结果。用mock跳过不相关的既有package verify，没有重验52件/13源码、构建、原OLED/核心或物化套件。

输入为C-018 NATIVE-01的最小要求；旧source hash acb92c631734cbf38df120822bb4df0c3154c9e5e0f65f7af5bd39db4d922530是修复前版本，先前FREEZE/报告是相应历史检查点。本文件是增量交接，不增加H执行审批或冻结链。

- tools\mid_baseline\validation\native.py SHA256 18ec0a4d2e55d66349d2ed08607ba9919e5471b9f32de5322893939dc917eb5d
- tests\mid_baseline\test_native01.py SHA256 42f02c79ff5092a8d1dddf70dc097489544c20ba558598287b393d1599ed7713
- simulation\outputs\E2-016\20261106-11-NATIVE01-targeted\result.json SHA256 165e7e2a775d70f7e22cd457e231d3dd7a0efb1e41fae10b8b81dad283eaa57d
- simulation\outputs\E2-016\20261106-11-NATIVE01-targeted\RUN_MANIFEST.json SHA256 9829b629a5fdf205ff1d468dc10a41038d0a07163fb61d2fa4718bf75542a4cf

所有命令退出，串口/Flash/RF0。本次0.532秒、累计21.721秒，原失败和manifest不改。只交C复核本增量；H继续既定实测，收到原始数据再分析，不轮询。
