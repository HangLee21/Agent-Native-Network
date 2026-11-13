# D-024 分机邻居界面对接

已接E2-025正式同源只读接口：GET /api/edge/neighbors、GET /api/edge/nodes/<MAC>。监测指定MAC优先后者，不逐个遍历探测；UI不调用主动RF复核。邻居数组为neighbors，单节点原回执内为neighbor；node_id/boot_id/state/age_ms/last_seen_ms/last_confirmed_ms来自E1固件，unknown可仅有state。

邻居显示需要实际MAC、可选名称、对方boot、上次本板接收时刻（单调时钟应标明单位）、接收年龄、明确双向确认/超时状态。未知、单向听到、双向确认、超时不能混淆。历史ABCDE名称不能成为实际发现证据；未知MAC也能出现在目的列表。发送保留实际MAC/载荷/request_id和未知禁重发。

分机主屏显示本板与邻居，旧台架图收在“历史台架图”中，标签明确不是当前邻接。切换目的/关注节点使旧异步状态响应失效。监测由用户显式点击，每2秒读取所选本板记录，5分钟自动停止；不启动所有邻居扫描。读取失败或本板断开时停监测、禁用未确认发送，不把旧绿色状态当实时证据。

Ubuntu指南已按E2真实install/uninstall/服务命令和E1正式发现包填写。旧预配置ABC多跳与自主一跳发现分开说明，旧RF/同PC记录不充当Ubuntu物理拔插实测。

当前E1状态是heard/bidirectional/lost，对应单向收到/双向确认/超时。本板clock以ms显示，不换成跨板UTC；页面按查询时age与经过时间推算9秒确认过期、12秒未见，推算的状态带“按上次记录”。发送时单独读取所选MAC；未确认、读失败、本板radio=false或fault均禁发。新名单外MAC可选；名称先用原生device_label/label/name，再按实际邻居MAC匹配本机status.labels（缺失时snapshot.labels）；均缺失才显示“未命名设备”。标签仅装饰已读取的真实邻居，不从旧ABCDE图推造节点或无线关系。

sender.js同一资源集成邻居组件，没有新增脚本依赖。分机操作固定真实本板；硬件连接状态按钮改读edge/status，服务和板断开时保留分机模式并显示未知，不能自动降成台架。status当前fresh info为本板只读查询；boot/MAC/instance_id改变会清旧确认及收件游标。整表和单节点请求互相失效，切目标后晚回的旧节点状态/错误都不能覆盖新选择。

发送冻结MAC/文字或HEX/版本；单节点复核不改变本次消息版本，若用户实际改目标/内容则取消POST。未知提交结果禁重发、双点仅一计划的原保护继续保留。离线预配置模式仍允许登记地址发送，但列表明确非发现证据。台架默认展开原图、隐藏邻居板块；分机默认折叠历史图。复位不会把台架图隐藏。

验收在D-024/20261108-01-neighbor-ui：真实E2 Handler+FakeEdge浏览器、15项邻居夹具及16项路线/发送回归；没有真实USB/RF。Ubuntu实用指南已发布edge_deployment/UBUNTU_DISCOVERY.md，02/03目录记录实际隔离安装产物检查。D不代替H的真实发现或Ubuntu物理拔插验收。
