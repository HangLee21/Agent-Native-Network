# M-064 默认启动器切换（2026-11-24）

用户在真实网关接入验证后明确要求：新前端作为默认 CMD，旧启动器保留但不默认。本轮按此实施，不把入口选择当作工程功能齐全或生产验收。

## 入口

- [默认 START_STUDIO.cmd](../../../START_STUDIO.cmd)：baseline 开发树进入真实 Vue Studio，默认10518；已验证同根 real-only 预览则复用，仅打开新UI。
- [旧 START_STUDIO_LEGACY.cmd](../../../START_STUDIO_LEGACY.cmd)：原默认文件逐字节副本，显式运行时保留原工程启动行为。
- 原始SHA256：`40074f56fdfcb569a0902bc7fe0bcb83c3c98eb58df39944f4888494b7b2dbcf`。单路径Git属性禁止行尾归一化，保留该字节身份。
- 旧交付包的 app/start/launcher.py 分派仍保留，未迁移deploy。

## 行为与边界

默认通过 [适配器](../../../tools/release/start_vue_studio.py) 启动。已有8780和8794服务通过schema识别后复用，不重启；缺失服务才委托原后台启动入口，并固定 `--no-browser --skip-lab`，不打开旧UI、不改网卡/触发提权。

已有10518预览必须同时满足baseline来源、当前checkout文件系统标记、真实网关桥与Mock未启用；陌生服务、其他checkout或Mock实例不复用、不杀。冷启动仍使用现有新真实前端CMD，用户需保留启动窗口。页面默认断开，需要显式选择网关并连接；无GPS使用清晰布局。

## 本轮验证

- **29项通过**：16项启动器测试、13项既有同步保护测试。含CMD路径空格/`&`/`!`、中文参数、参数转发、退出码23、无Vue文件的交付包分支退出17；实际执行无害CMD替身，未启动设备服务。
- 实际从父目录运行默认 `--which`、旧入口 `--which`、默认 `--no-browser` 均退出0；最后一项明确打印现有后台和real-only10518复用，不打开浏览器。
- 原PID保持：8780=39744、8794=38492、10518=5320；没有新Mock监听，没有重启网关/节点。
- 原旧CMD与运行前快照的原始字节完全相同；349个导入文件与旧后台代码本轮未改。
- 测试未实际停掉现场服务做冷启动，冷分派使用离线替身验证；没有声称另跑450项Vue测试或完成独立C审查。

原始运行目录：`simulation/outputs/M-064/20261124-111454595658-default-launcher/`。初轮28项通过后增加真实冷CMD分派用例，最终29项通过，两个结果均保留。

证据见 [最终测试结果](UNIT-FINAL-SUMMARY.json)、[最终逐项日志](unit-tests-final.log)、[实际CMD冒烟](cmd-smoke.log)、[完成记录](COMPLETION.json)、[字节清单](ARTIFACT_SHA256.json)。源码快照仅供比对，不从本归档目录直接执行。

现场3号未报告、4号间歇、原来源管理/SQLite/业务证据等Vue缺口保持原判定，见[现场验证](../20261124-M064-live-frontend/REPORT.md)。新默认不删除旧数据或工具，不推送Control或deploy。
