# 三设备本地收发与可选OLED

新增[AD-HOC自主多跳与一车一板指南](ADHOC_AUTONOMOUS.md)：从8767首页进入本机8780工作台，只给最终目的MAC和原始载荷，由板端寻路。包含Ubuntu首次配置、自启、业务API和恢复命令；自主OLED包已发布，自主无屏包及真实RF状态分别说明。

新增[Ubuntu一车一板与自主邻居发现指南](UBUNTU_DISCOVERY.md)，对应M-027及新发现目标。它与下面已保存的ABC预配置多跳分开；新发现固件/Ubuntu实板验收状态看E1-024/E2-025/H-014主卡。

从[快速开始](QUICKSTART.md)执行：分别接A/B/C、选本地端口、首次--profile部署、C先收、A发文字或原始字节、B自动中继，最后按步骤回台架。所有应用命令显式`--baud 460800`。

当前端口例为A COM12/B COM10/C COM7，换机按实际MAC重新选本机端口。当前ABC已回OLED/MIDidle且离线profile已清除，首次offline部署步骤不可省略。三主机之间不转运业务数据，不依赖8766/8767；每台只拥有本地一个串口。OLED只显示业务事件，无屏固件保留同一收发API。

同PC三个独立进程+三RF板、B/A复位后收件、无屏C收件已有证据。三台物理主机、Linux实机和真实断电循环未验证。用户已确认OLED业务首页和PRG返回正常，来源及固件/配置SHA见[正式发布与证据](RELEASE.md)及机器可读RELEASE.json。

目录：profiles/abc-deploy.json为正式E1共同部署命令的逐字节副本；configs/*.windows.json为可编辑本机端口例。已有CLI支持--config；部署时--profile应指deploy.json，不是profile.json。
