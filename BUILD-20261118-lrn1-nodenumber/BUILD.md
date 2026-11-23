# BUILD 2026-11-18 · LRN1 携带节点编号

## 内容

`lrn1_build` 在帧头第 35 字节写入设备编号，接收端从空口学到 `MAC → 编号`，
不再需要维护名单文件，也不需要 Pi 在线。

来源提交：`158c1b4`（代码）· 构建于 2026-11-18 11:07

## 镜像

| 文件 | 字节 | SHA256 |
|---|---:|---|
| `images/mid_edge.bin` | 970032 | `02C17B12C73D735604540653D7BE10CC2ACBA092DF6A0A57B45FB5930EDC4F60` |
| `images/bootloader.bin` | 21056 | — |
| `images/partition-table.bin` | 3072 | — |

**运行时 build_id**（`info` 应答中）：

```
mid-lora-ref-v1-bb52a9c1199c5cfba959c0602a6861c283a8b77dd362763a63c1121287e7a306
```

`fleet status` 显示其尾部 `121287e7a306`。

## 构建方式

打包的 IDF 是**精简安装**（无 riscv/openocd/ccache/dfu-util），
`export.ps1` 会把这些缺失当成致命错误而中止。因此环境变量手工装配：

```
IDF_PATH            = .local\espnow\E1-015\sdk\esp-idf-v5.5.1
IDF_TOOLS_PATH      = .local\espnow\E1-015\tools          ← 注意不是 E1-015
IDF_PYTHON_ENV_PATH = .local\espnow\E1-015\tools\python_env\idf5.5_py3.11_env
PATH 前置           = xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin
                      tools\tools\cmake\3.30.2\bin
                      tools\tools\ninja\1.12.1
```

构建脚本：`.local\mid\build_manual.ps1`（本机工具，不进版本库）

```
python <IDF>\tools\idf.py -C <project>\idf -B <build> build
```

分区余量：app 分区 4 032 KB，镜像 970 KB，**剩余 77%**。

## 刷写验证（fleet update）

```
eora-air-01    OK  VERIFIED: node is running the image that was just flashed
eora-air-02    OK  VERIFIED
eora-air-03    OK  VERIFIED
```

`fleet status` 三台均为 `121287e7a306`。

## 空口验证

亿佰特 E870-L（`a4f00fe57b830000`）转发，`topology_server` **不加载任何名单文件**：

```
frames=10  lrn1=10
90:da:72:48:a4:f8 -> 编号 1
90:da:72:48:a5:cc -> 编号 2
90:da:72:48:a4:e0 -> 编号 3
标签表: {'...a4:f8': '1', '...a5:cc': '2', '...a4:e0': '3', 'a4f00fe57b830000': 'E870L-470'}
```

编号与网关名全部来自空口，证明"不依赖名单"成立。

## 过程中修掉的两个问题

1. **Pi 2 / Pi 3 没装 esptool** → `flash FAILED:` 且错误信息为空。
   补装 `python3 -m pip install --user --break-system-packages esptool`（5.6.0）后恢复。
2. **网关丢了 DHCP 租约** → 我的迷你 DHCP 守护停掉后，网关拒在网段外。
   用新加的 `--only-mac a4:f0:0f:e5:7b:83` 重启守护，只应答这一台，
   网关立刻回到 `192.168.137.11`，且不会污染其他网络。

## 遗留建议

网关仍是 **DHCP 客户端**，依赖 PC 上那个守护常驻。
建议把它改成静态 `192.168.137.11/24`（网关不设默认网关），
这样 `lab` 模式下无需任何 DHCP 服务即可工作。
