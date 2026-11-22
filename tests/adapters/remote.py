"""Remote adapter client.

Adapters (JS for PWA/hybrid, Kotlin for the Android app) implement the same
``Link`` behaviour as the Python reference and expose it over a tiny JSON-lines
RPC on stdin/stdout. Keeping the *case evaluation* in Python means every
implementation is judged by exactly the same logic.

Request/response (one JSON object per line, UTF-8):

  {"op":"connect","state":{...}}                  -> {"ok":true,"state":{...}}
  {"op":"disconnect","state":{...}}               -> {"ok":true,"state":{...}}
  {"op":"command","action":"lock","nowMs":0,"state":{...}}
        -> {"ok":true,"writes":[{"cmd":"A50102","delayBeforeMs":0}],"state":{...}}
  {"op":"notify","cipher":"HEX","state":{...}}    -> {"ok":true,"parsed":{...}|null,"state":{...}}

State object:

  {"connected":bool,"lock":1|2,"mode":1|2,"pke":0|1|2,"pass1":int,"pass2":int,
   "statusValid":bool,"armedAtMs":int|null,"hint":str}

Failures: {"ok":false,"error":"..."} (e.g. command while disconnected).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Optional


def split_command(command: str) -> list[str]:
    """Split an adapter command line, keeping Windows backslashes intact."""
    if os.name == "nt":
        parts = shlex.split(command, posix=False)
        return [p.strip('"') for p in parts]
    return shlex.split(command)


class AdapterError(RuntimeError):
    pass


class RemoteLink:
    def __init__(self, proc: subprocess.Popen):
        self._proc = proc
        self.pin = 123789
        self.connected = False
        self.lock = 1
        self.mode = 1
        self.pke = 0
        self.pass1 = 0
        self.pass2 = 0
        self.status_valid = False
        self.start_armed_at_ms: Optional[int] = None
        self.hint = ""

    # -- state marshalling -------------------------------------------------
    def _state(self) -> dict:
        return {
            "connected": self.connected,
            "lock": self.lock,
            "mode": self.mode,
            "pke": self.pke,
            "pass1": self.pass1,
            "pass2": self.pass2,
            "statusValid": self.status_valid,
            "armedAtMs": self.start_armed_at_ms,
            "hint": self.hint,
        }

    def _apply_state(self, state: dict) -> None:
        self.connected = bool(state.get("connected", self.connected))
        self.lock = int(state.get("lock", self.lock))
        self.mode = int(state.get("mode", self.mode))
        self.pke = int(state.get("pke", self.pke))
        self.pass1 = int(state.get("pass1", self.pass1))
        self.pass2 = int(state.get("pass2", self.pass2))
        self.status_valid = bool(state.get("statusValid", self.status_valid))
        armed = state.get("armedAtMs")
        self.start_armed_at_ms = None if armed is None else int(armed)
        self.hint = state.get("hint", self.hint)

    def _call(self, request: dict) -> dict:
        request["state"] = self._state()
        line = json.dumps(request, ensure_ascii=False)
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
            reply = self._proc.stdout.readline()
        except (BrokenPipeError, OSError) as exc:
            raise AdapterError("adapter pipe broken (exit=%s): %s"
                               % (self._proc.poll(), exc))
        if not reply:
            raise AdapterError("adapter closed the connection")
        data = json.loads(reply)
        if not data.get("ok"):
            raise AdapterError(data.get("error", "adapter error"))
        self._apply_state(data.get("state") or {})
        return data

    # -- reference Link API ------------------------------------------------
    def connect(self) -> None:
        self._call({"op": "connect"})

    def disconnect(self) -> None:
        self._call({"op": "disconnect"})

    def command(self, action: str, now_ms: int = 0) -> list:
        data = self._call({"op": "command", "action": action, "nowMs": now_ms})
        return data.get("writes") or []

    def on_notify(self, cipher: bytes):
        data = self._call({"op": "notify", "cipher": cipher.hex().upper()})
        return data.get("parsed")

    @property
    def started(self) -> bool:
        return self.status_valid and self.mode == 2

    def close(self) -> None:
        try:
            self._proc.stdin.write(json.dumps({"op": "close", "state": {}}) + "\n")
            self._proc.stdin.flush()
        except Exception:
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:
            pass


class RemoteAdapter:
    """Mimics the ``protocol_ref`` module surface for run_dt.py."""

    PIN = 123789

    def __init__(self, command: str):
        argv = split_command(command)
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.Link = self._make_link

    def _make_link(self, pin: int) -> RemoteLink:
        link = RemoteLink(self._proc)
        link.pin = pin
        return link

    def _rpc(self, request: dict) -> dict:
        line = json.dumps(request, ensure_ascii=False)
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()
        reply = self._proc.stdout.readline()
        if not reply:
            raise AdapterError("adapter closed the connection")
        data = json.loads(reply)
        if not data.get("ok"):
            raise AdapterError(data.get("error", "adapter error"))
        return data

    def encode(self, cmd_hex: str, pin: int) -> str:
        return self._rpc({"op": "encode", "cmd": cmd_hex, "pin": pin})["hex"]

    def checksum(self, cmd_hex: str) -> int:
        return int(self._rpc({"op": "checksum", "cmd": cmd_hex})["value"])

    def decode(self, cipher_hex: str, pin: int):
        return self._rpc({"op": "decode", "cipher": cipher_hex, "pin": pin})["parsed"]

    def close(self) -> None:
        try:
            self._proc.terminate()
        except Exception:
            pass

    def stderr_tail(self) -> str:
        try:
            if self._proc.poll() is None:
                return ""            # still running: do not block on read()
            return (self._proc.stderr.read() or "")[-800:]
        except Exception:
            return ""
