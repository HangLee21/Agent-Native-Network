"""把 baseline 的对应文件同步到 deploy 交付包；也可只做漂移检查。

规则：**只改 baseline，再迁移到 deploy**。这个脚本就是"迁移"那一步，避免手工拷贝
导致两边悄悄分叉（此前 /health 与 LRN1 解码器就是这样在 deploy 上被单独改掉的）。

在 baseline 仓库里运行：

    python tools\\release\\sync_to_deploy.py --deploy ..\\wt-deploy        # 同步
    python tools\\release\\sync_to_deploy.py --deploy ..\\wt-deploy --check # 只检查

同步后必须回到 deploy 目录重算发布清单：

    python tools\\release\\refresh_release_manifest.py
    python tools\\release\\verify_release.py
"""
import argparse
import hashlib
import pathlib
import sys

# baseline 路径 -> deploy 路径
PAIRS = tuple(
    ("tools/mid_baseline/gateway_probe/" + name, "app/services/tools/gateway_probe/" + name, True)
    for name in ("mkcard.py", "node_reader.py", "node_update.py", "pi_node_probe.py",
                 "set_group.py", "node_reader.service")
) + tuple(
    ("tools/mid_baseline/gateway_probe/" + name, "tools/mid_baseline/gateway_probe/" + name, True)
    for name in ("topology_server.py", "start_frontend.py", "netmode.ps1")
) + tuple(
    ("tools/mid_baseline/fleet/" + name, "app/services/tools/fleet/" + name, True)
    for name in ("fleet.py", "flash_nodes.py", "refresh_labels.py", "enable_ssh_password.py",
                 "write_site_env.py", "make_production_kit.py")
) + tuple(
    ("research/agent_native_network/mobile_gateway/" + name,
     "app/services/assets/mobile_gateway/" + name, True)
    for name in ("view.js", "studio.js", "studio-model.js", "fleet-model.js", "lora-model.js",
                 "map.js", "map.css", "index.html")
) + tuple(
    ("tools/mobile_gateway/" + name, "app/services/tools/mobile_gateway/" + name, True)
    for name in ("studio.py", "server.py", "sources.py", "state.py", "remote.py", "replay.py",
                 "node_serial.py", "fleet_registry.py", "serial_discovery.py")
) + (
    ("firmware/mid_baseline/field_agent/lora_ref/decoder.py",
     "app/services/firmware/mid_baseline/field_agent/lora_ref/decoder.py", True),
    ("tools/flight_link/gateway.py", "app/services/tools/flight_link/gateway.py", True),
    ("tools/flight_link/codec.py", "app/services/tools/flight_link/codec.py", True),
    ("tools/flight_link/archive.py", "app/services/tools/flight_link/archive.py", True),
    ("tools/release/refresh_release_manifest.py", "tools/release/refresh_release_manifest.py", True),
    ("tools/release/verify_release.py", "tools/release/verify_release.py", True),
)

BASE = pathlib.Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalised(path):
    """Compare ignoring line endings only; content must otherwise match byte for byte."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", required=True, help="deploy checkout path")
    ap.add_argument("--check", action="store_true", help="report drift only, change nothing")
    args = ap.parse_args()
    deploy = pathlib.Path(args.deploy).resolve()

    if not (deploy / "app" / "services").is_dir():
        print("not a deploy checkout:", deploy)
        return 2

    drift, copied, missing = [], [], []
    for rel_base, rel_dep, _ in PAIRS:
        source = BASE / rel_base
        target = deploy / rel_dep
        if not source.is_file():
            missing.append(("baseline 缺文件", rel_base))
            continue
        if not target.exists() or normalised(source) != normalised(target):
            drift.append(rel_dep)
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                copied.append(rel_dep)

    print("对应文件 %d 个，漂移 %d 个" % (len(PAIRS), len(drift)))
    for item in drift:
        print("  %-58s %s" % (item, "已同步" if item in copied else "不一致"))
    for label, item in missing:
        print("  %s: %s" % (label, item))

    if args.check:
        if drift:
            print("\n有漂移：先改 baseline，再运行本脚本同步。")
            return 1
        print("两边一致。")
        return 0

    if copied:
        print("\n已同步 %d 个文件。下一步在 deploy 目录运行：" % len(copied))
        print("  python tools\\release\\refresh_release_manifest.py")
        print("  python tools\\release\\verify_release.py")
    else:
        print("无需同步。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
