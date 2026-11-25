# Ubuntu 24.04 一车一板

树莓派/Ubuntu 的可安装 wheel、LoRa 角色与周期控制、多本地板独立实例和可选开机服务见 [树莓派上手说明](RASPBERRY_PI_LORA.md)。沿用下述 udev 服务的用户可直接使用升级后的 LoRa 本地 API，每块板仍只开一个串口所有者。

每台Ubuntu主机只操作本机登记的一块板，界面和业务程序共同访问本地8780服务。只有服务进程打开串口；业务程序用`LocalClient`，不要再另开`Edge`。原有Windows台架和MID/静态多跳配置不变。

先安装Python与串口库：

```sh
sudo apt-get update
sudo apt-get install python3 python3-serial
udevadm info --query=property --name=/dev/ttyUSB0
```

该查询只读USB元数据，不打开串口。复制`config.example.json`为本机配置，填写候选板的精确`ID_PATH`、`ID_USB_INTERFACE_NUM`、VID/PID、已登记的STA MAC、实际波特率。示例路径不是通用值。CH340可能没有唯一序列号，不能只填写1a86:7523；这里必须限定物理路径及接口。换USB插槽需重新登记路径，换tty编号不需要。已知板波特率为460800；刷写工具的低速恢复波特率不是业务串口波特率。

```sh
sudo python3 deploy/ubuntu/install.py install --config ./本机配置.json --activate
systemctl status 'mid-edge@*.service'
journalctl -u 'mid-edge@*.service' -n 50
```

安装创建专用mid-edge账户、精确匹配的udev规则和设备依赖systemd服务，复制最小运行代码及共页资源。已有匹配设备会启动；开机设备枚举和随后插入由udev拉起。`BindsTo`及`After`绑定当前tty设备，拔出时停止服务并关HTTP/串口，重新插入按新tty重新验证身份、创建新服务会话。不会扫描并试开所有串口。

首次使用`start_policy: observe`。服务先核USB元数据，再只发送带nonce的`info`；只有项目固件`mid-espnow`、ESP32-S3和登记STA MAC全部匹配才开放本地应用接口。错误固件/身份退出78，不自动重复探测；没有重刷、清配置、远端发布者绑定。DTR/RTS在打开前设为false，程序不主动复位。固件曾保存的自启配置可能自行启动射频；主机不会在识别通过前发送无线启动命令。

新自主发现固件的首次组/信道配置由管理员显式执行（仅在本机板idle、无冲突静态profile时接受）：

```sh
curl --fail http://127.0.0.1:8780/api/edge/status
curl --fail -H 'Origin: http://127.0.0.1:8780' -H 'Content-Type: application/json' \
  -d '{"group":7,"channel":6,"autostart":true}' \
  http://127.0.0.1:8780/api/edge/discovery/config
```

该POST有意保存本板发现配置并启动，不能当成只读探测。确认后把`/etc/mid-edge/config.json`的策略改为`saved`，重启当前服务。后续插入只在验证身份后恢复已有`discovery_saved`配置；静态`offline_table`保留原`local_start`。配置缺失/不支持会拒绝自动启动，不替用户安装或清除profile。停止服务保留板端NVS，明确启动过的服务会尝试本地stop；拔出已断链时直接关句柄，不重开端口补命令。

浏览器打开[本机工作台](http://127.0.0.1:8780/)。业务程序用同一个串口所有者的API：

```python
from tools.mid_edge.local_api import LocalClient
car = LocalClient(8780)
print(car.neighbors())                 # 只查本板邻居表
print(car.node_status('90:da:72:48:a5:cc'))  # 单节点只读，无RF探测
print(car.events(after=0, wait=10))     # 同reader原始事件/游标，最长等待10秒
car.send('90:da:72:48:a5:cc', '你好'.encode(), request_id='trip-message-001')
message = car.recv(timeout=30)         # 仅本板rx_local，payload是原始bytes
```

使用已安装模块时可设置`PYTHONPATH=/opt/mid-edge`。本地GET `/api/edge/neighbors`、`/api/edge/nodes/<MAC>`保留E1固件字段：状态heard/bidirectional/lost、boot、age_ms、last_seen_ms及last_confirmed_ms；时间来自本板单调时钟。USB出现、旧ABCDE图、源接纳和链路回调都不能代表无线邻居或远端交付。只有显式POST `/api/edge/nodes/<MAC>/probe {}`才触发固件按需复核，固件每秒最多一次；不会为监测全表高频探测。

服务会话`instance_id`随拔插变化，`LocalClient`会重置收件游标。收件是有限内存队列，事件/串口原文另记在`/var/lib/mid-edge/`，不是持久可靠邮箱；离线期间的载荷不保证保存。请求账本持久化防同id重发，未知结果不会自动补发。旧boot和邻居重现由固件实际无线事件决定，主机不从USB事件推断。

```sh
sudo python3 deploy/ubuntu/install.py uninstall --activate
# 明确要删除本机请求账本/日志时才加 --purge-state
```

卸载停止本服务并只删有安装标记的固定路径，默认保留数据和系统账户，不碰固件/NVS/其他udev规则。拔插后设备权限恢复其他系统规则的默认值。离线审阅安装产物可用`--root <空暂存目录>`，不加`--activate`；不会改系统服务。

systemd/udev设计参考：[设备单元与SYSTEMD_WANTS](https://www.freedesktop.org/software/systemd/man/247/systemd.device.html)、[udev规则限制](https://www.freedesktop.org/software/systemd/man/latest/udev.html)。运行长服务由systemd负责，不在udev的RUN回调中保持串口进程。

验证范围以E2-025任务卡及新运行记录为准。Ubuntu容器中的PTY/服务程序和规则解析，不等于Ubuntu实板物理拔插、systemd作为PID1的热插拔生命周期或三物理主机验证。

自主多跳沿用同一安装/USB门控服务。装E1 autonomous固件后，用observe策略显式POST `/api/edge/route/config`配置共同组/信道/自启，再改saved策略。原生info的模式为autonomous；配置仍以discovery_saved/discovery_fault表示本地保存状态，服务据此route_start。业务程序只`LocalClient.send(dst, payload)`，目的可不是一跳邻居；路径由本板按需求出。原一跳发现和静态路径恢复分支保留。新包的排队、SDK提交、板端无路和目的本地收件语义见`tools/mid_edge/AUTONOMOUS.md`。
