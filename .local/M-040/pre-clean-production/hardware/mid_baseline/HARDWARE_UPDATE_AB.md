# A/B接入更新

用户明确通知两板接入后，有限枚举确认COM7/location1-2和新增COM8/location1-1。A沿既有MAC绑定，未重新读取A应用info；B经一次ROM识别确认为ESP32-S3 revision0.2，MAC90:da:72:48:a5:cc，实际4MiB，安全启动/Flash加密/secure-download未启用。已正常复位并关闭COM8。B应用身份及原Flash备份未验证，没有新MID烧录或无线测试。

最新动态清单是BOARD_INVENTORY_20261106_AB.json和BOARD_LABELS_20261106_AB.json。本次不改H显示FREEZE、模块源码、历史BOARD_INVENTORY和HARDWARE_HANDOFF，保留已交审27文件快照。B可由E1按已实读MAC在冻结identity API中提供标签B，不改显示模块中的A默认回退表。

当前烧录依赖：E1 FREEZE checkpoint1明确candidate_host_checkpoint_only，README明确不是flashable release，ESP-IDF适配/OLED集成/目标构建和烧录包待完成；C-018当前明确未放行MID烧录/RF。不是等待五块板到齐。可先在A/B验证，但须先有真实可烧录包及该包就绪结论。E1正式集成时须读取H冻结接口/新板号映射，E2/C按具体hash继续验证。普通交接落卡，不任意跨聊天发送。
