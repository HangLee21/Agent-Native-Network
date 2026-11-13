# 五板真实日志离线回放

双击`index.html`即可打开；全部数据、脚本和样式均内嵌，不需要服务器或网络。`five-board-four-hop.svg`是组会静态图。页面默认打开chain_ABCDE，可播放/暂停、切12场景、按包/主机观察时间拖动、点选节点查看实际下一跳和当前观测计数。事件表每行可定位到原文件行号及原始事件字段。

数据来自H的`simulation/outputs/H-005/20261107-06-AB-RF/`至`20261107-17-chain_BADEC-RF/`十二份native.jsonl，身份/payload/完整链依据E2的`simulation/outputs/E2-016/20261107-05-real-five-review/identities.json`。现有批次120条目的交付、20条受控四跳均有E2核对。不是新实验或动画合成性能结果。

`replay-data.json`是可读派生数据，保留原host_monotonic_ns、设备事件monotonic_ms、文件与行号。页面t相对每个场景首条host记录；设备本地时钟不能跨板相减。串口缓存/采集顺序可能让接收先于提交被主机观察，页面不人为重排因果、不模拟包的空口飞行。节点位置为示意，不是物理坐标。粗实线为本包已经观察的tx_submit，虚线为E2核定但尚未走到对应观察时刻的路径。

节点计数为回放到此时的实际数据tx_submit、目的rx_local、中继rx_relay，包含转发提交，不能当作源唯一业务包数。到达时刻是目的rx_local的主机观察时刻，不是单向链路时延。MID源无目的ACK，源端未确认与电脑汇总到目的日志是不同事实。无接收时显示缺失，不补造成功；本批次没有目的缺失。

168.424994秒是12段host控制窗口合计，不是PHY airtime。两条受控四跳的逻辑邻接不代表物理RF隔断或覆盖收益。RTT/RF重试/airtime及package-03五板完整像素/PRG观察未知。既有三板报告与原始日志均未修改。

`build_replay.py`只读历史数据并生成本目录资产，不接触串口或运行求解器；`replay.template.html`是页面源。当前120包数据保持原批次，不代表动态恢复实验。新增M-019中继替换对照另见[实测对照页](replacement/index.html)，已接E2第1–4对8臂统计，第4对fixed未知覆盖保留，第5对待E2。该页可播放时间游标、切方向、按包查看来源，并导出配对曲线PDF/SVG；详情见[对照页说明](replacement/README.md)。

本机Chrome实际检查了默认四跳、12场景、逐包选择/拖动、时间拖动、节点选择、播放推进和最终收到计数。证据在`simulation/outputs/D-016/20261107-03-final-preview/`。Playwright CLI因npm DNS不可用未启动；最初沙箱Chrome因crash server失败，原记录保留01号，获准以任务独立浏览器目录完成离线检查，无依赖下载或设备操作。所有检查命令已退出，无本任务服务器或后台等待。
