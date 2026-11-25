# 板级与驱动来源

- 厂商400TB原理图：https://www.ebyte.com/pdf-down/3699.html 。本轮M取得的真PDF为154188 byte，E1另存`.local/mid/E1-029/schematic.pdf`。一页图的“Peripheral and I/O mapping table”已渲染核对：NSS8、SCK9、MOSI10、MISO11、RESET12、BUSY13、DIO9 IRQ14。OLED17/18，与现有已用引脚一致。3.3VB共享电源36沿现有OLED实现，只置高、不因LoRa off拉低。
- Semtech官方EBYTE BSP固定提交：`Lora-net/one_channel_hub@7c0be623fefb1a16afd9372d10c978bddbf6f29e`，路径`components/smtc_ral/bsp/lr11xx/ebytes_esp32_lr1121.c`。SPI引脚与真原理图逐项相符；TCXO3.0V/300tick、RF switch enable7/rx2/tx3/tx_hp1、nominal0dBm的LP寄存器power3均取自该BSP。原代码/版权在vendor/reference中保留。
- LR11xx驱动：`Lora-net/SWDR001@e0fa77181f27803dcc5964b1f721a1efb2cba342`（v2.4.1），编译system/radio/regmem，原文件与LICENSE.txt保留。取得文件逐一核API目录的Git blob SHA1，来源URL/内容SHA256见UPSTREAM.json。仅下载约593KB源码，不用厂商预编译固件或LoRaWAN服务。
- HAL是本任务适配：SPI2、2MHz、mode0、手动CS、BUSY最多200ms且让出CPU，工作线程独占；读取命令/返回阶段及dummy字节沿官方HAL。仅Sub-GHz 410..493MHz，SF7..12/BW125/250/500k/CR4/5..4/8；本试点仅支持nominal0dBm配置。该值是BSP标称，不是本机测得功率。

候选先读芯片version.type并要求LR1121才配置收发，不盲目升级LR1121内部固件；初始化失败后worker报错停止，须明确配置请求才能再尝试。RSSI/SNR来自芯片packet status，未做外部校准。TCXO/RF开关及真实收发仍需H首板验证；目标编译与引脚文档相符不代替该验证。

共享ESP-NOW、OLED、业务合同及冻结E1-028包保留。E1只在E1-029隔离候选副本插入组件/命令/主任务取样及事件排出入口，入口差异见本卡与INTEGRATION.md。

目标现有sdkconfig的FreeRTOS为100Hz；本组件所有1/5ms休眠都加至少一tick，防止pdMS_TO_TICKS取整为0导致off空转或RESET脉冲过短。接收轮询时间是worker读取时刻，不冒充精确硬件IRQ时戳。
