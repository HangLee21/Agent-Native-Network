# 本次发布、当前状态与证据

2026-11-08。当前ABC为OLED正式包、MID兼容空闲，已清除离线profile，全部stop/closed；A COM12、B COM10、C COM7，MAC及460800/8N1见QUICKSTART。换机须重选本机端口。切offline先分别执行--profile，当前不能直接当作NVS仍在。

## 固件与部署文件

- OLED调试：`.local/mid/E1-023/oled-package-02/`；build `mid-edge-v1-1969b4d894badc0f1c59940fc426b779a14f49b89cca5fedd69a8216d90da143`；`mid_edge.bin` SHA256 `71e1cddf67263ae3c98d83c5dd6521c6067a63192636e43292ce17159004fbcf`；`PACKAGE_MANIFEST.json` SHA256 `fe222ad894f469b0239cc1096209e47ff9ce92923f9be80bd54cb11b44f6c35d`。
- 无屏上线候选：`.local/mid/E1-023/headless-package-01/`；build `mid-edge-v1-26f0f3bbc58fdfa29be384118d069c8c11328dc7efe5ff5aa7aac35cc2346efa`；`mid_edge.bin` SHA256 `3c5ac572e5a236fb84e7f1041ccc5a80ddbd53f946ad7f32556034a761d20b58`；`PACKAGE_MANIFEST.json` SHA256 `be219b29434a88cd87cd333700f0d94150c6b9d72292c5c2aa6d491aedc61e83`。

本目录`profiles/abc-deploy.json`逐字节复制E1正式03配置，SHA256 `fdcc22923a38146df24221a304901377056f4813763b33bda29f3f56cc2f9f1f`，profile_id `abc-two-way-v1`。三节点同表，实际MAC绑定；不含COM、主机IP或一次启动的publisher_boot。`configs/*.windows.json`是当前端口示例，换机须修改，不能照搬旧E2示例A COM7/C COM12。

两个包的HANDOFF.json是正式app-only刷写参数与退回方案；已有板本轮无需再刷。设备持有者换包时核对实际MAC、idle/队列及镜像hash，只在已核兼容boot/分区布局上按HANDOFF写0x10000 app，不擦NVS/eFuse，不将本机Windows SDK绝对路径当成Linux通用路径。空白新板须先满足相应完整固件/分区前提，不能直接套app-only。OLED/headless共用NVS，autostart=true会在刷后复位自动启用射频，刷前stop不意味着刷后仍关。

D本轮实算核对两正式包的app与清单hash、正式配置复制一致；只读，不编译、不烧录、不打开串口。原包/manifest/失败构建记录均保留。

## 对应证据

- 正式发布目录以`coordination/tasks/E1-023.md`及两个包HANDOFF为准；09-final-audit核对共同业务源码及两目标清单。无屏构建不链接I2C/renderer，纯C计数模型保留。
- `simulation/outputs/H-012/20261108-14-local-edge/`真实本地CLI与ABC RF；原监督success=false/AssertionError保留。H15及`simulation/outputs/E2-023/20261108-04-real-local-audit/checks.json`沿保存日志核3/3与A/B复位，无远端boot重绑；第三包未保存独立stdin，不把汇总当原始输入证据。
- `simulation/outputs/E2-023/20261108-05-headless-audit/checks.json`核无屏C应用1/1、原payload/身份与display_enabled=false。实际I2C总线活动没有另做电测。
- `simulation/outputs/H-012/20261108-29-user-OLED-confirmation/result.json`为用户实物观察：三块业务页正常、PRG约5秒回首页；没有D摄像像素证据。
- `simulation/outputs/H-012/20261108-26-restore-MID-mode/`、27-final-bindings、30-final-service-state、31-final-handoff保留清profile/MIDidle/新端口/交接状态。
- `simulation/outputs/D-023/20261108-05-c-port-retest/`：端口修正后新的52字节网页ABC 1/1，run5338f99667a591caf2fa2d77。它是台架路径，不代替offline模式或三台物理主机验证。

同PC三个独立单板进程和真实RF已验证；三台物理边缘主机、Linux实机、真实断电循环尚未验证。软件复位不等于断电。本轮没有远端ACK、持久业务邮箱、可靠重发、加密或协议版本协商的新增交付；应用必须看目的端原始字节/身份。
