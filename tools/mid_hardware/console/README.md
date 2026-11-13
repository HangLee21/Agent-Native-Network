# H控制台串口后端

双击本目录`打开实板控制台.cmd`打开8766实板控制台。已有同模式服务时直接复用，不重复起服务；否则委托现有E2 server.py --hardware --port8766 --open。打开页面不发送数据，仍需选择/预览/显式发送，实验保留和进程锁同样生效。`launch_console.py --check`仅只读检查，不启动服务或浏览器。E2原8765预览入口保留，不覆盖其文件。

解释器使用已有ESP-IDF Python（带pyserial），不安装全局依赖：`.local/espnow/E1-015/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe`。

```python
from tools.mid_hardware.console.adapter import status, execute
import threading
live = status(publisher="B")  # 不打开串口；有当前USB和最近info的来源说明
cancel = threading.Event()
# E2在worker线程执行；plan为E1 PlanLibrary返回的完整不可变JSON。
result = execute(plan, "D:/Multi-Agent Network/simulation/outputs/H-007/<唯一run>", cancel,
                 on_event=queue.put, timeout=60)
cancel.set()  # 由服务stop端点设置同一Event，不另开串口发指令
```

`execute`只允许不同的A–E、单流NetworkUpdate、1–10包，核表内节点和权重。实时info再核MAC/idle/同build/同UART速率，以实际源节点boot绑定配置发布者；原bridge.pack编码。不使用预览假boot或把TTL冒充固定跳数。沿已运行固件，接口不刷写、不复位。

结果含逐包nonce、origin/boot/seq/dst身份、实际tx_submit边、中继rx_relay、目的rx_local及payload匹配、完整原始JSONL/逐板raw、最终stop和端口状态。源接纳或MAC回调不等于交付。网络模型和预期链单列，未收到/部分/未知不伪装成功。调用回调应为快速queue.put，不做网络阻塞IO。

`lease.py`用Windows进程级非阻塞文件锁保护串口；同一时刻只有一个Wire。另有显式实验保留：H006正在执行M019时，控制台status返回busy，execute拒绝，不抢串口。M019每个进程退出会释放OS锁，但实验保留跨场景存在，直到H确认本轮结束后`release_reservation("H006")`。保留不会自动超时抢占；崩溃后由H检查进程停毕再释放。E2只消费status，不调用reserve/release。打开/刷新/计划预览不得调用execute。

`status`的ready_nodes来自USB存在和最近实际info，不声称已重新读取设备；状态可能在预览后变化。执行在锁内强制重读实时info，planner的runnable不是租约。服务自行维护唯一plan_id、重复点击防护、run状态/stop Event、loopback与Host/Origin防护。本模块不给HTTP任意命令或文件读取接口。

硬件测试须等M019实验闲置并由H沿H007授权从控制台操作。本接口未完成实板验收前只能声明代码/离线接入状态。
