# 串口现场核对与固件发布（2026-11-12）

## 最终状态

五板全部应答，端口↔板子按**固件自报 MAC** 认定；`hardware/eora_hub_400tb/bindings.local.json`
的 `port`/`location`/`hwid` 已按实测刷新（其余字段未动）。原文件备份：
`.local/mid/bindings-backup-20261112.json`；变更来源：`.local/mid/bindings-remap-20261112.json`。

| 端口 | USB 位置 | MAC | 标签 | 固件 |
|---|---|---|---|---|
| COM8 | 1-1 | `90:da:72:48:a4:f8` | A | `mid-lora-ref-v1-158bf1db…934a948f` |
| COM13 | 1-2.4 | `90:da:72:48:a5:cc` | B | 同上 |
| COM16 | 1-2.1 | `90:da:72:48:a4:e0` | C | 同上 |
| COM14 | 1-2.3 | `90:da:72:48:a5:20` | D | 同上 |
| COM15 | 1-2.2 | `90:da:72:48:a6:98` | E | 同上 |

> 早前记录的 `1-1.1/1-1.2/1-1.3/1-1.4/1-2` 已作废。当时 COM13 无应答是接触问题，
> 用户重新插拔后该板恢复，并随插拔落到新的 USB 位置。

## 已执行的设备操作

1. 只读 `info` 核对五板身份（未复位、未烧录、未启射频）。
2. 五板 app-only 烧录到 `mid-lora-ref-v1-158bf1db…`：`0x10000` 偏移、每板**一次写入**、
   写前核 ROM MAC 与安全位、写后核 `build_id` 与 idle 态，端口全部关闭。
   证据：`simulation/outputs/H-019/20261112-09-flash-D` 与 `-10..-13-flash-{B,C,E,A}`。
3. 五板 LoRa 频点由 433 MHz 切到 **470 MHz**（可逆，写 NVS）：
   证据 `20261112-02..07-*-470`。
4. 五板 `route_start` 恢复 active，`field_resume` 恢复业务发生器。

## 一次被闸门拦下的写入

B 板首次烧录时我把回滚镜像的 SHA 误填成了 D 板的，`flash.py` 在**任何字节写出之前**
就中止（`image SHA/rollback SHA/1MiB app bound failed`，`write_calls=0`）。
改用 manifest 里的原值后重烧成功。这条记录保留，作为“烧前校验确实生效”的实例。

## 端口映射重建脚本

一次性工具，未入库：临时目录下按 `info` 回复重建映射；正式改动已落 `bindings.local.json`。
