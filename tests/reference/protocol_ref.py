"""Reference implementation of the bdb-PKE BLE protocol.

Pure Python (no third-party packages) so the test suite runs anywhere:

* AES-128-ECB (FIPS-197, verified against the standard vector in the tests);
* frame encoding / decoding (16 bytes, checksum, zero padding);
* status / event / heartbeat parsing;
* command sequencing (press -> 150 ms -> release, status query rules);
* the client-side start/stop state machine ("press twice to start, unlock to stop").

Every phone implementation (PWA, Android, hybrid) is expected to match this
behaviour byte for byte; ``tests/dt`` and ``tests/vectors`` are generated from
it, and the per-implementation adapters are compared against it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Default accessory PIN (also used by the reference model and the vectors).
PIN = 123789

# --------------------------------------------------------------------------- AES

RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _gmul(a: int, b: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _build_sbox() -> Tuple[List[int], List[int]]:
    inv = [0] * 256
    for i in range(1, 256):
        for j in range(1, 256):
            if _gmul(i, j) == 1:
                inv[i] = j
                break
    sbox = [0] * 256
    for i in range(256):
        x = inv[i]
        s = x
        for _ in range(4):
            x = ((x << 1) | (x >> 7)) & 0xFF
            s ^= x
        sbox[i] = s ^ 0x63
    inv_sbox = [0] * 256
    for i, v in enumerate(sbox):
        inv_sbox[v] = i
    return sbox, inv_sbox


SBOX, INV_SBOX = _build_sbox()


def _expand_key(key: bytes) -> bytes:
    assert len(key) == 16, "AES-128 key must be 16 bytes"
    w = [list(key[4 * i:4 * i + 4]) for i in range(4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [SBOX[b] for b in t]
            t[0] ^= RCON[i // 4 - 1]
        w.append([w[i - 4][j] ^ t[j] for j in range(4)])
    return b"".join(bytes(x) for x in w)


def _add_round_key(s: List[int], rk: bytes, rnd: int) -> None:
    for i in range(16):
        s[i] ^= rk[rnd * 16 + i]


def _sub_bytes(s: List[int]) -> None:
    for i in range(16):
        s[i] = SBOX[s[i]]


def _inv_sub_bytes(s: List[int]) -> None:
    for i in range(16):
        s[i] = INV_SBOX[s[i]]


def _shift_rows(s: List[int]) -> None:
    t = s[:]
    for r in range(1, 4):
        for c in range(4):
            s[4 * c + r] = t[4 * ((c + r) % 4) + r]


def _inv_shift_rows(s: List[int]) -> None:
    t = s[:]
    for r in range(1, 4):
        for c in range(4):
            s[4 * c + r] = t[4 * ((c - r) % 4) + r]


def _mix_columns(s: List[int]) -> None:
    for c in range(4):
        a = [s[4 * c + i] for i in range(4)]
        s[4 * c + 0] = _gmul(a[0], 2) ^ _gmul(a[1], 3) ^ a[2] ^ a[3]
        s[4 * c + 1] = a[0] ^ _gmul(a[1], 2) ^ _gmul(a[2], 3) ^ a[3]
        s[4 * c + 2] = a[0] ^ a[1] ^ _gmul(a[2], 2) ^ _gmul(a[3], 3)
        s[4 * c + 3] = _gmul(a[0], 3) ^ a[1] ^ a[2] ^ _gmul(a[3], 2)


def _inv_mix_columns(s: List[int]) -> None:
    for c in range(4):
        a = [s[4 * c + i] for i in range(4)]
        s[4 * c + 0] = _gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9)
        s[4 * c + 1] = _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13)
        s[4 * c + 2] = _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11)
        s[4 * c + 3] = _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)


def aes128_encrypt_block(block: bytes, key: bytes) -> bytes:
    rk = _expand_key(key)
    s = list(block)
    _add_round_key(s, rk, 0)
    for rnd in range(1, 10):
        _sub_bytes(s)
        _shift_rows(s)
        _mix_columns(s)
        _add_round_key(s, rk, rnd)
    _sub_bytes(s)
    _shift_rows(s)
    _add_round_key(s, rk, 10)
    return bytes(s)


def aes128_decrypt_block(block: bytes, key: bytes) -> bytes:
    rk = _expand_key(key)
    s = list(block)
    _add_round_key(s, rk, 10)
    for rnd in range(9, 0, -1):
        _inv_shift_rows(s)
        _inv_sub_bytes(s)
        _add_round_key(s, rk, rnd)
        _inv_mix_columns(s)
    _inv_shift_rows(s)
    _inv_sub_bytes(s)
    _add_round_key(s, rk, 0)
    return bytes(s)


# ----------------------------------------------------------------------- protocol

def derive_key(prefix: bytes, pin: int) -> bytes:
    """``Lenzeapp``/``Lenzedev`` + 4-byte big-endian PIN + 4 zero bytes."""
    return prefix + pin.to_bytes(4, "big") + b"\x00\x00\x00\x00"


def checksum(cmd: bytes) -> int:
    return sum(cmd[2:]) & 0xFF if len(cmd) > 2 else 0


def build_plain(cmd: bytes) -> bytes:
    if not 1 <= len(cmd) <= 15:
        raise ValueError("command must be 1..15 bytes")
    plain = cmd + bytes([checksum(cmd)])
    return plain + bytes(16 - len(plain))


def encode_command(cmd: bytes, pin: int) -> bytes:
    return aes128_encrypt_block(build_plain(cmd), derive_key(b"Lenzeapp", pin))


def decode_notify(cipher: bytes, pin: int) -> Optional[dict]:
    if len(cipher) != 16:
        return None
    plain = aes128_decrypt_block(cipher, derive_key(b"Lenzedev", pin))
    op = plain[0]
    if op == 0xA6:
        return {
            "kind": "status",
            "lock": plain[2],
            "mode": plain[3],
            "pke": plain[5],
            "pass1": plain[8],
            "pass2": max(0, plain[9] - 1),
            "plain": plain.hex().upper(),
        }
    if op == 0xA5:
        return {
            "kind": "event",
            "cmd": plain[2],
            "lock": plain[3],
            "plain": plain.hex().upper(),
        }
    if op == 0xA9:
        return {"kind": "heartbeat", "counter": plain[2], "plain": plain.hex().upper()}
    return {"kind": "unknown", "op": op, "plain": plain.hex().upper()}


COMMANDS: Dict[str, Tuple[str, Optional[str]]] = {
    "lock": ("A50102", "A50112"),
    "unlock": ("A50101", "A50111"),
    "horn": ("A50104", "A50114"),
    "mute": ("A50103", "A50113"),
    "start": ("A50106", "A50116"),
    "status": ("A600", None),
}

RULE_RELEASE_DELAY_MS = 150
RULE_QUERY_DELAY_MS = 600
RULE_ARM_WINDOW_MS = 5000
# "status" is already a query; "start" must not be followed by one (it would
# clear the device's "waiting for the second press" state).
NO_QUERY_AFTER = {"start", "status"}


def hex_to_bytes(value: str) -> bytes:
    return bytes.fromhex(value)


def bytes_to_hex(value: bytes) -> str:
    return value.hex().upper()


@dataclass
class Write:
    """One GATT write the client would perform."""
    hex: str
    delay_before_ms: int = 0

    def to_dict(self) -> dict:
        return {"hex": self.hex, "delayBeforeMs": self.delay_before_ms}


@dataclass
class Link:
    """Client-side model: command sequencing + state derived from notifications."""
    pin: int = 123789
    connected: bool = False
    lock: int = 1          # 1 = unlocked, 2 = locked
    mode: int = 1          # 1 = not started, 2 = started (engine on)
    pke: int = 0
    pass1: int = 0
    pass2: int = 0
    status_valid: bool = False
    start_armed_at_ms: Optional[int] = None
    hint: str = ""

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> None:
        self.connected = True
        self.start_armed_at_ms = None

    def disconnect(self) -> None:
        self.connected = False
        self.start_armed_at_ms = None
        self.status_valid = False

    # -- encoding / notify -------------------------------------------------
    def encode(self, action: str) -> bytes:
        press_hex, _ = COMMANDS[action]
        return encode_command(hex_to_bytes(press_hex), self.pin)

    def on_notify(self, cipher: bytes) -> Optional[dict]:
        parsed = decode_notify(cipher, self.pin)
        if not parsed:
            return None
        if parsed["kind"] == "status":
            self.lock = parsed["lock"]
            self.mode = parsed["mode"]
            self.pke = parsed["pke"]
            self.pass1 = parsed["pass1"]
            self.pass2 = parsed["pass2"]
            self.status_valid = True
        elif parsed["kind"] == "event":
            self.lock = parsed["lock"]
        return parsed

    @property
    def started(self) -> bool:
        return self.status_valid and self.mode == 2

    # -- command sequencing ------------------------------------------------
    def command(self, action: str, now_ms: int = 0) -> List[Write]:
        """Return the writes the client should send for ``action``.

        Mirrors the real device behaviour:
        * press then release 150 ms later for every action with a release;
        * start does NOT follow with a status query;
        * start twice within the arm window is the only thing that starts;
        * unlock stops a running engine, but only on the peripheral side.
        """
        if not self.connected:
            raise RuntimeError("not connected")
        if action not in COMMANDS:
            raise ValueError("unknown action %r" % action)

        press_hex, release_hex = COMMANDS[action]
        writes: List[Write] = [Write(press_hex, 0)]
        if release_hex:
            writes.append(Write(release_hex, RULE_RELEASE_DELAY_MS))
        if action not in NO_QUERY_AFTER:
            writes.append(Write("A600", RULE_QUERY_DELAY_MS))

        if action == "start":
            if self.started:
                self.hint = "already running"
            elif (self.start_armed_at_ms is not None and
                  now_ms - self.start_armed_at_ms <= RULE_ARM_WINDOW_MS):
                self.hint = "starting"
                self.start_armed_at_ms = None
            else:
                self.hint = "press again to start"
                self.start_armed_at_ms = now_ms
        return writes

    def hint_after(self, action: str, now_ms: int = 0) -> str:
        self.command(action, now_ms)
        return self.hint


def load_spec(tests_dir: Path) -> dict:
    with open(tests_dir / "spec" / "protocol.json", encoding="utf-8") as fh:
        return json.load(fh)


def self_check() -> None:
    """Critical constants must match the real device captures."""
    key = derive_key(b"Lenzeapp", 123789)
    assert key.hex().upper() == "4C656E7A656170700001E38D00000000", key.hex()
    assert encode_command(b"\xA5\x01\x06", 123789).hex().upper() == \
        "3DC21FE3D2882F3D67B60A45E196969F"
    assert encode_command(b"\xA5\x01\x16", 123789).hex().upper() == \
        "A38D419301B9328C2E7F59952A7C2F8C"
    assert encode_command(b"\xA6\x00", 123789).hex().upper() == \
        "8717AEFDD5B58595B75758C24760A551"
    # FIPS-197 appendix C.1
    assert aes128_encrypt_block(
        bytes.fromhex("00112233445566778899aabbccddeeff"),
        bytes.fromhex("000102030405060708090a0b0c0d0e0f"),
    ).hex() == "69c4e0d86a7b0430d8cdb78070b4c55a"


if __name__ == "__main__":
    self_check()
    print("protocol reference self-check OK")
