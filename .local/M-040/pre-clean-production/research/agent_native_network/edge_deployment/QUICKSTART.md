# A、B、C 分接三台设备：快速开始

本指南用本地串口和板间 ESP-NOW：设备1只接A，设备2只接B，设备3只接C。路径为 A→B→C（另配反向 C→B→A），B由固件自动转发。正常业务不依赖8766/8767，也不通过主机IP搬运数据。这是离线预配置路径，不是在线MID动态优化。

**当前ABC已恢复OLED正式固件、MID兼容空闲，离线profile已清除。现在切分机必须执行下面首次 `--profile` 部署，不能直接省略。**

## 1. 每台设备准备文件与本地端口

三台都放置相同目录结构，从项目根目录运行命令。应用最小文件为 `tools/mid_edge/`、本目录 `profiles/abc-deploy.json`；Python依赖pyserial。Windows主机验证使用pyserial 3.5。离线机器预先准备相应Python/pyserial安装包。不要把一台机器的COM端口写成远端端口。

先列本机端口（不打开串口）：

```powershell
python -m serial.tools.list_ports -v
```

当前同PC台架的真实映射如下；分接三台设备后，各自重新选择本机端口，但MAC不变。

| 板 | 本轮台架端口 | 实际MAC | 应用串口参数 |
|---|---|---|---|
| A | COM12 | 90:da:72:48:a4:f8 | --baud 460800，8N1 |
| B | COM10 | 90:da:72:48:a5:cc | --baud 460800，8N1 |
| C | COM7 | 90:da:72:48:a4:e0 | --baud 460800，8N1 |

当前包已刷好，无需重刷。新板或切换有屏/无屏先按[正式包清单](RELEASE.md)核对固件与实际MAC。以下COM值仅是本轮真实例子，换设备后改成各自本机值；客户端会检查实际板身份。

一个串口只留一个所有者：CLI、Python应用、可视服务和串口监视器不能同时打开同一块板。下面部署命令会执行后关闭串口；关闭客户端本身不会停止已部署板的射频。

## 2. 首次分别部署同一份路径表

确认每板idle、radio=false、无在途发送。当前三板已由H收尾到该状态。在三台设备分别执行对应一条：

```powershell
# 设备1 / A
python -X utf8 -m tools.mid_edge.example deploy --port COM12 --node-id 90:da:72:48:a4:f8 --baud 460800 --profile research/agent_native_network/edge_deployment/profiles/abc-deploy.json
```

```powershell
# 设备2 / B
python -X utf8 -m tools.mid_edge.example deploy --port COM10 --node-id 90:da:72:48:a5:cc --baud 460800 --profile research/agent_native_network/edge_deployment/profiles/abc-deploy.json
```

```powershell
# 设备3 / C
python -X utf8 -m tools.mid_edge.example deploy --port COM7 --node-id 90:da:72:48:a4:e0 --baud 460800 --profile research/agent_native_network/edge_deployment/profiles/abc-deploy.json
```

`deploy.json` 是部署命令，不能换成E1的说明文件 `profile.json`。本目录文件逐字节复制自E1正式ABC双向配置，来源/哈希见RELEASE.md。`autostart:true` 会保存本板NVS并立即启动；三块板各存一份，不需要缓存A某次启动的publisher_boot。部署失败不继续发包；`saved_but_start_failed` 表示已保存但启动失败，应读info后修复，再显式local_start。

也可首次直接运行JSONL客户端并加同一 `--profile`；此后普通连接不要重复deploy：

```powershell
python -X utf8 -m tools.mid_edge --port COM12 --node-id 90:da:72:48:a4:f8 --baud 460800 --profile research/agent_native_network/edge_deployment/profiles/abc-deploy.json
```

此入口首次输出的ready附带deploy前info，部署后在该客户端再输入 `{"op":"info"}` 核实际 `offline_table`、`deployment_saved:true`、`autostart:true`、`mode:active`、`radio:true`。不要另开客户端查询同一串口。

## 3. B观察中继，C先接收，A再发文字

B部署后固件即可中继，不需要主机应用转发。要保留本地事件，可在设备2运行：

```powershell
python -X utf8 -m tools.mid_edge --port COM10 --node-id 90:da:72:48:a5:cc --baud 460800 --log B-session-01.jsonl
```

日志名须是新文件。该窗口可输入 `{"op":"info"}`、`{"op":"stats"}` 或 `{"op":"events","after":0}`；这里不需要再加 `--profile`。

先在设备3运行C接收，保持等待：

```powershell
python -X utf8 -m tools.mid_edge.example recv --port COM7 --node-id 90:da:72:48:a4:e0 --baud 460800 --timeout 120
```

再在设备1发送文字（A端若还有上一节交互客户端，先Ctrl+C关闭它，再用此命令；不发stop即可保持已部署固件运行）：

```powershell
python -X utf8 -m tools.mid_edge.example send --port COM12 --node-id 90:da:72:48:a4:f8 --baud 460800 --dst 90:da:72:48:a4:e0 --text "你好，C！"
```

文字按UTF-8编码，单包最多160字节。这条消息是13字节，C的 `payload_hex` 应为 `e4bda0e5a5bdefbc8c43efbc81`。核对A回执与C应用结果的 `origin / origin_boot / seq / dst` 一致，且C原始字节相等。B事件应有 `rx_relay` 和向C的 `tx_submit`。

A的 `destination_unconfirmed` 仅表示本机接纳，不能改写成“C已收到”；C应用的本板 `rx_local` 才是目的证据。没有端到端ACK或自动可靠重发，超时可能已经发出，不能盲目用新请求补发。

## 4. 发送任意二进制，或由应用直接调用

C完成一次接收后，再运行上面的recv命令等待下一包。A执行：

```powershell
python -X utf8 -m tools.mid_edge.example send --port COM12 --node-id 90:da:72:48:a4:f8 --baud 460800 --dst 90:da:72:48:a4:e0 --hex 00ff6869
```

C应取到原始 `00 ff 68 69`，不要求它是合法文本。真实业务可直接使用同一个Edge对象；显示屏不是接口依赖：

```python
from tools.mid_edge import Edge

# C应用；端口换成本机值。只有这个对象持有该串口。
with Edge('COM7', '90:da:72:48:a4:e0', 460800) as board:
    board.info()
    item = board.recv(timeout=120)
    original_bytes = item['payload']
    identity = (item['origin'], item['origin_boot'], item['seq'], item['dst'])
```

A用同一API的 `board.send(C_MAC, b'\x00\xffhi')`。一个应用同时收发时，共用一个Edge对象及其后台reader，不另开接收串口。

Linux用同一模块，把 `python` 换为 `python3`、COM端口换成本机 `/dev/serial/by-id/...`（列举命令仍是 `python3 -m serial.tools.list_ports -v`），其余包括 `--baud 460800` 保持。每台只选择自己的板；本轮Linux和三台物理主机尚未实机验收。

## 5. 开机、关闭客户端、重启与停机

- 已部署 `autostart:true` 后，固件复位会从本板NVS恢复。A或B单独复位不需要向其他板重新分发源boot；A的新包带新boot，序号可从1重新开始。重新连接不带 `--profile`。H已实测A/B复位后收件，真实断电循环尚未验证。
- 只关闭客户端会释放串口，板仍可中继。显式stop保留profile但关射频；不复位而想恢复时，在该板本地客户端输入 `{"op":"local_start"}`，再读info确认active。
- PRG是显示诊断键，不是这里的复位操作。重启后若 `deployment_load_failed` 或profile缺失，不自动假装正常运行；先info定位，在inactive状态重新首次部署。
- C客户端应在A发包前开始接收。板端没有持久业务邮箱；应用掉线期间的载荷不保证补交，接收队列和去重窗口均有界。

## 6. 看屏测试与无屏运行

有屏测试默认一个业务首页：本板/源目的/原包序号，A显示TX；B区分中继收到、提交TX与链路结果；C显示目的RX。本地失败另显示，TX不会冒充目的确认。用户已在H012/29确认ABC业务页正常，PRG诊断约5秒返回首页；这是用户实物观察记录，不是D拍摄像素。

无屏正式目标使用同样的网络/部署/串口/载荷接口，`display_enabled:false`，保留事件与计数；构建不链接显示renderer/I²C。H已在C无屏目标实际收到1包，payload/身份一致。切换固件由设备持有者按正式包HANDOFF操作，先停业务/关闭串口，再核MAC；已存autostart配置会在刷后复位时启用射频，不能因刷前stop就假定刷后仍idle。当前三板已恢复OLED，尚未保留离线profile。

## 7. 回到网页台架模式

每块本地板分别操作；A/B/C都完成后才使用网页。当前三板已执行过此收尾，下面是下次从offline返回时的步骤。

在持有该板的JSONL客户端依次输入：

```json
{"op":"stop"}
{"op":"stats"}
```

确认 `mode:idle`、`radio:false`、`stopping:false`、`queue_depth:0`，再输入：

```json
{"op":"deployment_clear"}
{"op":"info"}
```

确认 `deployment_mode:mid`、`deployment_saved:false` 且保持idle/radio=false，然后Ctrl+C关闭客户端释放串口。若stats仍stopping或有队列，等待后再读stats，不能直接clear。之后网页才可独占本机台架串口。不要用erase_flash或擦整个NVS代替deployment_clear。

## 已验证的范围

| 内容 | 现有证据 |
|---|---|
| 同一Windows PC三个独立本地进程，各只开本板串口，经真实ABC交付原字节 | H012/14原记录，H15补核与E2-023/04独立逐包核3/3；原监督脚本断言失败保留 |
| B单独复位、A复位换boot后继续收到，无远端boot重绑定 | E2-023/04原日志核对 |
| C换无屏目标收件1/1，接口与原始字节保留 | H012/17、E2-023/05 |
| 当前新端口网页真实A→B→C | D-023/05，A COM12/B COM10/C COM7，52字节1/1 |
| 当前OLED业务页与PRG返回 | H012/29用户观察记录 |
| 三台物理边缘主机、Linux实机、真实断电循环 | 未验证；不能用同PC三进程/复位结果代替 |

完整来源与正式包哈希见[RELEASE.md](RELEASE.md)。本指南编写时D只做入口帮助、文件/配置/证据核对，没有新增串口或RF测试。
