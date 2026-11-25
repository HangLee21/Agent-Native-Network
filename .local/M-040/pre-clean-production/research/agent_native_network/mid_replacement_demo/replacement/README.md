# 中继替换实测对照

双击index.html即可离线打开。切换配对、业务方向和实验臂，拖时间游标或播放；计划包下拉框可定位具体slot。每秒表、逐包身份/接纳/目的匹配、实际事件和原始日志行号分开显示。目的收到和游标之后才发生的接收均保留实际host时刻，不把图中时间当作空口延迟。

当前使用E2正式首对09-pair01-audit、其余11-pairs02-04共8臂分析，1920个设计计划包、960个每秒方向窗；直接读取现成packets/seconds/annotations/directions，不重跑分析器或原始采集。H最终10臂状态另表显示，四个完整采集配对为1/2/3/5；当前E2完整对照为1/2/3，第4对fixed不完整，第5对待E2正式统计，不能把二者合成同一个N。

第4对fixed的unknown窗口严格保持null，图中不补0；H观察到的62条接收仍留在采集索引表。故障后独立stop不回填业务覆盖。恢复直接显示E2的连续3个1秒窗/基线80%结果，右删失不写成已恢复时间，不求删失恢复均值。没有跨配对平均、置信区间或显著性推断。

`paired-service.pdf`、SVG和PNG是Matplotlib直接从E2每秒数据生成的分面图，各配对/方向独立，蓝虚线为固定旧表、橙实线为现场重规划、淡色区间为真实求解窗口、点线为重规划臂真实退休生效、斜线为固定臂unknown。单页研究展示导出，不表示期刊投稿已验收。共同条件为同桌天然直达、controlled逻辑图、软件停C启E；不能外推自然掉线、移动、覆盖、容量或校准QoS。

来源路径和摘要记录在sources.json及内嵌DATA.sources，viewer-data.json含完整派生展示数据；E2引用的H原日志/上下文路径和hash保留。第5对正式分析到达后，把明确交付的两个E2文件加入sources.json，再使用全新run-id构建；不要扫描最新目录自动择样，也不要重复分析旧run。

从仓库根目录重建（输出目录必须不存在）：

```powershell
.venv/Scripts/python.exe -X utf8 research/agent_native_network/mid_replacement_demo/replacement/build_view.py --run-id <新的D-016运行名>
```

依赖已有Matplotlib环境，完全离线，不操作设备。该脚本生成新simulation/outputs/D-016/<run-id>/后更新本目录展示资产；历史构建目录不改写。最终构建09-replacement-timer、浏览器17项操作检查与180mm静态图预览在10-replacement-browser-final；早期播放检查失败06/08保留，定时播放修复后通过。没有服务或设备后台进程。
