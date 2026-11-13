# 五板本地控制台

已运行的实板入口：http://127.0.0.1:8766/ （H保留的硬件模式服务）；http://127.0.0.1:8765/ 为预览实例。有限验收中，恰好4跳A→B→C→D→E和MID下实际B→D各3条均目的收到，实际路径来自日志；这6条功能记录不代表长期可靠性或测量模型。当前实例关闭后，按下列启动方式重开。

实板可直接双击H提供的 [打开实板控制台.cmd](../mid_hardware/console/打开实板控制台.cmd)：已有8766硬件服务时只打开页面，未运行时启动原服务的硬件模式。打开页面仍不发送，必须显式点击发送并通过实验锁。此入口由H维护；本目录START_CONSOLE.cmd继续默认预览。

清理未确认时会显示cleanup_unconfirmed，保留发送保护。[恢复页面](http://127.0.0.1:8766/recovery/)只核对指定失败运行的H停止凭据，不能提交自称已停或任意文件路径；没有新鲜证明时不放行。恢复保留原失败和选择，不重发业务。运行及已消费计划保存在.local/mid/E2-018/service-8766，重启会恢复保护。2026-11-07的C→A→E失败已用H实核凭据恢复，旧版未落盘的临时预览需重新预览。

双击本目录 `START_CONSOLE.cmd`，浏览器打开 http://127.0.0.1:8765/ 。默认只预览，打开或刷新不会发包。关闭终端或按 Ctrl+C 结束服务。端口占用时可运行 `START_CONSOLE.cmd --port 8766`。

选择不同的源/目的板，选 MID、恰好几跳或手工中继，再点规划。固定跳数是恰好相应边数的简单链，选择规则由 E1 返回；MID 调用真实 SOCP，显示权重及候选边，实际逐包路径只能来自设备日志。默认模型系数来自历史假设输入，不代表实时链路测量。求解失败会明确返回原因，不替换为假算法。

服务使用 Python 标准库。MID 规划优先使用现有 `.local/mid/E1-016/venv/Scripts/python.exe`；缺少依赖时仍可用系统 Python 预览 hops/manual，MID 会报告依赖错误，不安装全局包。

实板入口为 `START_CONSOLE.cmd --hardware`。只有明确点击发送才调用 H 适配器；H 必须报告当前可用设备和发布者 boot，并原子检查 M-019 实验锁。没有 H 接口、设备不足或实验忙碌时仍能预览，发送返回原因。E2 不打开或刷写任何串口；H的status仅枚举USB并说明最近info来源。同一 plan_id 至多执行一次，最多10包，60秒触发停止，运行结束以 H 排空释放结果为准。停止中仍保持忙碌，不强制杀掉串口线程。任何执行异常、参与板停止未确认或端口未关都会保留cleanup_unconfirmed占用，须H核实后处理，不能靠再次发送恢复。实板结果写入H-007的新run。

API：GET `/api/status`；POST `/api/plan` `{src,dst,mode,hops|via,count}`；POST `/api/run` `{plan_id}`；GET `/api/runs/{id}`；POST `/api/runs/{id}/stop` `{}`。POST 须 `Content-Type: application/json` 及同源 Origin。只监听127.0.0.1，校验 Host/Origin，不支持任意命令、模型路径或文件读取。

同源优先加载 D 的 `research/agent_native_network/mid_replacement_demo/control/index.html`，尚未交付时用本目录备用页。`/replay/` 为已有真实历史回放，与当前发送结果分开。服务运行状态只在内存保存，重启后旧计划不能重放；H保留原始记录及执行结果。
