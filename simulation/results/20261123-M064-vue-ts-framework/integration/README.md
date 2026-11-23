# baseline 主目录集成复核（2026-11-23 19:47–19:51）

在隔离 worktree 验证完成后，仅用 fast-forward 将 `3b843af` 集成到原 baseline 分支，未切换主目录分支、未合并两个无关仓库历史。

- 集成瞬间 17 份原未提交文件（含当前任务卡）逐字节 SHA256 完全相同；后续仅在授权范围内更新本卡/共享摘要，不夹带其余 16 份工程卡。
- 初次归档的 15 个文件校验值在主目录 checkout 后全部一致，原归档/原始 manifest 不改写。
- 主目录独立执行锁定依赖安装，231 包从缓存安装；再次完整跑过 59 文件/450 测试、类型检查、三入口生产构建。
- 预览从 `D:\Multi-Agent Network` 主目录启动，而不是旧隔离 worktree。新 Edge 上下文访问 Studio，确认默认断开、0 后端读取、0 页面异常、0 意外请求。
- 只运行 real-only 10518；没有测试 Mock/静态服务监听。原采集/工程入口不替换、不主动重启。
- deploy 保持冻结；ControlSystem/lh 不反写。未做设备/无线/生产部署验收，也不是 C 独立审查。

## 文件

- [本次初始运行清单](RUN_MANIFEST.json)
- [集成与未提交工作保护](INTEGRATION.json)
- [主目录测试/构建汇总](FRONTEND-MAIN-SUMMARY.json)
- [主目录完整测试/构建输出](frontend-main-regression-build.log)
- [主目录真实预览检查](MAIN-REAL-PREVIEW.json)
- [最终受保护路径核验](FINAL-SAFETY.json)
- [本组校验值](ARTIFACT_SHA256.json)

原始测试 JSON 等记录留在本机 `simulation/outputs/M-064/20261123-194758726540-integration/`。本子目录有独立校验清单，不修改父目录初次验收的校验清单。后续只在 baseline 前端开发；按 [迁移说明](../../../../docs/BASELINE_FRONTEND_MIGRATION.md) 受控回传 lh，deploy 另行充分验收后才允许同步。
