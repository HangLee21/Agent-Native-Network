"""Set a node's mesh group and Wi-Fi channel over its Pi's USB serial link.

Runs ON THE PI (needs pyserial and pi_node_probe.py next to it). fleet.py drives it:
it stops node_reader, runs this, restarts node_reader. Group and channel are stored in the
node's NVS, so **no reflash is needed** to move a board between groups.

    python3 set_group.py <group> <channel>
"""
import json
import sys

from pi_node_probe import Node, candidate_ports


def main(argv):
    if len(argv) != 3:
        print("usage: set_group.py <group> <channel>", file=sys.stderr)
        return 2
    try:
        group, channel = int(argv[1]), int(argv[2])
    except ValueError:
        print("group and channel must be integers", file=sys.stderr)
        return 2
    if not (0 <= group <= 0xFFFFFFFF) or not (1 <= channel <= 13):
        print("group must be 0..2^32-1 and channel 1..13", file=sys.stderr)
        return 2

    ports = candidate_ports()
    if not ports:
        print("no serial port: is a node attached to this Pi?", file=sys.stderr)
        return 1

    node = Node(ports[0])
    try:
        # The firmware only accepts discover_config while the radio is idle, so stop first.
        try:
            node.ask("stop", timeout=4)
        except TimeoutError:
            pass  # already idle is fine
        # The fleet runs the source-routing profile, whose configuration command is
        # route_config; discover_config belongs to the legacy neighbour-table profile and
        # is rejected there (the reply came back ok=false with the group unchanged).
        # Try the routing profile first and fall back, so one build works for both.
        args = {"group": group, "channel": channel, "autostart": True}
        reply = node.ask("route_config", timeout=6, extra=args)
        chosen = "route_config"
        if not reply.get("ok"):
            fallback = node.ask("discover_config", timeout=6, extra=args)
            if fallback.get("ok"):
                reply, chosen = fallback, "discover_config"
        info = node.ask("info", timeout=6)
    finally:
        node.close()

    ok = bool(reply.get("ok"))
    print(json.dumps({
        "ok": ok, "why": reply.get("why"), "command_used": chosen,
        "group_requested": group, "channel_requested": channel,
        "group_reported": info.get("group"), "channel_reported": info.get("channel"),
        "mode": info.get("mode"), "node_id": info.get("node_id"),
        "build_id": info.get("build_id"),
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
