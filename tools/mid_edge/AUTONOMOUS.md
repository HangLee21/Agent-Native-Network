# 只给目的地和载荷

自主模式使用E1的autonomous固件。每台主机只连自己的板，通过现有Edge或本地服务送入最终目的MAC和0–160字节。主机不上传全图、安装远端路由或选择中继；`routes()`只读取板端缓存。原MID、静态路径和一跳模式继续可用。

初次配置由管理员在本板inactive、无冲突配置时显式调用：

```python
from tools.mid_edge import Edge
with Edge('/dev/serial/by-id/本板', '本板实际STA-MAC', 460800) as board:
    board.route_config(group=29, channel=6, autostart=True)
```

这会写本板模式/组/信道并启动，不是只读探测。旧模式的停止、清理由操作者显式处理，适配器不会为配置成功而自动清除旧profile。`route_start()`恢复本地保存配置；`stop`保留配置；`route_clear()`在停止后显式删除自主配置。Ubuntu沿原精确USB规则和单串口服务，`saved`策略识别原生`deployment_mode=autonomous`及`discovery_saved`后用`route_start`，不装远端表。第一次用`observe`进入管理员配置流程。

业务与可视界面共用本地服务，不另开串口：

```python
from tools.mid_edge.local_api import LocalClient
app = LocalClient(8780)
receipt = app.send('目的STA-MAC', bytes(range(160)), request_id='mission-message-001')
progress = app.request_status('mission-message-001')
# 目的主机上的业务程序：
message = app.recv(timeout=30)
original_bytes = message['payload']
```

接纳回执给出`origin/origin_boot/seq/dst`，即使还没有下一跳也可以成功接纳。旧包在此时释放发送队列，不会被误当成新包：适配器按完整身份关联。相同request_id重复提交返回原记录；目标或载荷改变会拒绝。未知结果不会自动补发。

进展分开呈现：`queue_status`表示观察到的本地排队/等待寻路，`transmission_status=radio_api_accepted`来自本板SDK提交，链路回调另列。`board_terminal=route_no_route`只关联这包的等待轮次；`delivery_unknown`保留交付未知。`wait_packet(..., timeout=10)`的`observation_timeout`只是应用观察截止，不能当作板端寻路截止或未送达证明。源端没有端点ACK时始终`destination_unconfirmed`；目的本板`rx_local`才有`destination_received`及原始字节。

只读接口：

- `GET /api/edge/routes`：板端缓存，不是PC计算结果。
- `GET /api/edge/requests/<request_id>`：原请求及按原身份相关的progress。
- `GET /api/edge/packet?origin=...&origin_boot=...&seq=...&dst=...`：仅本板包事件证据。
- `GET /api/edge/events?after=...&wait=10`：同reader原始事件，保留游标、会话和路由轮次。

`route_history`按原生`route_waiting.request`关联候选/选择/失效，`board_selected_paths`标为`board_choice_not_hop_receipts`。路径向量不是沿途实际收件链，不能填补远端日志空缺；不同轮次不覆盖旧包选择。事件环形缓冲覆盖旧记录时会标`evidence_complete=false`，应查持久串口日志。

管理员同源POST仅提供`/api/edge/route/config {group,channel,autostart}`、`/route/start {}`、`/route/clear {}`、`/api/edge/radio/stop {}`。其中start/clear先核当前自主模式，防止误操作其它profile。业务发送仍只给dst和原字节，本地API自身管理请求ID。

模拟串口/Ubuntu PTY与实际RF分别记录在E2-027任务卡；此适配器测试不代替板上选路正确性或多物理Ubuntu主机验收。
