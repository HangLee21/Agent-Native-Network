# 候选作者行为：独立来源与探针

只核danmox/miod提交`d4ba825cb2068301f7811e522c4cc44092796e1e`，不声称它对应TRO六组最终实验。未下载较新mid模块，也未直接校对论文全文/数值求解，版本和论文公式关系交D/E1后续冻结。本轮资料从公共GitHub只读取得，存.local/mid/E2-016/author，不对外发布许可未确认源码。SOURCES.json记录7份原字节文件、URL与SHA256；检验前逐hash核对。

| 已核候选代码 | 独立结论 | 对适配的要求 |
|---|---|---|
| [main_cli.py](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/src/main_cli.py) rt_update_thread；main_srv.py local_rt_update_thread | 0.5秒循环；coin在0至权重总和，累计阈值命中后无break。独立调用实际client函数AST：权重0.5/0.5、coin0.25会先尝试g1再g2；coin0.75只尝试g2。fake subprocess全部返回2，函数不检查失败也不抛出 | 只证明命令尝试，真实Linux路由最终状态未测。单次类别抽样加break是需要披露的最小执行修复；不能把最后一次尝试等同实际生效，也不能改成每包路由 |
| [main_srv.py](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/src/main_srv.py) global_rt_update_thread | 实际函数AST收到相同node/src、不同dest两条ROS列表，最后只保留第二目的。rt_update_sub输出本来含dest；丢失发生在字典转换 | 对等任意src/dst单流与同源多目的并发分别验收。若改为三元流键须写ADAPTATION，不称作者原转换支持 |
| main_cli.py status_receive_update_thread | 首份和更大原发送者序号接受并重播原始bytes，重复/旧序号不播；不同UDP中继地址不创建新源。内存socket输入4/4/3/5，实际转播4/5 | ESP-NOW保持原发送者/原控制序号，不拿中继MAC作原源；代码无boot字段，重启回退问题不能宣称无条件解决 |
| main_srv.py status_send_update_thread | 默认period=1秒，非空路由表广播[HOST,seq,routing_table]至10.42.0.255:54545 | 配置广播周期与0.5秒路由执行周期分列；不能以收到控制表等同选路已生效 |
| [rr_socp.py](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/socp/src/socp/rr_socp.py) cone_constraints | 源码直接跳过每流目的节点；a系数对入/出rate_var开平方；源需求、出正入负均值、对角零及F序布局可定位 | 本轮仅静态核对，未运行CVXPY/残差/优化解；目的约束/方差与论文区别待D确认 |
| [channel_model.py](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/socp/src/socp/channel_model.py) PathLossModel；net_patrol.launch；network_planner.py | PathLossModel默认b=6.0，方差(a*d/(b+d))²；net_patrol显式/b=0.6，Planner从参数传b至路由solver及位置模型 | 不把类默认当具体实验配置；后续冻结输入要带参数覆盖链和实际位置/距离单位 |

AST探针只提取指定函数，不import作者模块（main_cli/main_srv会在顶层调用main并涉及OS/网络）。subprocess、UDP socket、ROS子进程、随机输入与停止条件全部为内存替身，没有执行ip/route、UDP广播、无线、ROS或优化求解。探针观察对应源SHA，不能当MID固件通过或真实RF结果。

首次网页抓取cache miss，沙盒直连报WinError10013；之后通过受审查的只读网络取件成功。没有安装环境或运行外部作者入口。失败说明保留在本报告和E2任务记录，不据抓取失败伪造来源。本轮只把能直接验证的候选行为交接，不擅自扩展baseline机制。
