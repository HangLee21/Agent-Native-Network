# M-064 第一阶段：lh Vue+TS 框架迁入 baseline

来源：ControlSystem/lh `bdadc989decf4d383b49dff2def4aa1aa0aa59b5`；实现提交 `ab12ebf17d553187d0c95b0b4c05341c1c9ebe1f`。349 个已提交源文件导入，未导入 node_modules/dist/Java 后端/现场日志数据库。框架源码成为 baseline 后续开发源，deploy 冻结。

## 软件验证

- 完整 Vue 测试：59 文件、450 测试通过；类型检查和 platform/studio/mock-studio 构建通过。
- Native Node Mock/只读网关桥：18 通过。
- 同步工具：13 离线文件系统/Git 测试通过。
- Edge 158 合成浏览器：21 项通过，0 页面错误、0 意外请求；48 次 real-mode 请求由测试夹具拦截，绝非现场实测。
- 测试文件仅清理上游 EOF 空白后，joint-replay 5 项补跑通过，不改逻辑。
- 最后启动 real-only 10518 预览，独立新浏览器上下文确认默认断开、零 API/桥读取；10519 无 Mock 监听。验证用 Mock/静态服务已结束，旧现场服务未主动停止。

## 证据索引

| 内容 | 文件 |
|---|---|
| 汇总与明确限制 | [SUMMARY.json](SUMMARY.json) |
| 初始运行清单（原始字节保留，开始时的 running 状态不代表最终未结束） | [RUN_MANIFEST.json](RUN_MANIFEST.json) |
| 前端完整回归、类型、构建输出 | [frontend-regression-build.log](frontend-regression-build.log) |
| Native 网络软件测试 | [network-node-tests.log](network-node-tests.log) |
| 同步工具测试 | [sync-tool-tests.log](sync-tool-tests.log) |
| 21 项浏览器检查 | [browser-REPORT.json](browser-REPORT.json) |
| 最终 real-only 启动检查 | [REAL-PREVIEW.json](REAL-PREVIEW.json) |
| 版本与依赖环境 | [VALIDATION_ENVIRONMENT.json](VALIDATION_ENVIRONMENT.json) |
| 只读 lh 计划（1 add/2 update/347 unchanged/0 conflicts，未应用） | [lh-sync-check.json](lh-sync-check.json) |
| 旧工程路径/部署 refs/Control 工作树保护 | [SAFETY-CHECK.json](SAFETY-CHECK.json) |
| 归档文件校验（不包含校验文件自身） | [ARTIFACT_SHA256.json](ARTIFACT_SHA256.json) |

日志是原本机运行的 UTF-8/LF 可读派生副本；原始运行文件未覆盖。原始目录 `simulation/outputs/M-064/20261123-165227286-framework/` 还保留 PowerShell 将 stderr 警告当终止错误的一次前端采集，以及一次宿主 Git CRLF 夹具断言失败；没有把这些尝试算成通过。构建仍有既有 Vue 注入警告和大块提示，未声称已做性能优化。

## 截图

- [真实入口默认断开](screenshots/real-disconnected.png)。无节点、无后端数据。
- [TEST ONLY：旧网关协议适配](screenshots/TEST-ONLY-local-gateway.png)。**拦截合成夹具，非物理网关**。
- [TEST ONLY：平台共享 Network 路由](screenshots/TEST-ONLY-integrated.png)。**拦截合成夹具，非现场平台接入**。

## 边界

原 START_STUDIO/采集/来源选择/SQLite 持久记录回放/恢复/做卡/USB 与远程刷写/机群等保留。新 Vue 尚未完整接入旧工程来源管理与持久回放，不切换旧默认入口。ControlSystem 本轮只读，没有实际回传，deploy 不改不推。

这些是实施者的框架导入与本地软件自测，**没有 C 独立审查、硬件/无线/完整工程能力验收或生产发布许可**。迁移范围与后续流程见 [迁移说明](../../../docs/BASELINE_FRONTEND_MIGRATION.md)。
