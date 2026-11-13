# 树莓派控制本地 LoRa 板

包名 `mid-edge`，导入路径为 `tools.mid_edge`，要求 Python 3.10 及以上。树莓派 OS / Ubuntu 使用同一份纯 Python wheel。LoRa 参数由本地 USB 串口设置，业务载荷继续由板上的 Wi-Fi / ESP-NOW 发送；LoRa 收件单独读取。旧固件没有 LoRa 命令时会明确返回 `UnsupportedFirmware`。

## 安装

从仓库生成 wheel，不下载依赖、不打开串口：

```sh
python3 deploy/ubuntu/build_package.py --output ./mid-edge-package
```

将生成的 wheel 复制到树莓派：

```sh
sudo apt-get install python3-venv
python3 -m venv ~/mid-edge-venv
~/mid-edge-venv/bin/pip install ./mid-edge-package/mid_edge-0.4.0-py3-none-any.whl
~/mid-edge-venv/bin/python -c 'from tools.mid_edge import Edge, LocalClient; print("import OK")'
```

安装会获取 `pyserial>=3.5`。离线树莓派可事先另行下载 pyserial wheel，使用 `pip install --no-index --find-links <wheel目录> mid-edge`。本包不含板端固件，不自动刷写。

## 登记 USB 和启动一个板的服务

```sh
ls -l /dev/serial/by-path/ /dev/serial/by-id/
udevadm info --query=property --name=/dev/ttyUSB0
```

复制 wheel 旁的 `board.example.json` 为 `board-a.json`，填写这块板实际的稳定路径、ID_PATH、接口号、VID/PID、STA MAC 和波特率。CH340 没有唯一序列号时用 `by-path`；换 USB 插槽需更新登记。`ttyUSB0` 只用来查元数据，不写成长期配置。服务打开后会核项目固件与 STA 身份。首次用 `start_policy: observe`，沿用板端原有 Wi-Fi 与 LoRa 启动策略。

```sh
~/mid-edge-venv/bin/python -m tools.mid_edge.board_service \
  --config ./board-a.json --state ./state-a
```

业务程序只访问这个串口所有者的 HTTP API。如果原 `mid-edge@ttyUSB*.service` 已占此板，继续用原服务升级后的 API，或先停旧服务再启新实例。每块板只有一个所有者。

同一树莓派接多板时，每块板使用自己的配置文件、稳定 USB 路径、STA MAC、HTTP 端口和状态目录。例如 A 用 8780 / `state-a`，B 用 8781 / `state-b`。服务只操作本地登记的板，不遍历试开其他端口。

## Python 控制与收发

```python
from tools.mid_edge import LocalClient

board = LocalClient(8780)
print(board.lora_status())

# E1 固件的 config 命令会保存到 NVS，不需要另发 save，也不需要重编译。
result = board.lora_config(role="rx", report_period_ms=10000, start_on_boot=True)
print(result["readback"])       # matches / mismatches / not_reported
print(result["status"])         # 请求角色、worker 状态、计数和 PHY

print(board.lora_config(role="tx", report_period_ms=15000))
print(board.lora_config(role="off"))  # 只关闭 LoRa，保留 Wi-Fi 与 OLED

events = board.lora_events(after=0, wait=1)
for item in events["records"]:
    if item["event"] == "lora_ref_rx":
        print(item["report"])  # LRN1 解码后的报告者/boot/序号/邻居表
        print(item["lora"])    # 节点→LoRa 接收板的 RSSI/SNR，独立于 Wi-Fi RSSI

accepted = board.send("90:da:72:48:a5:cc", b"hello over Wi-Fi")
print(accepted)                 # 本地接纳，不代表远端交付
# 目的树莓派的 LocalClient.recv(timeout=30) 才取得目的板原始 bytes。
```

LoRa 配置成功表示固件已确认保存并接受异步应用；只有 requested_generation 与 applied_generation 一致且 worker 无故障、角色相符时，`driver_configuration_verified` 才为 true；缺少这些字段时保持 false。worker 角色相同不代表新 PHY 已应用。读回缺失的字段列在 `not_reported`，不能当作已验证；主机不自动重启设备验证 NVS。命令超时的结果未知，不自动重发。帧时长是否允许指定周期由固件最终检查。

PHY 频点、天线和参数沿用 H 的实测配置。当前试点固件只接受标称 0 dBm。只改角色/周期时不要重复填写 PHY。LoRa 邻居状态表示采样当时的观测，不给当前 9 秒 Wi-Fi 互证续期。

也可运行自带示例，默认只查状态和已有事件；传参数才修改：

```sh
python -m tools.mid_edge.lora_example --port 8780
python -m tools.mid_edge.lora_example --port 8780 --role rx --period-ms 10000 --start-on-boot true
python -m tools.mid_edge.lora_example --port 8781 --role tx --period-ms 15000 --start-on-boot true
```

LoRa 事件是有界队列，返回 cursor / oldest_cursor / truncated，连续读取时传上次 cursor。新服务会话应从 0 开始；原始事件可随同串口日志持久保存。它不是可靠邮箱，不据收件缺口直接计算丢包率。

## 可选：树莓派服务随主机开机启动

板端 `start_on_boot` 是板由充电宝供电后恢复 LoRa 角色；下面的 systemd 服务是树莓派开机后打开本地 USB 并提供 Python API。两项分别配置。包构建和安装 wheel 都不会替用户启用系统服务。

将虚拟环境安装到 unit 中固定的 `/opt/mid-edge/venv`，再准备服务账户、登记文件和 unit：

```sh
sudo python3 -m venv /opt/mid-edge/venv
sudo /opt/mid-edge/venv/bin/pip install ./mid-edge-package/mid_edge-0.4.0-py3-none-any.whl
sudo useradd --system --user-group --groups dialout --home-dir /nonexistent --shell /usr/sbin/nologin mid-edge
sudo install -d -m 755 /etc/mid-edge/boards
sudo install -m 644 ./board-a.json /etc/mid-edge/boards/a.json
sudo install -m 644 ./mid-edge-package/mid-edge-board@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mid-edge-board@a.service
```

已有 `mid-edge` 账户时跳过 useradd。第二块板另存 `b.json`，填不同 USB 路径和 HTTP 端口，再启 `mid-edge-board@b.service`。首次用 observe 策略，主机服务停止不会主动关板上 Wi-Fi。若选择已有 saved 策略，原服务会负责恢复及停止它启动的 Wi-Fi；它不会替用户写 LoRa 配置。

```sh
systemctl status mid-edge-board@a.service
journalctl -u mid-edge-board@a.service -n 50
sudo systemctl disable --now mid-edge-board@a.service
```

设备尚未枚举时服务等待重试；USB 身份或固件不符退出 78，避免反复开口。停止会关闭串口和本机 HTTP，不删除板端 NVS 或主机状态。本文的安装/控制/API 已做主机检查；树莓派 ARM、物理 USB 热插拔、PID1 自启和实际 LoRa 空口收发由相应实机记录确认。
