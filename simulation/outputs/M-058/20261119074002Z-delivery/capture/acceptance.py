"""M-058 acceptance. Replay five archived RF payloads on isolated local ports."""
import datetime as dt
import hashlib
import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path.cwd()
SOURCE = ROOT / "simulation/results/20261113-H019-gateway-eora-link/lrn1_samples.jsonl"
HERE = pathlib.Path(__file__).resolve().parent
GATEWAY = bytes.fromhex("b827ebfffe32e2c1")
children = []

def unused(kind):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def launch(name, module, *args):
    log = (HERE / (name + ".log")).open("xb")
    try:
        child = subprocess.Popen([sys.executable, "-X", "utf8", "-m", module, *map(str, args)],
                                 stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        children.append(child)
    finally:
        log.close()

def api(port, path, post=False):
    base = "http://127.0.0.1:%d" % port
    req = urllib.request.Request(base + path, data=b"{}" if post else None,
                                 headers={"Origin": base, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.load(resp)

def ready(port, path):
    for i in range(50):
        if any(c.poll() is not None for c in children):
            raise RuntimeError("service exited; see logs")
        try:
            return api(port, path)
        except OSError:
            time.sleep(.2)
    raise RuntimeError("service did not become ready")

def run():
    rows = [json.loads(line) for line in SOURCE.read_text().splitlines()]
    udp = unused(socket.SOCK_DGRAM)
    topo, studio, pc = (unused(socket.SOCK_STREAM) for _ in range(3))
    assert len({topo, studio, pc}) == 3
    launch("receiver", "tools.mid_baseline.gateway_probe.topology_server", "--port", topo, "--udp-port", udp)
    ready(topo, "/api/v1/lora/topology")
    launch("studio", "tools.mobile_gateway.studio", "--port", studio, "--pc-port", pc, "--topology-port", topo,
           "--output", HERE/"studio", "--replay-db", HERE/"recording.sqlite3", "--stop-file", HERE/"stop")
    ready(studio, "/api/v1/replay/sessions")
    rid = api(studio, "/api/v1/replay/start", True)["id"]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        def transmit(row=None):
            payload = b""
            mtype = 2 if row is None else 0
            if row is not None:
                p = {k: v for k, v in row.items() if k not in ("hex","b64","host_t")}
                p["data"] = row["b64"]
                payload = json.dumps({"rxpk": [p]}).encode()
            sock.sendto(bytes([2, 0x12, 0x34, mtype])+GATEWAY+payload, ("127.0.0.1", udp))
            ack = sock.recv(16)
            assert ack == bytes([2, 0x12, 0x34, 4 if row is None else 1]), ack
        for row in rows[:-1]:
            transmit(row)
            time.sleep(1.4)
        for _ in range(9):
            transmit()
            time.sleep(4)
        transmit(rows[-1])
        time.sleep(4)
    assert api(studio, "/api/v1/replay/stop", True)["id"] == rid
    result = api(studio, "/api/v1/replay/session?id="+rid)
    assert result["id"] == rid
    frames = result["frames"]
    assert len(frames) > 3
    seen = [f for f in frames if f["topology"].get("reports")]
    assert seen
    stale = [f for f in seen if f["topology"]["receiver"].get("gateway_observed") and
             any(r["pc_receive_age_ms"] >= 30000 for r in f["topology"]["reports"])]
    assert stale, "no recorded age crossing while gateway remained observed"
    last = seen[-1]["topology"]
    assert last["receiver"]["lrn1_frames"] == len(rows)
    mac = bytes.fromhex(rows[-1]["hex"])[8:14].hex(":")
    restored = next(r for r in last["reports"] if r["report"]["observer_id"] == mac)
    assert restored["pc_receive_age_ms"] < 7500
    assert restored["lora"]["rssi_dbm"] == rows[-1]["rssi"] and restored["lora"]["snr_db"] == rows[-1]["lsnr"]
    assert any(r["report"]["observer_id"]==mac and r["pc_receive_age_ms"]>=30000
               for f in stale for r in f["topology"]["reports"])
    summary = dict(status="pass", evidence="archived RF payloads, controlled local UDP timing; not a new physical movement",
                   source=str(SOURCE.relative_to(ROOT)), sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                   reports_received=len(rows),sample_count=len(frames),sampling_span_ms=frames[-1]["t_ms"]-frames[0]["t_ms"],
                   first_stale_ms=stale[0]["t_ms"], restored_observer=mac, final_lora=restored["lora"],
                   final_age_ms=restored["pc_receive_age_ms"], endpoint=rid)
    (HERE/"ACCEPTANCE.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary))

if __name__ == "__main__":
    try:
        run()
    finally:
        if len(children)>1:
            (HERE/"stop").touch()
            try: children[-1].wait(timeout=5)
            except subprocess.TimeoutExpired: pass
        for c in reversed(children):
            if c.poll() is None:
                c.terminate()
                c.wait(timeout=5)
