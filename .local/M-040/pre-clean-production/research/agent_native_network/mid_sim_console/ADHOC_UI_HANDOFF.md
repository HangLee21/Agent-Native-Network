# D-026交接：从首页进入本机自主收发

2026-11-09，交review。8767服务未重启，刷新即可载入新页面；本聊天保留的首页已选AD-HOC，入口目标仍为本机8780。原仿真草稿/消息字节未变，接入回放仍为join-6560779c、位置0、零边；只改变最终显示的操作模式。没有真实发送或串口操作。

## 已交

- 首页操作列表直接可见AD-HOC；打开本机单板服务的`/?mode=adhoc`，无跨主机代理/PC规划。离线和当前旧模式显示下一步并隐藏旧发送/仿真面板。临时命令生成器只收本地串口/MAC/HTTP端口，不自动执行；已有Ubuntu安装给出更新启动命令。
- autonomous原生状态下，最终MAC可不在本板邻居表。send仍只有request_id/dst/payload_hex，API未知或绑定错时禁自动重发。旧一跳邻居门控和台架/回放模式保留。
- 同身份包按waiting.request相关板选路径；新轮不改写旧包，旧失效不撤新路。板选、当前缓存、本板DATA提交/中继收到、目的本地原字节四类分开。缺实际远端事件不补全链；源端无ACK保持未确认。控制同seq和外板rx不能伪装目的交付。stop取消与无路截止区分。
- [分机部署指南](../edge_deployment/ADHOC_AUTONOMOUS.md)含Ubuntu登记/observe→显式route_config→saved、LocalClient业务例、停止/清配置/回退及OLED/无屏边界。[事件判据](BOARD_ROUTING_CONTRACT.md)按E1最终合同和E2真实API更新。

## 证据

`simulation/outputs/D-026/20261108-01-autonomous-ui/`是HTTP/浏览器夹具：等待、ABC选择且只本板A→B提交、第二包ADC、旧第一包仍ABC、原生无路、目的本地原字节、首页→本机服务→第四次提交。仅8792源fixture收四次POST；8793目的原收件两条；8794接口不可用和8795当前discovery均禁发。fixture重启后新游标/会话独立；数据均标synthetic。

`20261109-02-final-checks/`的82项断言全部通过，node语法及CLI帮助通过，安装器成功暂存而未activate。其最终汇总脚本错误地要求不存在的可选neighbors.js而断言失败，原脚本、日志及failed manifest保留；未为满足检查而造文件，未重跑已通过的82项。

`20261109-03-final-verification/FINAL_CHECKS.json`读取上一轮82项结果并核source hash未变；按HTML实际引用的index.html/workbench.js/sender.js/route-view.js核暂存副本全部一致，原稿/消息/零边保留和四次fixture提交通过。该轮manifest记录实际执行命令。浏览器证据只检查前端，不代替E1算法或真实RF。

首页截图`20261108-01-autonomous-ui/adhoc-homepage.jpg`，源发送`adhoc-local-submit.jpg`，旧包与新路`old-packet-vs-new-route.jpg`，目的字节`destination-original-bytes.jpg`。最后微小的标题/标点修正在截图之后；最终代码由82项检查及hash一致性覆盖。

最终可视复核补充：旧首页全页截图出现异常窄排版，保留原图不作为最终视觉验收。重新打开正常8767页面后viewport1280、入口面板1248px，当前最终源码布局正常，无页面代码变更。最终截图为`20261109-03-final-verification/adhoc-homepage-final.jpg`，`FINAL_VISIBLE_UI.json`保存原稿/消息相同、AD-HOC/8780、发送隐藏及回放位置0。此前`USER_STATE_RESTORED.json`在接入回放激活时确认零边；切出到AD-HOC后隐藏的旧SVG会回到台架草稿边，不能把隐藏SVG子节点数当作当前接入视图。最终入口没有可见网络图，不影响回到接入回放时从位置0绘制。已保留新的首页页签，无新增查询timer或RF。

## 未决与下一步

H-015继续实板空表多跳、撤实际中继/新包改道、无路截止和最终设备状态。三物理Ubuntu主机、USB/PID1热插拔未由D验证。M-025旧静态模式的无屏实包/收件证据不外推为M-029自主无屏镜像；后者仍待正式发布/实板验证。当前无端到端ACK、持久邮箱或自动可靠重传，不将页面接纳称可靠交付。

M/C可按本卡独立审阅，不需要D再发模拟包。D的fixture三个exec session均已Ctrl-C退出（Windows exit1已保存），相关fixture页已关闭，主首页无回放/查询timer。没有后台队列、跨聊天工具发送、实板/串口操作、服务8766/8767重启或Git写操作。本范围交审后停写。
