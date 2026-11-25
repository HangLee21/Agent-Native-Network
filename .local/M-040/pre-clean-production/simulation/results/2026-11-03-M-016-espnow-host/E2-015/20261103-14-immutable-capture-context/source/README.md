# E2-015独立协议验证

协议测试、wire参考、日志分析与硬件证据校验在本目录。当前执行状态、源码版本、失败与限制见[VALIDATION.md](VALIDATION.md)，不据测试文件存在或旧结果宣布当前固件通过。

日志分析的固定Python函数/CLI、ann.analysis.v1 schema、事件/时钟/身份/单位和H接入要求见[ANALYZER_API.md](ANALYZER_API.md)。分析器只依赖标准库；H真实测量追加需经M派发局部冻结，合成结果不得升级实测。

`CASES.json`是独立用例；`core_driver.c`在确定性测试传输上驱动实际冻结C核心，链接图只控制测试帧能否到达，不是RF/性能仿真。`wire_reference.py`按公开little-endian/CRC32格式独立生成字节，与C编解码交叉核对。`protocol_properties.py`审计归一化trace；分区仍允许失败发射，禁止虚构成功。去重保证限定boot/窗口，不承诺跨接收重启exactly-once。

有界入口：`python -B -X utf8 tests/espnow/run_validation.py --pattern test_analysis.py --output simulation/outputs/E2-015/<新run>`；协议C套件用test_core.py。每命令≤120秒，全任务累计≤600秒，输出≤100MiB；所有失败与名额留在execution_budget.jsonl和各run，拒绝覆盖。保护停止后不自动重启。

只编译M授权的冻结核心或稳定归档，测试build与source快照只写E2输出。当前H活动或未重冻结时，H模块测试显式跳过而不读活动文件；已有独立结果按当时freeze解释。主机C编译不等于ESP-IDF目标编译，没有板卡就没有无线范围、PDR、吞吐或RTT实测。不开串口、不刷写/擦除，不安装驱动、不改全局环境、不运行模型/旧ns-3。
