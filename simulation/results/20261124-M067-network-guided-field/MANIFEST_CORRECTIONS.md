# 阶段字段补充说明

主运行 `RUN_MANIFEST.json` 和各档的冻结配置 `config-nNN.json`、各档 `config.json` 均正确记录 `phase: 4`。各档 `nNN/RUN_MANIFEST.json` 中的 `phase: 1` 是复用分阶段执行器时的常数字段错误，不表示运行了 Phase 1：应以各档配置中 `phase: 4`、节点数、种子、运行日志、策略和数据快照确认阶段。此补充不改写原 manifest 或任何结果数据。早期单独 pilot 各自的 config/目录和标签仍为其本来阶段；后续复跑应修复脚本使 manifest 跟随配置。
