# E2-020服务交付

实际服务：http://127.0.0.1:8767/ ，session10193保留，双击tools/mid_sim_console/START_SIM_CONSOLE.cmd。只使用软件仿真，不访问8766或串口。D的正式编辑页同源提供；/api/catalog、预设/default/validate由H实际库给出，真实worker导入E1 runner/pair.py:run_pair，120秒墙时/数学库2线程。具体API见CONTRACT.md。

正常页面由D实际操作产生的两个新运行（E2没有并发重跑）：

- 默认20261107-173556-90c9d26a4dff：两臂各240生成，目的唯一234/234。
- 自定义20261107-173633-a3ae97cee5e0：AC/CA在[20,40)断开，CD/DC同窗750ms；目的唯一fixed175/adaptive226。不是预录曲线。

这两次的settings/scenario/experiment固定，源计划/初表/设置hash两臂一致；E2独立核原始destination_rx/payload和实际传播。与默认同包/同边/同服务开始对齐，fixed40个、adaptive5个实际arrival后移0.74秒（750−10ms），发送至到达严格为序列化+本次传播。证据simulation/outputs/E2-020/20261107-03-browser-run-intake/，原始两run不修改。结果页/results/<id>/由实际本次事件生成曲线、逐时刻接收路径及冻结设置，不用候选路线填实际记录。

13项真实HTTP/输入安全检查通过（01-service-checks），未启动模拟。另在隔离registry下取消一个真实新子进程（02-cancel-check，子run20261107-174006-c99a8bae9527）：取消/退出、busy拒绝第二run、重复取消幂等通过；没有进入两个正常样例或主页面历史，也未干扰D reset计数。取消先设flag供E1保存partial，两秒未退再kill；state为cancelled，不变成成功。

打开、预设/草稿/reset/validate无运行副作用，旧run结果绑定自身settings不随草稿改变。D负责最终真实浏览器reset/键盘/导出与视觉验收；E2只消费D产生的新运行及原始事件，不替代D/C报告。当前后台仅本机服务，子进程已结束；无硬件、旧M021重跑、无限任务队列或监控。C/M独立验收待接收，本卡不自行done。跨聊天受限时按主卡与本文件交接。
