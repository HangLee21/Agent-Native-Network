# M-044 脚本交付验收

2026-11-15 M-044 脚本离线交付完成，生产 05d4ca6 已推送：新增 SETUP_GATEWAY.cmd 一次初始化/回滚，START_STUDIO 默认 remote，PC主动发现并核对网关、不绑定本机LoRa接收UDP。网关标准库接收服务采用systemd socket activation，限定专用接口、普通用户运行；DHCP不下发默认路由/DNS。E2真实本机回环、H假Linux/Windows及故障重试测试、C独立增量审查已完成。真实RHF/ARM/Python3.4、systemd215、DHCP、换电脑/断电/RF未实测，本轮未改变现场网络或烧板。证据 simulation/results/20261115-M-044-gateway-deployment/。

源文件、命令与逐项测试见各子目录；SOURCE.json记录原始输出及哈希。网关新socket入口的FD检验是模拟，不将其记为真实Linux继承。C036-02回滚失败重试为五项模拟注入，未测试实机回滚。保留所有原始输出。
