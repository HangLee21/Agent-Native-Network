# M-044 接口与部署合同

总体路径：节点 LoRa → RHF2S008 packet forwarder → 网关本地接收服务；PC Studio 主动从网关 HTTP 读取。packet forwarder 固定 localhost:1680，接收服务正确回 PUSH/PULL ACK。板间 ESP-NOW 不变。

网关保留 192.168.137.200/24 作为本次专用直连接口地址，DHCP 池与该地址隔离；仅对明确指定的专用以太网接口提供 DHCP，禁止默认路由与 DNS 下发，不在校园/共享 LAN 上自动启动 DHCP。安装器显示目标接口、地址、EUI和变更，保存原始服务/配置、原开关状态；提供幂等安装和完整回滚，不覆盖无关配置。选择其他子网时通过参数整体配置，PC 发现不得硬绑网段。真实系统/依赖版本先检查，缺依赖给明确错误；不要假定 Python3.11 可在旧 ARM 系统运行。

远端服务合同：
- HTTP 默认 8780：保持现有 GET /api/v1/lora/topology；新增 GET /api/v1/appliance，schema=ann.gateway.appliance.v1，含 gateway_eui、api_version=1、服务就绪状态。身份是设备匹配，不等同真实 LoRa 上报/在线。
- UDP 发现默认 8781，仅直连 LAN；请求 schema=ann.gateway.discover.v1，nonce；响应同 schema、原 nonce、gateway_eui、api_version=1、http_port。PC 只使用回复源 IP，经 HTTP 身份再次核对；不采信回复提供的任意URL，不向公网扫网。提供显式候选IP作为发现失败回退；HTTP有界超时/退避，无网关仍开完整 Studio。
- PC 配置 gateway.mode=remote、http_port=8780、discovery_port=8781；candidate_hosts 保留回退，eui 必须核对。缺 mode 的旧配置迁移规则由 E2 明确实现，不能静默继续电脑 UDP 接收而让新架构无效；保留显式 legacy_local 可回滚旧部署。
- 不把发现响应/API就绪当作 RF接收成功。gateway_observed、report freshness、离线状态保持真实；连接失败不能把旧数据标在线。
- 网关服务只接收默认启用；现有 control.enabled=false 约束保留。远端命令接口若暴露，必须显式启用并认证，未启用返回清晰拒绝；本轮没有真实发射参数核验，不能自动解锁。
- PC 本地 Studio 继续使用127.0.0.1:8794和原页面/数字映射。浏览器打开按M043；控制台显示实际地址、发现/连接/离线原因。不操作或强杀无关实例；旧版自身实例不能加载新配置时给明确重启提示。

H 安装器读取同一 app/services 包和 manifest，部署服务最小依赖；E2给 H 实际CLI与最低Python版本交接，不再多复制一套维护源码。systemd自启/异常重启、日志有界、只读运行目录/可写状态目录分离。实现中合同必要变更在本文件由M登记，窗口不得私下分叉。

## 初次安装引导
现网关尚无DHCP时，PC为169.254/16无法SSH到192.168.137.200。H的一次性安装工具必须覆盖该引导：检测已可达则直接用；不可达时明确选择唯一专用有线接口（多候选需用户选，不能误改Wi-Fi/虚拟网卡），显示变更并经UAC临时配置同网段地址用于SSH，保存原配置；安装成功或失败均恢复原电脑地址分配配置，成功后DHCP续租验证。也提供已有可达连接的无改网卡模式。不要为便利禁用其他网卡/改默认路由/DNS/全局防火墙。本轮只实现及模拟测试此逻辑，不实际改变现场网卡。

## 已确定的部署依赖
E2 已改为 Python 3.4 语法兼容的标准库服务，入口 tools.flight_link.appliance；仅需 app/services/tools/flight_link/appliance.py、compat_decoder.py（保持目录/namespace包路径）。真实Python3.4/ARM运行尚未验证。M在最终 firmware/manifest.json 添加 gateway_appliance：module、minimum_python=[3,4]、files两路径，所有文件仍列入service_files_sha256；H从此元数据打包/检查，不硬编码旧3.8。Windows临时地址会关闭接口DHCP，H只允许明确选择的专用有线口且无默认路由，finally恢复所保存配置，原本DHCP且安装成功则续租。

## C-036 部署边界修正
appliance 新增可选 --interface <专用网口>，Linux 对 HTTP 和 UDP发现套接字绑定 SO_BINDTODEVICE；安装生成的服务必须传该参数，指定绑定失败则拒绝启动。UDP仍接受该接口的广播，不仅绑定某个IP而丢失广播。PC本机回环测试可省略此参数；真实多网口Linux隔离需现场验证。Windows成功安装后不能只执行renew，必须检查已取得预期子网地址并核网关身份可达，未达成则报告具体未完成状态。

## 最终低权限方案（替代服务自行绑定）
历史Linux4.4的非特权服务无法自行SO_BINDTODEVICE；提升root/CAP_NET_RAW被自动审批拒绝，禁止重试或绕过。采用systemd socket activation：安装器创建HTTP和UDP discovery两个.socket单位，BindToDevice限定专用接口，Service指向ann-gateway.service；服务仍User=nobody，通过Sockets=获得FD。E2 CLI --systemd-sockets校验LISTEN_PID/FDS并按SO_TYPE识别两个socket，不依赖systemd227才引入的LISTEN_FDNAMES；校验端口/设备并复用，不再绑定。forwarder接收仍127.0.0.1:1680。两socket单位纳入备份/启动/禁用/回滚，避免残留自动拉起服务。旧直接--interface仅供明确有权限的独立测试，实际安装使用继承路径。
依据：https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html 与 https://freedesktop.org/software/systemd/man/latest/sd_listen_fds.html 。真实systemd215/ARM尚未验证。
