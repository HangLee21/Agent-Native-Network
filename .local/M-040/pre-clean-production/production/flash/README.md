# 节点烧录入口

双击根目录 `FLASH_NODES.cmd`。自动识别和烧录适配器已实现并经过隔离模拟测试；目前没有冻结发布包，也没有实板验证，不能作为正式交付。完整发布包缺失时程序在枚举串口前停止。运行环境需要 Python 3、pyserial 和 esptool；已参考的工具版本为 pyserial 3.5、esptool 4.13.0，程序不自动下载安装。

面向对接人的默认入口无需填写命令或选择串口：程序根据完整MAC识别节点，逐板显示进度，日志保存在 `production/local/logs/`。新板编号记录在 `production/local/registry.json`，沿用原有配置的设备保留已保存网络组号和频道；没有可用自启配置的新板需要交付方在 fleet 配置中提供 `network.group`、`network.channel`，不会猜测。新板编号与前端自动同步尚待集成。离线模拟结果不证明实际烧录或断电自启成功。

`FLASH_NODES.cmd --self-test` 只运行假设备测试。`FLASH_NODES.cmd --dry-run --config <fleet.json> --release <manifest.json>` 只校验文件和镜像，不枚举或打开串口。配置缺省优先 `production/local/fleet.json`，其次使用 D 提供的 `production/config/fleet.example.json`；重复 MAC、重复编号直接拒绝。编号映射来自配置，不能由 COM 顺序推导。

`manifest.example.json` 的未知字段为 null；它不是发布包。版本、完整来源提交、协议、芯片、app 偏移、完整4KiB分区表和 SHA256 等必要字段缺失或不符时不能写板。烧录前核对应用身份和 ROM MAC、安全状态、分区表，再 app-only 写 0x10000；随后设置并读回数字 ID、build_id 和网络自启设置。故障按板记录；即使读回通过也须另做断电验证。`--rollback --release <已验证清单>` 明确选择回滚版本，同样执行身份和分区核验。运行时不得执行全片擦除。

程序在实际写入前同步保存设备MAC、目标镜像和分区摘要、编号及原网络设置，并记录“结果待定”。再次双击时，若应用仍能正常应答，先核对版本、编号和配置并完成恢复；若应用无法应答，则仅尝试原 USB 位置，并在 ROM MAC、安全状态、分区和同一镜像均匹配时恢复应用，保留 NVS。历史记录缺少必要信息、日志损坏、USB位置或身份不符时会停止，不盲写。不要删除日志绕过核验。自动发现最多三次、间隔5秒；仍未恢复可将设备插回原 USB 接口后再次双击。残留锁文件由操作系统锁判定，不要求手动删除。以上均仅经离线模拟，实际USB驱动、ROM和断电恢复尚未实测。

从明确提交准备待审候选：`python production/release/prepare_release.py --commit <完整commit> --image <明确的app.bin> --output production/release/<新目录>`；加 `--dry-run` 仅检查参数、提交和哈希，不生成文件。脚本只从提交归档 firmware/production 并复制明确指定的镜像，记录哈希；不会自动从研发工作树同步或烧板。归档不证明镜像与该提交有关，必须独立提供构建记录、build_id、分区布局、兼容性与其他清单字段后才能发布。状态只有实机验收后才能由负责人改为 validated。
