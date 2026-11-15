# 生产部署状态

2026-11-15：已装配本机可测试候选candidate-20261115-default31，实际manifest在production/release/candidate-20261115-default31/manifest.json；默认反馈关闭，源码a101f8e108be239dccc1a776f741ac1ecfa33163。FLASH_NODES.cmd及START_STUDIO.cmd均已用真实CMD完成离线dry-run（H-022/20261115-06-summary），未代用户烧录或启动现场服务。默认fleet在production/local，沿用5板组31/频道11；Windows运行时在production/flash/runtime-win64-py311随本机交付、未纳入Git。Git源码下载本身不包含该运行时或本地fleet。网关接收/拓扑展示启用，下行控制未配置而禁用。候选仅供用户点击实机测试，真实烧录、断电、WDT/RTC/NVS及RF仍未验收。以下为历史阶段记录。

2026-11-14：codex/production-deployment 独立分支已建立，起点f304632，部署脚本/数字ID/前端正由H/E2/D实现。此提交仅初始化生产合同，不表示一键工具或新固件已经可用。

用户2026-11-15接串口，今天仅离线软件工作；不检测设备。算法候选在研发分支冻结后由M选择性同步，硬件验证前只标candidate。正式入口为FLASH_NODES.cmd和START_STUDIO.cmd。实时进度见主目录coordination/tasks/M-039.md。

H-022已回填离线阶段：FLASH_NODES.cmd及发布工具已编写，H报告4项合成测试和fixture dry-run通过（主仓simulation/outputs/H-022/20261114-01-offline/）。M已核对任务卡；尚未独立审查实现。真实执行当前在枚举串口前阻断，仍缺真实设备适配、数字ID写读及分区核验；不能作为已可实刷版本。M已将接口依赖通知E1。启动入口与前端仍待各负责人交接。
