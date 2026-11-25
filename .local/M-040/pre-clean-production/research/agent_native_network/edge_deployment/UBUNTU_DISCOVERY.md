# Ubuntu：每车一板，自主发现后收发

每台车只接自己的板。首次登记本机USB接口、板MAC和共同组/信道；以后由本地服务处理开机、插入和重新枚举。板间业务走ESP-NOW，业务程序和网页共用本地8780服务，一个进程持有串口。

这里使用M-027自主一跳发现固件。它与[旧ABC预配置多跳](QUICKSTART.md)分开：发现模式可收到未预录MAC的新邻居，只向当前双向确认的直连邻居发送；它不自动发现多跳路径。不要拿旧MID或offline_table固件的历史结果证明发现模式已可用。

## 1. 准备本机文件和板

将同一版本项目放到每台Ubuntu 24.04主机，至少保留`deploy/ubuntu/`、`tools/mid_edge/`、`tools/mid_sim_console/`和`research/agent_native_network/mid_sim_console/`的安装器所需文件。安装器会复制最小运行文件到`/opt/mid-edge`。新发现包的来源及可刷状态看[E1-024主卡](../../../coordination/tasks/E1-024.md)，真实设备执行及结束状态看[H-014主卡](../../../coordination/tasks/H-014.md)。本指南不自动刷板，也不把已有OLED包视为新发现包。

E1已发布`.local/mid/E1-024/oled-package-01/`，本轮应按[07-release/HANDOFF.json](../../../simulation/outputs/E1-024/20261108-07-release/HANDOFF.json)交设备持有者操作；其中明确实际刷写对象和主退回目标。包已编译不代表本车已经刷好，也不代表Ubuntu物理插拔通过。

在项目根目录安装依赖并读取本机USB属性：

```sh
sudo apt-get update
sudo apt-get install python3 python3-serial
udevadm info --query=property --name=/dev/ttyUSB0
cp deploy/ubuntu/config.example.json ./car-local.json
```

`ttyUSB0`换成本机当前设备名。把实际`ID_PATH`、`ID_USB_INTERFACE_NUM`、`ID_VENDOR_ID`、`ID_MODEL_ID`分别填入JSON的`id_path/interface/vid/pid`；`node_id`填本板已登记STA MAC，`baud`为该包实际波特率460800，`http_port`为8780，首次`start_policy`保留`observe`。示例USB路径和A的MAC必须改成本车值。CH340的VID/PID不唯一，不能只凭1a86:7523认板。

## 2. 安装并核本板身份

```sh
sudo python3 deploy/ubuntu/install.py install --config ./car-local.json --activate
systemctl status 'mid-edge@*.service'
journalctl -u 'mid-edge@*.service' -n 50
curl --fail http://127.0.0.1:8780/api/edge/status
```

规则只拉起精确登记的USB物理路径和接口，服务再读项目固件、芯片及实际STA MAC；错误身份退出78，不自动试开其他外设。`observe`不向板下发无线启动命令；板上已有自启配置可能自行启无线，不能把observe理解为强制静默。网页或业务程序运行时，不另开串口监视器或`Edge`。

## 3. 首次共同组/信道配置

先核板处于idle，没有静态profile或其他业务；切模式须由设备持有者按E1合同显式停止并清相应旧profile，本页不偷偷清配置。每车本地分别执行相同组号和信道：

```sh
curl --fail -H 'Origin: http://127.0.0.1:8780' -H 'Content-Type: application/json' \
  -d '{"group":7,"channel":6,"autostart":true}' \
  http://127.0.0.1:8780/api/edge/discovery/config
```

这一步会保存本板配置并启动无线，属于首次部署。组号/信道要与团队一致，组号不是认证密钥。确认status里`discovery_saved:true`、`deployment_mode:discovery`、组和信道正确后，把`/etc/mid-edge/config.json`中的`start_policy`改为`saved`。用status查到当前tty对应的服务名，再重启它，例如：

```sh
sudo systemctl restart mid-edge@ttyUSB0.service
```

以后验证身份后只恢复已保存的本地配置，不需要预录邻居MAC或某次启动的远端boot。没有支持的配置会拒绝自动启动，不能把服务退出当作邻居失联。

## 4. 网页选邻居、发消息、关注一台车

在每台车打开[本机收发页](http://127.0.0.1:8780/)。先读本板身份，再点“读取邻居”。B晚启动后，A的邻居表应由实际无线记录出现B的MAC；名称缺失时会显示“未命名设备”，以MAC和boot为准。

- “单向收到”表示听到对方，不能发送；“双向已确认”才可选作发送目的；“已超时”会禁发。接收年龄显示本板单调时钟，不能拿不同车的时钟相减当无线时延。
- 选为目的，输入UTF-8文字或HEX，单包最多160字节。发送前再读所选MAC的本板记录；目标或内容在读取期间变化会取消本次发送。结果未知时禁重发。
- 在“关注设备”里选一台车，“读取本板记录”只查本地表；“开始监测”每2秒查该节点，5分钟结束，可手动停止。不会为监测全表逐个发无线探测。确认/超时由固件记录决定；页面也会按上次记录推算过期并标明。
- C查看本板收件，取得原始载荷和`origin/origin_boot/seq/dst`。A的“本机接纳”与链路回调都不代表C已收到，当前没有端到端ACK或自动可靠重传。

旧五板图折叠在“历史台架图”，不显示成当前无线邻接；原8767台架仿真和保存包图仍保留。

## 5. 业务程序共用本地服务

在安装后的主机设置`PYTHONPATH=/opt/mid-edge`，使用实际发现的目的MAC：

```python
from tools.mid_edge.local_api import LocalClient

car = LocalClient(8780)
print(car.neighbors())
print(car.node_status("90:da:72:48:a5:cc"))  # 替换为本车刚发现的邻居
car.send("90:da:72:48:a5:cc", "你好".encode("utf-8"), request_id="car-message-001")
received = car.recv(timeout=30)
payload = received["payload"]  # 原始bytes；仅本板rx_local
```

同一请求ID绑定目的和载荷。超时可能已经发出，不用新ID自动补发。业务与UI同用8780，不另开串口。收件是有界内存队列，掉线期间不保证补交；事件日志及请求账本在`/var/lib/mid-edge/`。

## 6. 拔出、重新插入及排查

拔出后设备依赖停止本地服务；页面读不到本板时显示未知并禁发，不从USB断开直接推断所有无线邻居的状态。插回同一登记USB插槽后，tty编号可以变化；服务按新tty重新核身份，并产生新`instance_id`。页面重新读取本板后丢弃旧邻居确认和旧收件游标，再读实际记录。对方板重启换boot后同样需要新双向确认。

换USB插槽会改变`ID_PATH`，需更新登记配置再安装，不能放宽成只匹配VID/PID。查`systemctl status`与`journalctl`：身份拒绝、缺配置、串口被其他程序占用分别处理。确认服务重新就绪后刷新本板状态；不要为恢复连接而重刷或擦NVS。

```sh
sudo python3 deploy/ubuntu/install.py uninstall --activate
```

默认卸载保留请求账本/日志和系统账户，不碰固件/NVS。只有明确要删除本机历史时才加`--purge-state`。

## 本次证据边界

本指南的安装、API和固件字段来自E2-025/E1-024当前实现；D只做CLI帮助、隔离目录安装产物及界面检查。D的浏览器邻居/收发、超时、重加入与断开场景使用假板和正式HTTP处理器，没有真实RF。Ubuntu容器/PTY与规则解析、同机实板RF、Ubuntu实板物理拔插须分别看各任务记录，不能互相替代。发布和最新限制另见[Ubuntu安装器说明](../../../deploy/ubuntu/README.md)及各主卡。
