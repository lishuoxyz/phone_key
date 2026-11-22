"""Reference JSON-lines adapter (used to test the adapter mechanism itself).

    python tests/adapters/py/rpc_ref.py

It wraps ``tests/reference/protocol_ref.py``: if the harness cannot drive this
adapter correctly, the harness is broken (not the implementation).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS / "reference"))

import protocol_ref as ref  # noqa: E402


def state_out(link) -> dict:
    return {
        "connected": link.connected,
        "lock": link.lock,
        "mode": link.mode,
        "pke": link.pke,
        "pass1": link.pass1,
        "pass2": link.pass2,
        "statusValid": link.status_valid,
        "armedAtMs": link.start_armed_at_ms,
        "hint": link.hint,
    }


def apply(link, state: dict) -> None:
    state = state or {}
    link.connected = bool(state.get("connected", False))
    link.lock = int(state.get("lock", 1))
    link.mode = int(state.get("mode", 1))
    link.pke = int(state.get("pke", 0))
    link.pass1 = int(state.get("pass1", 0))
    link.pass2 = int(state.get("pass2", 0))
    link.status_valid = bool(state.get("statusValid", False))
    armed = state.get("armedAtMs")
    link.start_armed_at_ms = None if armed is None else int(armed)
    link.hint = state.get("hint", "")


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
                reply = {"ok": True, "writes": [{"cmd": w.hex, "delayBeforeMs": w.delay_before_ms} for w in writes]}
            elif op == "notify":
                parsed = link.on_notify(bytes.fromhex(req["cipher"]))
                reply = {"ok": True, "parsed": parsed}
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
            reply["state"] = state_out(link)
        except Exception as exc:  # noqa: BLE001 - adapter must report, not crash
            reply = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
                     "state": state_out(link)}
        print(json.dumps(reply), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
