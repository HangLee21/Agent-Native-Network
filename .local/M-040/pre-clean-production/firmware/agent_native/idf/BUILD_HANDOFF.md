# E1-015：ESP32-S3 实际目标构建交接

2026-11-06，M-017。实际构建与离线镜像校验已通过，尚未烧录或实板启动。协议核心 src/include 的6份文件与 M-016 冻结 hash、构建副本一致；本轮只为目标配置在 idf/sdkconfig.defaults 显式固定 DIO/40MHz/2MiB、关闭 PSRAM，未更改协议机制。

## 实际交付

烧录包目录：`D:\Multi-Agent Network\.local\espnow\E1-015\package-01\`。完整文件清单与 SHA256 以包内 `PACKAGE_MANIFEST.json` 为准，该清单自身 hash 记录在 E1-015 主卡。`HANDOFF.json` 给出机器可读的偏移、大小、配置和预期 info；`flash_args`、`flasher_args.json` 均来自实际构建，原样保留。

| 偏移 | 文件 | 字节 | SHA256 |
|---|---|---:|---|
| 0x0 | bootloader/bootloader.bin | 21056 | b36ab601ce3034b42b83318d2593a22fceb6ad4f2456e3f6d0adab2ceb48847f |
| 0x8000 | partition_table/partition-table.bin | 3072 | 7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820 |
| 0x10000 | ann_espnow.bin | 789792 | 34b15f7bc22ab5c220f7f3a3c9fae069caf8ec8ddea41a15889dd0e30a523a8a |

运行时串口 `build_id` 必须为：

`ann-v1-edf06224e6071c14780ba44b4b209f02c29c4d1625a462765f50476e78c810dd`

该字符串已按实际参与构建的 adapter/core/header 字节重新计算，并在应用 bin 中找到。镜像 app version 是 `b7f16ea-dirty`，与运行时 build_id 为两个字段；H应核对后者，不能把 Git 简短版本串当成源码唯一标识。

## 配置与实物前置条件

目标 ESP32-S3，DIO、40MHz，镜像 Flash header 2MiB，PSRAM关闭；UART0、115200、8N1，main task stack12288 byte。完整 sdkconfig、defaults、project_description.json、ELF/map 与实际 partition CSV 均在包内。

分区为 nvs:0x9000/24KiB、phy_init:0xf000/4KiB、factory:0x10000/1MiB。应用大小0xc0d20，构建分区检查通过，factory约25%空闲。布局及镜像要求物理Flash至少2MiB；H-004主卡已识别同一设备为ESP32-S3 revision0.2、实际Flash4MiB、MAC90:da:72:48:a4:f8，故容量满足，但写入前仍由H重新核对设备关联/安全状态。关闭PSRAM不依赖尚未实测的板载PSRAM容量。

H-004阶段A当前记录原Flash备份失败，bytes/hash=null；**M解除阶段B依赖前，H必须完成实际4MiB原Flash备份及长度/hash确认**。镜像header为2MiB不意味着原板只需备份2MiB。E1仅交构建，不代替H认定备份通过。保留原NVS/phy_init数据，不生成这两个数据分区的新镜像。

## H可直接使用的工具与命令

已验证不依赖 R: 别名的Python路径：

`D:\Multi-Agent Network\.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe`

该环境内 esptool4.13.0。离线 image_info 已用上述物理路径成功运行，两个镜像的 checksum/validation hash 均有效。工具启动形式为 `[python绝对路径, '-m', 'esptool', ...]`，H通过参数数组调用，工作目录设为 package-01；`HANDOFF.json` 保存完整候选参数数组。

H确认备份与身份、收到M阶段B交接后，候选命令如下，`$BoundPort`由H根据本轮绑定确认（当前候选COM7）：

```powershell
Set-Location -LiteralPath 'D:\Multi-Agent Network\.local\espnow\E1-015\package-01'
& 'D:\Multi-Agent Network\.local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe' -m esptool --chip esp32s3 --port $BoundPort --baud 460800 --before default_reset --after hard_reset write_flash '@flash_args'
```

E1没有执行此命令；本轮没有打开物理串口。命令使用实际flash_args中的三个bin，不额外全片erase或写eFuse。启动后只核nonce对应的 ann.serial.v1 info：node_id等于H确认的MAC、上述build_id、firmware=ann-espnow、protocol=1、chip=esp32s3、board=unverified、mode=idle；可读stats，不arm/start/bench。端到端无线交付、距离/PDR/吞吐/RTT仍无本轮证据。

## 版本、来源和执行证据

官方 ESP-IDF v5.5.1，commit `fcae32885b0296b32044cb99ecbdc50d98dddb83`。发布SDK zip1414183542 byte，SHA256 `7dfcf8ddca496940a06ea2598fc349554d6ac73a40d041c42e95d8aff5cd07b1`，与官方release API发布digest一致。工具使用该tag的tools.json推荐版本和发布SHA256：Xtensa GCC14.2.0（esp-14.2.0_20241119）、CMake3.30.2、Ninja1.12.1；全部归档校验通过。Python3.11.5，esptool4.13.0，完整60包版本与官方constraints文件/hash已保存。下载仅官方GitHub分发及Espressif Python索引，安装局限任务.local，无系统PATH/全局包/驱动安装。

SDK Git版本实际显示`v5.5.1-dirty`，保留Windows ZIP解压后的执行位变化和子模块状态记录，未冒称干净checkout。源码归档SHA、准确commit与实际版本并列记录。构建过程使用临时R:别名缓解带空格的SDK路径；每个隔离作业核对并重新建立指向本任务.local的映射。给H的烧录工具和包均使用物理绝对路径，无需该构建别名。

实际配置命令为 idf.py reconfigure，独立 sdkconfig位于 `.local/espnow/E1-015/configs/sdkconfig-01`；构建用 CMake --build --parallel2，build目录 `.local/espnow/E1-015/build/01`。全部工具环境及复现脚本在 `.local/espnow/E1-015/`，无历史目录覆盖。源副本、sdkconfig与工具环境的hash是复现依据。

`simulation/outputs/E1-015/20261106-01-prepare/`保存下载与首次跨会话映射失败；02工具安装、03Python环境、04实际配置、05目标构建、06实际版本、07-package/07-package-job打包、08离线镜像检查分别留日志/manifest。所有安装/构建/检查进程均已退出后交审。旧主机套件未重跑，旧FREEZE/golden未改。
