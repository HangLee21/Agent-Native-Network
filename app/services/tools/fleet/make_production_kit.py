"""Build the production card-making kit: a small folder an operator can run with no repo.

Production only makes cards. Everything else (firmware builds, remote updates, the receiver,
the frontend) stays in the development checkout, and the developer pushes code to the fleet
over SSH later. So the kit contains exactly what mkcard.py reads at runtime plus a README:

    MK_CARD.cmd
    mkcard.py
    gateway_probe/{node_reader.py, node_update.py, pi_node_probe.py, node_reader.service}
    fleet.pub                     <- management PUBLIC key (no private key, ever)
    site.env.example              <- Wi-Fi + optional Tailscale key
    README.md                     <- one page: how to make a card

The kit deliberately excludes: firmware images, the receiver, the frontend, fleet tools,
build scripts, .local/, and the git history.
"""
import argparse
import pathlib
import shutil
import sys

def _repo_root(start):
    """Walk up to the checkout root, whatever the packaging layout is.

    This file lives at tools/mid_baseline/fleet in the development tree and at
    app/services/tools/fleet in the deploy packaging, so a fixed ../.. count breaks.
    """
    for candidate in [start] + list(start.parents):
        if (candidate / ".git").exists() or (candidate / "START_STUDIO.cmd").exists():
            return candidate
    return start


ROOT = _repo_root(pathlib.Path(__file__).resolve().parent)
PROBE = pathlib.Path(__file__).resolve().parent.parent / "gateway_probe"
HELPERS = ("node_reader.py", "node_update.py", "pi_node_probe.py",
           "node_reader.service", "set_group.py")
SIMPLE_CMDS = ("SETUP_SITE.cmd", "MK_CARDS.cmd", "SITE_STATUS.cmd",
               "SITE_FLASH.cmd", "SITE_GROUP.cmd")

SITE_ENV = """# 现场配置：做卡工具会写进每一张卡，然后从这台机器上删除也不会影响已做好的卡。
# 复制成 site.env 后填好，再运行 MK_CARD.cmd。

# --- WiFi ---
WIFI_SSID=替换成现场WiFi名称
WIFI_AUTH=psk                 # psk = 普通密码WiFi；eap = 企业802.1X
WIFI_PASSWORD=替换成现场密码
# WIFI_IDENTITY=              # 仅 eap 需要（如校园网账号）

# --- 远程管理（可选）---
# 由运维在【自己的】Tailscale 组织后台生成，建议一次性、24 小时过期。
# 留空则卡片不装 Tailscale，只能在同一局域网内访问。
TAILSCALE_AUTHKEY=

# --- SSH 登录方式（两种都支持）---
# 公钥由 fleet.pub 提供；设置下面的密码后，卡片会同时开启密码登录。
# 另一位运维如果不想带私钥，就靠这个密码登录。
SSH_PASSWORD=
"""


README = """# 生产做卡工具（只需做卡）

这个包只做一件事：**把身份写进 SD 卡**。
固件、前端、远程升级都不在这里——那部分由开发侧远程完成。

## 一、准备

1. 用 Raspberry Pi Imager 把基础镜像写到卡上
   （用户 `eora`、打开 SSH、填入管理公钥——或直接用下面的 `fleet.pub`）
2. 复制 `site.env.example` 为 `site.env`，改成现场的 WiFi / 密钥
3. 确认 `fleet.pub` 存在（管理公钥，没有它做卡会报错）

## 二、做卡

按顺序双击三个文件，不需要敲命令：

```
1) SETUP_SITE.cmd     ← 只需做一次，问几项，生成 site.env
2) 用 Imager 把基础镜像写到每张卡（用户名 eora，SSH 打开）
3) MK_CARDS.cmd       ← 问起始编号和张数，然后一张张插卡，自动编号
```

单张也可以：`MK_CARDS.cmd 6 1`（编号 6，只做一张）。

## 三、编号规则

编号写在卡上，1–255，**不能重号**。做卡前先确认自己的号段。

## 四、做完之后

插到对应树莓派上电，2–5 分钟后卡上 `/boot/firmware/eora-status.txt` 会写：

```
6/6 DONE host=eora-air-06 overlay=<管理网IP或none> ip=<局域网IP>
```

失败会写 `FAILED: <哪一步>`。把卡拔回来重新运行 `MK_CARD.cmd`，它会先打印上次失败原因。

## 五、这个包里没有什么

| 没有 | 原因 |
|---|---|
| 固件镜像 | 由开发侧远程刷写 |
| 前端 / 接收器 | 只在开发侧运行 |
| 机群工具（fleet） | 由开发侧使用 |
| 构建脚本 | 生产不需要编译 |
| `.local/` | 内含开发者个人密钥，绝不外发 |

## 六、安全

- `fleet.pub` 只是**公钥**，泄露不影响安全；对应私钥只在开发侧
- `site.env` 含 WiFi 密码与 Tailscale key，**不要外传、不要提交到任何仓库**
- 卡片本身会带这些配置，做完请妥善保管卡片
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="target directory (must be empty or absent)")
    ap.add_argument("--public-key", default=str(pathlib.Path.home() / ".ssh" / "id_ed25519_eora.pub"),
                    help="management public key file to ship (one key per line)")
    ap.add_argument("--with-flash", action="store_true",
                    help="also ship the fleet/flash tools (both operators may flash)")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit("目标目录非空：%s" % out)

    pub = pathlib.Path(args.public_key)
    if not pub.is_file():
        raise SystemExit("找不到管理公钥：%s" % pub)
    text = pub.read_text(encoding="utf-8").strip()
    if not text.startswith("ssh-ed25519 "):
        raise SystemExit("不是 ed25519 公钥：%s" % pub)

    (out / "gateway_probe").mkdir(parents=True, exist_ok=True)
    (out / "fleet").mkdir(parents=True, exist_ok=True)
    # Layout-agnostic launchers: they find python, the tools and site.env by themselves,
    # so the operator only ever double-clicks a name.
    for name in SIMPLE_CMDS:
        shutil.copy2(ROOT / name, out / name)
    shutil.copy2(PROBE / "mkcard.py", out / "gateway_probe" / "mkcard.py")
    for name in HELPERS:
        shutil.copy2(PROBE / name, out / "gateway_probe" / name)
    if args.with_flash:
        for name in ("fleet.py", "flash_nodes.py", "refresh_labels.py"):
            shutil.copy2(ROOT / "tools" / "mid_baseline" / "fleet" / name, out / "fleet" / name)
        for name in ("FLEET_STATUS.cmd", "FLASH_NODES.cmd"):
            shutil.copy2(ROOT / name, out / name)
        (out / "config").mkdir(exist_ok=True)
        for name in ("fleet.hosts.example.json", "fleet.groups.example.json"):
            shutil.copy2(ROOT / "config" / name, out / "config" / name)
        print("   + fleet/flash tools included")
    (out / "fleet.pub").write_text(text + "\n", encoding="utf-8")
    (out / "site.env.example").write_text(SITE_ENV, encoding="utf-8-sig")
    (out / "README.md").write_text(README, encoding="utf-8")

    print("production kit -> %s" % out)
    for item in sorted(out.rglob("*")):
        if item.is_file():
            print("   %-42s %6d B" % (item.relative_to(out), item.stat().st_size))
    print("\n检查：包里不应出现任何私钥、.local、固件镜像、前端资源。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
