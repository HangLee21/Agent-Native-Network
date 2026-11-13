# AD-HOC：每台边缘设备只连自己的板

应用在A主机调用本地服务，给最终目的C的STA MAC和原始字节；A板自行寻路，B等中继板自行转发，C主机从自己的本地服务取包。三台主机不通过HTTP互相转运业务，也不需要集中在一台电脑上。中继主机不用代替板子收一包再发一包。

```text
A应用 → A本地8780 → USB → A板 ──ESP-NOW── B板 ──ESP-NOW── C板 → USB → C本地8780 → C应用
                                        B板自主转发
```

这里使用M-029的`autonomous`固件；[一跳发现](UBUNTU_DISCOVERY.md)只能直接发给已确认邻居，[旧预配置ABC多跳](QUICKSTART.md)则需要事先配置路径。网页的“链路仿真”不打开串口，也不发送真实无线包。8767里的“实板发送”是同机台架入口，不用于分机部署。

## 从网页开始

在[8767首页](http://127.0.0.1:8767/)的“操作”中选 **AD-HOC · 本机自动路由**，再打开本机8780工作台。也可在每台车直接打开[本机AD-HOC页](http://127.0.0.1:8780/?mode=adhoc)。`127.0.0.1`始终指当前浏览器所在的设备；在A车上打开不会连接到C车的串口。8767只提供入口，不代理业务或计算路径。

本机接口未接入时，入口提供启动命令；当前板仍为旧模式时，显示配置步骤并禁用旧发送面板。`routing_supported:false`只表示当前没有确认已配置自主模式，不能据此断定固件一定不支持。网页不会自动刷写、清profile或启动射频。

本板原生状态为`autonomous`后，输入“最终目的MAC”和UTF-8文字或HEX，单包0–160字节。目的可以不在一跳邻居表中。应用仍需知道最终MAC；全网名称到MAC的发现未实现。页面分别显示板端选择、本板实际观测和目的本地收件；读取时的缓存不会套到旧包。读取是手动操作，“跟踪30秒”有明确截止，不发新业务包。

## Ubuntu首次部署

每台Ubuntu 24.04主机准备同一版本项目及本板。正式OLED自主包为`.local/mid/E1-025/oled-package-01/`，build为`mid-route-v1-c761d1e8eb12ca803b5164c07dbc23e05e4d19c76a5db953b13d6f39f00852c8`，业务串口460800/8N1。设备持有者按包内`HANDOFF.json`核实际MAC、分区兼容和回退条件后操作；网页选择模式不能改变板上固件。

在项目根目录执行：

```sh
sudo apt-get update
sudo apt-get install python3 python3-serial
udevadm info --query=property --name=/dev/ttyUSB0
cp deploy/ubuntu/config.example.json ./car-local.json
```

把当前tty名称换成本机值。编辑`car-local.json`：`id_path/interface/vid/pid`填写实际USB属性，`node_id`填本板已登记STA MAC，`baud`为460800，`http_port`为8780，首次`start_policy`为`observe`。CH340不一定有唯一序列号，VID/PID相同不能替代精确USB路径和接口。换插槽需重新登记。

```sh
sudo python3 deploy/ubuntu/install.py install --config ./car-local.json --activate
systemctl status 'mid-edge@*.service'
journalctl -u 'mid-edge@*.service' -n 50
curl --fail http://127.0.0.1:8780/api/edge/status
```

服务是唯一串口所有者。先核项目固件、ESP32-S3、登记STA和当前模式。`observe`不主动下发无线启动命令，板中已有自启配置仍可能自行启动无线。旧静态或发现profile须由设备持有者显式stop并清相应配置；不能直接覆盖正在运行的模式。正式包`DEPLOYMENT.md`给出串口命令，本地CLI也保留`stop/deployment_clear/discover_clear`。

在已装自主固件、idle且无冲突profile的本板，分别给所有板相同的组和信道：

```sh
curl --fail -H 'Origin: http://127.0.0.1:8780' -H 'Content-Type: application/json' \
  -d '{"group":29,"channel":6,"autostart":true}' \
  http://127.0.0.1:8780/api/edge/route/config
curl --fail http://127.0.0.1:8780/api/edge/status
```

该POST会写本板NVS并启动无线；没有路径、远端表或下一跳字段。确认`info.deployment_mode=autonomous`、`discovery_saved=true`、`discovery_fault=false`和组/信道后，把`/etc/mid-edge/config.json`的`start_policy`改为`saved`，重启当前实际tty对应服务，例如`sudo systemctl restart mid-edge@ttyUSB0.service`。下一次通过USB及STA验证后，服务执行`route_start`恢复本板配置。

已有安装重新部署用`sudo python3 deploy/ubuntu/install.py install --config /etc/mid-edge/config.json --activate`。临时调试可用下面入口，替换实际串口/MAC；它不自动写profile或开启无线，串口须先由原服务释放：

```sh
python3 -X utf8 -m tools.mid_sim_console.local_edge --serial-port /dev/ttyUSB0 \
  --node-id 90:da:72:48:a4:f8 --baud 460800 --port 8780 \
  --state car-requests.json --log car-session-001.jsonl
```

Windows改用`python`和本机COM号。每次日志使用新文件名；账本路径应保留，避免丢掉原请求状态。此命令不代表上面示例MAC一定接在当前串口。

## 不用网页和OLED的业务接口

业务与网页共用本地服务，不能再另开同一串口。安装后设置`PYTHONPATH=/opt/mid-edge`。A主机：

```python
from tools.mid_edge.local_api import LocalClient

car = LocalClient(8780)
receipt = car.send("90:da:72:48:a4:e0", "A发给C".encode("utf-8"),
                   request_id="mission-message-001")  # 替换为最终目的实际MAC
print(receipt)
print(car.request_status("mission-message-001"))
```

C主机独立运行：

```python
from tools.mid_edge.local_api import LocalClient

message = LocalClient(8780).recv(timeout=30)
print(message["origin"], message["origin_boot"], message["seq"], message["dst"])
original_bytes = message["payload"]
```

B只需板端自主模式运行，无需主机应用为每包指定C或中继路线。相同`request_id`绑定同一目的和字节；结果不确定时查原请求，不换新ID自动重发。当前没有端到端ACK和自动可靠重传；源接纳、SDK提交或`tx_link_ok`都不能证明C收到。C本地`rx_local`的原始身份和字节才是目的收件证据。

OLED订阅同一业务事件：本地TX、作为中继RX/转发、最终目的RX及失败会更新业务首页。发送API不含翻页或显示参数，业务程序无需操作OLED。M-025已交旧静态模式的OLED及无屏包，且有无屏C收件证据；M-029本次正式发布的是OLED自主包，不能把旧无屏包当作自主多跳无屏版本。自主无屏镜像的正式发布和实板验证仍须单独交付。

## 停止、恢复与证据

只停止本板无线而保留配置：

```sh
curl --fail -H 'Origin: http://127.0.0.1:8780' -H 'Content-Type: application/json' \
  -d '{}' http://127.0.0.1:8780/api/edge/radio/stop
curl --fail http://127.0.0.1:8780/api/edge/status
```

核`radio=false`后，可显式POST同源`/api/edge/route/clear`删除自主配置；保留配置时用`/api/edge/route/start`恢复。stop不会取消NVS自启，清除前先把主机策略设`observe`。正式包要求清运行期`link_filter`后按实际MAC/lease退回旧OLED1969；这由设备持有者按`HANDOFF.json`执行，不由网页代刷或擦NVS/eFuse。卸载主机服务使用`sudo python3 deploy/ubuntu/install.py uninstall --activate`，默认保留账本/日志。

拔插后先查systemctl/journalctl，确认同一登记插槽、身份和新会话。网页重读本板；`instance_id`或boot变化后，旧邻居确认及旧事件不会作为当前状态。收件是有界内存队列，服务退出期间不保证补收；持久串口日志和请求账本保留在`/var/lib/mid-edge/`。

D-026的浏览器发送/改道/无路/目的收件是正式E2 HTTP处理器配合synthetic板事件的夹具检查，无串口或RF。E2-027的Ubuntu容器PTY不是物理USB/PID1或三物理主机；E1-025的同核主机测试及目标构建不是无线结果。自主空表多跳、撤中继改道和最终设备状态由[H-015](../../../coordination/tasks/H-015.md)记录，整体验收看[M-029](../../../coordination/tasks/M-029.md)。
