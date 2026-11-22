"""Broken adapter used to prove the harness catches implementation bugs.

Bug injected: "start" only sends the press frame (no release), which the real
device treats as a held button and never starts. The suite must fail on it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS / "reference"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import protocol_ref as ref  # noqa: E402
from rpc_ref import apply, state_out  # noqa: E402


def main() -> int:
    link = ref.Link(ref.PIN)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("op") == "close":
                return 0
            apply(link, req.get("state"))
            op = req.get("op")
            if op == "connect":
                link.connect()
                reply = {"ok": True}
            elif op == "disconnect":
                link.disconnect()
                reply = {"ok": True}
            elif op == "command":
                writes = link.command(req["action"], req.get("nowMs", 0))
                if req["action"] == "start":
                    writes = [w for w in writes if w.hex != "A50116"]   # bug
                reply = {"ok": True,
                         "writes": [{"cmd": w.hex, "delayBeforeMs": w.delay_before_ms}
                                    for w in writes]}
            elif op == "notify":
                reply = {"ok": True, "parsed": link.on_notify(bytes.fromhex(req["cipher"]))}
            elif op == "encode":
                reply = {"ok": True, "hex": ref.encode_command(
                    bytes.fromhex(req["cmd"]), int(req.get("pin", ref.PIN))).hex().upper()}
            elif op == "checksum":
                reply = {"ok": True, "value": ref.checksum(bytes.fromhex(req["cmd"]))}
            elif op == "decode":
                reply = {"ok": True, "parsed": ref.decode_notify(
                    bytes.fromhex(req["cipher"]), int(req.get("pin", ref.PIN)))}
            else:
                reply = {"ok": False, "error": "unknown op"}
        except Exception as exc:  # noqa: BLE001 - adapter reports, must not die
            reply = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
        reply["state"] = state_out(link)
        print(json.dumps(reply), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
