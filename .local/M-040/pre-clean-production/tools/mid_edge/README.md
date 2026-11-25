# 本机单板收发

每台主机只连接自己的板。Python `Edge`、JSONL客户端和本机可视服务共用同一个串口所有者；不要同时开串口监视器或另一个客户端。板间转发由固件完成，主机不转运载荷，不需要8766/8767或主机间IP。Python代码兼容Windows/Linux，依赖pyserial；本轮主机检查在Windows运行，Linux实机未验证。

E1的offline_table固件在首次本地deploy后保存有向表，断电重启从本板NVS恢复，无远端publisher_boot。B运行固件即可中继，不需应用转发。首次部署用E1发布的profile；原MID固件不支持deploy。`stop`保留配置，`local_start`重新启动本地配置，`deployment_clear`显式删除。关闭客户端只关闭串口，不自动停止已部署的板。

以下物理命令供H或实际设备持有者执行，E2未打开设备。端口须按本机识别修改；460800来自H本轮c422身份检查，新固件用其实际配置，不猜用115200。

```powershell
# C：等待原始字节和身份
python -X utf8 -m tools.mid_edge.example recv --port COM12 --node-id 90:da:72:48:a4:e0 --baud 460800 --timeout 60
# A：自定义二进制（00/ff不会被文本编码改写）
python -X utf8 -m tools.mid_edge.example send --port COM7 --node-id 90:da:72:48:a4:f8 --baud 460800 --dst 90:da:72:48:a4:e0 --hex 00ff6869
```

Linux使用相同模块，把COM端口换成本机`/dev/serial/by-id/...`路径，`python`换为`python3`。Linux启用pyserial exclusive；Windows COM由系统独占。每台机器单独复制`tools/mid_edge/`即可用Python API/CLI；可视服务另需`tools/mid_sim_console/local_edge.py`，无H全板工具依赖。

```python
from tools.mid_edge import Edge
with Edge('/dev/serial/by-id/本板', '90:da:72:48:a4:e0', 460800) as board:
    board.info()
    message = board.recv(timeout=60)
    original_bytes = message['payload']
    identity = (message['origin'], message['origin_boot'], message['seq'])
```

`send()`返回`destination_unconfirmed`：只证明本地接纳。`recv()`只由本板`rx_local`生成，给出原始bytes和身份。链路回调、中继接收和本地接纳都不算目的交付。无远端ACK，也不增加自动重发。命令超时可能已经发出，不能以新请求自动补发。

单进程同时需要发送、接收时，用一个Edge对象；一个后台reader读完整串口，发送命令由nonce关联，接收队列保留目的包。JSONL入口：

```powershell
python -X utf8 -m tools.mid_edge --port COM7 --node-id 90:da:72:48:a4:f8 --baud 460800
```

stdin每行一个对象，例如`{"op":"send","dst":"90:da:72:48:a4:e0","payload_hex":"00ff6869"}`、`{"op":"recv","timeout":30}`、`{"op":"stats"}`。首次inactive部署可加`--profile`，之后连接不重复deploy。`--log`写新JSONL文件，已有文件拒绝覆盖。接收积压超界会明确失败，不静默丢弃。

主机检查命令已实际运行：`python -X utf8 -m tools.mid_edge.hostcheck -v`。使用模拟串口核对原始00ff/UTF-8字节、原包身份、B中继与目的收件区别、CLI入口、错误板身份拒绝；这些是synthetic证据，不是RF或三台物理主机结果。实际profile、冷启动和RF验收依E1/H交付。

E1正式ABC双向配置已生成于`simulation/outputs/E1-023/20261108-03-abc-profile/deploy.json`；E2也实际运行生成器，生成ABC单向示例`simulation/outputs/E2-023/20261108-01-profile/deploy.json`。按所需方向选择同一份文件，分别在每个inactive板本机用`python -m tools.mid_edge.example deploy --port <本地端口> --node-id <本板MAC> --baud 460800 --profile <deploy.json>`配置；之后正常连接不再带profile。E2-023/20261108-02-host-client含Windows本地配置JSON，CLI支持`--config <文件>`读取port/node_id/baud，换主机时只改本机端口。上述文件/生成命令与模拟串口deploy检查已实际运行；真实NVS写入和重启由H验证。

H现已实际执行三个本地CLI进程，各自连接A/B/C，部署后3条载荷均由C应用取到，经B自动转发。B单独重启恢复NVS后、A单独重启换boot后继续收到，无远端boot重绑定；C换无屏目标另收1条。真实命令是`python -m tools.mid_edge --port COM7 --node-id 90:da:72:48:a4:f8 --baud 460800 --profile <上述deploy.json> --log <新文件>`，B/C各用自身端口/MAC，重启连接不带profile，再在stdin发send/recv对象。E2只读核验在`simulation/outputs/E2-023/20261108-04-real-local-audit/`及`05-headless-audit/`。原H14监督脚本第三包快照断言失败保留，完整日志另证3/3；未重发补测试。本次是同一Windows PC三个独立进程及三块真实板，Linux和三物理主机仍未验证。
# LoRa reference control

Installable wheel, per-board USB configuration, Python examples and optional Raspberry Pi boot service: [Raspberry Pi guide](../../deploy/ubuntu/RASPBERRY_PI_LORA.md). `Edge` and `LocalClient` provide `lora_status()`, `lora_config(...)` and `lora_events(...)`; Wi-Fi business send/recv retains its original endpoint evidence semantics.

