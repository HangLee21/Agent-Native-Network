"""校验 ARM 网关用的 compat_decoder 与主机解码器行为一致。

compat_decoder.py 是 Python 3.4 的手工副本（ARM 运行时不能跑 f-string 版本），
两份实现没有任何机制保证一致。这里用一组构造帧逐一比对"接受/拒绝"与关键字段，
在部署包里跑一次即可发现漂移。

    python tools\\release\\check_decoder_parity.py [--deploy <path>]

找不到 compat 副本时（开发树）跳过并返回 0。
"""
import argparse
import importlib.util
import pathlib
import struct
import sys
import zlib

HEADER = struct.Struct("<4sBBBB6sIIQIBBII")
ROW = struct.Struct("<6sIBBHHbHB")
STATUS = struct.Struct("<BHbBBBBbBBBbBHbBBB")
GPS = struct.Struct("<BiiHHhBBB2s")
OBS = bytes.fromhex("90da7248a4f8")
PEER = bytes.fromhex("90da7248a5cc")


def build(flags, node_number, status=False, gps=False, count=1, total=1, corrupt=False):
    hdr = HEADER.pack(b"LRN1", 44, 20, flags, count, OBS, 1234, 5, 111, 31,
                      total, node_number, 10000, 0)
    body = hdr
    for _ in range(count):
        body += ROW.pack(PEER, 77, 2, 7, 900, 450, -70, 300, 0)
    if status:
        body += STATUS.pack(1, 3300, 31, 80, 2, 0, 1, 0, 7, 0, 0, 28, 120, 85, -60, 0, 100, 6) + b"\x00" * 4
    if gps:
        body += GPS.pack(3, 399000000, 1163000000, 55, 1200, 9000, 9, 8, 9, b"\x00\x00")
    crc = zlib.crc32(body)
    if corrupt:
        crc ^= 0xFFFFFFFF
    return body + struct.pack("<I", crc)


CASES = (
    ("old", dict(flags=0, node_number=0)),
    ("node-number", dict(flags=0, node_number=12)),
    ("status-block", dict(flags=8, node_number=12, status=True)),
    ("status+gps", dict(flags=24, node_number=12, status=True, gps=True)),
    ("truncated", dict(flags=1, node_number=12, count=1, total=3)),
    ("bad-crc", dict(flags=0, node_number=0, corrupt=True)),
    ("bad-flags", dict(flags=0x20, node_number=0)),
)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", help="deploy checkout path")
    args = ap.parse_args()

    root = pathlib.Path(args.deploy).resolve() if args.deploy else pathlib.Path(__file__).resolve().parents[2]
    host = root / "app/services/firmware/mid_baseline/field_agent/lora_ref/decoder.py"
    compat = root / "app/services/tools/flight_link/compat_decoder.py"
    if not host.is_file():
        host = root / "firmware/mid_baseline/field_agent/lora_ref/decoder.py"
    if not compat.is_file():
        print("跳过：找不到 compat_decoder.py（开发树没有这个 ARM 副本）")
        return 0
    if not host.is_file():
        print("失败：找不到主机解码器", host)
        return 2

    a = load(host, "host_decoder")
    b = load(compat, "compat_decoder")
    failed = 0
    for label, kwargs in CASES:
        frame = build(**kwargs)
        ra = rb = None
        ea = eb = None
        try:
            ra = a.decode_frame(frame)
        except Exception as exc:
            ea = type(exc).__name__
        try:
            rb = b.decode_frame(frame)
        except Exception as exc:
            eb = type(exc).__name__
        accepted_a = ra is not None
        accepted_b = rb is not None
        same = accepted_a == accepted_b
        detail = ""
        if accepted_a and accepted_b:
            if ra.get("node_number") != rb.get("node_number"):
                same = False
                detail = " node_number %s!=%s" % (ra.get("node_number"), rb.get("node_number"))
            if bool(ra.get("status")) != bool(rb.get("status")):
                same = False
                detail += " status 不一致"
            if bool(ra.get("gps")) != bool(rb.get("gps")):
                same = False
                detail += " gps 不一致"
        elif not same:
            detail = " host=%s compat=%s" % ("接受" if accepted_a else ea, "接受" if accepted_b else eb)
        print("  %-14s %s%s" % (label, "一致" if same else "不一致", detail))
        if not same:
            failed += 1

    print("\n%d/%d 一致" % (len(CASES) - failed, len(CASES)))
    if failed:
        print("compat_decoder.py 与主机解码器已漂移：请按主机实现重新生成该副本。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
