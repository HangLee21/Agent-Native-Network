# M-048 网关依赖分析

## 已知事实与缺口

- 本地 `simulation/results/20261113-H019-gateway-inventory/SOURCE.json` 保存的是 2026-11-13 只读盘点：RHF2S008 / CM3、Raspbian 8 Jessie、内核 4.4.50-v7+、armv7l。现状可能已变化；CPU 的 armv7l 不能代替 dpkg 的架构和 ABI。
- 同目录 `lora_receiver.py` 的 shebang 为 `/usr/bin/env python2`，说明当时脚本期望 Python 2，**不证明当前 python2 命令可执行**，也没有记录 Python 3、dnsmasq、dpkg 安装状态或库依赖。
- 本轮用户遇到 `sudo: python3: command not found`，只证明该 sudo 调用路径下未找到该命令；不能断定网关无其他路径 Python 3，也不能推断 dnsmasq 状态。
- 针对生产 app/gateway_setup、runtime、历史网关盘点和 H-023 输出目录做文件名检索，未发现可直接交付的 `.deb`；只检查了这些目录，不声明整个磁盘不存在。现有 runtime/python 是 Windows 解释器，不是 ARM Linux 运行时。

## 建议的单次只读预检

H 的同一 SSH/sudo 会话在任何安装或配置写入之前，用 POSIX shell 一次性收集：

1. `/etc/os-release`（缺失时 `/etc/debian_version`）、`uname -m`、`dpkg --print-architecture`、`dpkg --print-foreign-architectures`、`getconf GNU_LIBC_VERSION`、`systemctl --version`、可写空间 `df -Pk`。
2. 分别在普通用户和实际 sudo 环境记录 PATH 与 `command -v python3 python3.4 python dnsmasq ip systemctl dpkg apt-get`，并检查 `/usr/bin/python3`、`/usr/bin/python3.4` 等具体路径。对发现的候选逐个运行版本和最小标准库导入：`import sys,socket,socketserver,http.server,json,struct,zlib,base64,binascii,threading,time,argparse,re,os`；输出版本和导入结果，不启动服务。
3. 用 `dpkg-query` 检查 python3、python3-minimal、python3.4、python3.4-minimal、libpython3.4-minimal、libpython3.4-stdlib、dnsmasq、dnsmasq-base、libc6、zlib1g、libexpat1 等已安装状态/版本/架构；列出 `/var/cache/apt/archives/*.deb` 的包名、版本和架构。这里只是预检名单，不是完整依赖闭包。
4. 检查 dnsmasq 可执行路径与 `--version`，以及当前 service 状态和已占用端口，区分已有可用功能与包名。保留既有来源列表和系统配置，只读检查，不运行 apt update/install 或改系统时间。

## 交付路线

- 首选：若有可执行且标准库完整的 Python >=3.4，安装器使用预检确认的**绝对路径**贯通 sudo 和 systemd；若 dnsmasq 也可用，不需要添加包。systemd socket activation 和完整安装仍须另测，Python语法解析不是运行证明。
- 确实缺失时：先依据上述单次清单确定发行版、dpkg架构与已安装库，再在隔离构建机基于对应的 Raspbian Jessie 已签名仓库索引求解 Python 和 dnsmasq 的**完整依赖闭包**。验证索引签名/受信密钥和每个包的 SHA-256、版本、架构、依赖；在与目标相同 ABI、库版本的隔离环境做离线安装模拟、导入与启动验证。把明确版本及闭包随交付包携带，安装前再次核对目标环境，缺包/冲突时停止，不做全系统升级。不能仅下载单个 python3.4 二进制，标准库和依赖也必须齐全；不能仅因 armv7l 就选通用 armhf 包或混用 Debian 与 Raspbian 软件源。
- 可查来源（仅证明目录存在，不证明已下载、签名有效或目标兼容）：Raspbian Jessie 仓库 `https://legacy.raspbian.org/raspbian/dists/jessie/`；其 Python 3.4 包目录 `https://legacy.raspbian.org/raspbian/pool/main/p/python3.4/`；Raspbian 历史快照 dnsmasq 目录 `https://snapshot.raspbian.org/201908311732/raspbian/pool/main/d/dnsmasq/`。应从同一可信发行版/版本索引解出闭包，不能因目录展示的文件名就直接安装。
- Python 2 重写不是当前现成替代：历史脚本仅打印并 ACK；当前安装器、服务/解码器和接口依赖 Python 3，且 DHCP 仍需处理。若采取该路线，需要独立实现、审查并验证完整协议，不能把历史接收脚本当成可交付服务。

本分析没有登录网关、下载/安装包、修改生产文件或网络配置；实际安装和版本兼容均未验证。
