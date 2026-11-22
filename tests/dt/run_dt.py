"""Decision-table (判定表) runner.

Executes ``dt/cases.json`` against a protocol implementation. By default the
reference implementation is used; ``--impl module.path:Class`` can point to any
Python module exposing the same API (Link, encode_command, decode_notify,
checksum). The real phone implementations are validated through adapters, see
``adapters/README.md``.

Usage:
    python tests/dt/run_dt.py            # run all cases, human readable
    python tests/dt/run_dt.py --json     # machine readable (adapters compare)
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
sys.path.insert(0, str(TESTS / "reference"))

import protocol_ref as ref  # noqa: E402


def _hex(value: str) -> str:
    return value.upper().replace(" ", "")


def _writes_to_pairs(writes) -> list[dict]:
    out = []
    for w in writes:
        if isinstance(w, dict):
            out.append({"cmd": _hex(w["cmd"]), "delayBeforeMs": int(w.get("delayBeforeMs", 0))})
        else:
            out.append({"cmd": _hex(w.hex), "delayBeforeMs": int(w.delay_before_ms)})
    return out


def _apply_given(link, given: dict) -> None:
    if given.get("connected"):
        link.connect()
    if "status" in given:
        st = given["status"]
        link.lock = st.get("lock", link.lock)
        link.mode = st.get("mode", link.mode)
        link.pke = st.get("pke", link.pke)
        link.pass1 = st.get("pass1", link.pass1)
        link.pass2 = st.get("pass2", link.pass2)
        link.status_valid = True
    if given.get("armedAgoMs") is not None:
        now = given.get("_nowMs", 0)
        link.start_armed_at_ms = now - int(given["armedAgoMs"])


def _check_subset(actual: dict, expect: dict) -> list[str]:
    errs = []
    for key, value in expect.items():
        if key not in actual:
            errs.append("missing key %r" % key)
        elif actual[key] != value:
            errs.append("%s: expected %r, got %r" % (key, value, actual[key]))
    return errs


def _state(link) -> dict:
    return {
        "lock": link.lock,
        "mode": link.mode,
        "started": link.started,
        "armed": link.start_armed_at_ms is not None,
        "connected": link.connected,
        "hint": link.hint,
    }


def run_case(case: dict, impl, crypto=ref) -> tuple[bool, str]:
    link = impl.Link(impl.PIN)
    given = dict(case.get("given") or {})
    given["_nowMs"] = case.get("nowMs", 0)
    _apply_given(link, given)

    try:
        kind = case.get("kind", "command")
        if kind == "command":
            return _run_command(case, link, impl, crypto)
        if kind == "notify":
            return _run_notify(case, link, impl, crypto)
        if kind == "sequence":
            return _run_sequence(case, link, impl, crypto)
        return False, "unknown case kind %r" % kind
    except Exception as exc:  # surface implementation bugs as case failures
        return False, "exception: %s: %s" % (type(exc).__name__, exc)


def _run_command(case: dict, link, impl, crypto=ref) -> tuple[bool, str]:
    expect = case.get("expect") or {}
    action = case["action"]
    now = case.get("nowMs", 0)

    try:
        writes = link.command(action, now)
    except (RuntimeError, ValueError) as exc:
        if expect.get("error"):
            return True, "raised as expected (%s)" % exc
        return False, "unexpected error: %s" % exc

    if expect.get("error"):
        return False, "expected an error but got writes %r" % (_writes_to_pairs(writes),)

    if "writes" in expect:
        got = _writes_to_pairs(writes)
        want = [{"cmd": _hex(w["cmd"]), "delayBeforeMs": int(w["delayBeforeMs"])}
                for w in expect["writes"]]
        if got != want:
            return False, "writes mismatch\n  expected %r\n  got      %r" % (want, got)

    errs = []
    if "hint" in expect and link.hint != expect["hint"]:
        errs.append("hint: expected %r, got %r" % (expect["hint"], link.hint))
    if "armedAfter" in expect:
        armed = link.start_armed_at_ms is not None
        if armed != expect["armedAfter"]:
            errs.append("armed: expected %r, got %r" % (expect["armedAfter"], armed))
    return (not errs), "; ".join(errs) or "ok"


def _run_notify(case: dict, link, impl, crypto=ref) -> tuple[bool, str]:
    expect = case.get("expect") or {}
    inp = case.get("input") or {}

    if "rawHex" in inp:
        parsed = link.on_notify(bytes.fromhex(inp["rawHex"]))
    else:
        plain = bytes.fromhex(inp["plain"])
        if len(plain) < 16:
            plain = plain + bytes(16 - len(plain))
        pin = inp.get("wrongPin", case.get("pin", impl.PIN))
        key = crypto.derive_key(b"Lenzedev", pin)
        cipher = crypto.aes128_encrypt_block(plain[:16], key)
        parsed = link.on_notify(cipher)

    if expect.get("parsedNone"):
        if parsed is not None:
            return False, "expected None, got %r" % (parsed,)
        return True, "ignored as expected"

    if "parsedKind" in expect:
        if not parsed or parsed.get("kind") != expect["parsedKind"]:
            return False, "kind: expected %r, got %r" % (expect["parsedKind"], parsed)
    if "parsedKindNot" in expect:
        if parsed and parsed.get("kind") == expect["parsedKindNot"]:
            return False, "decoded as %r with the wrong PIN" % expect["parsedKindNot"]

    errs = []
    if "status" in expect:
        if not parsed or parsed.get("kind") != "status":
            errs.append("no status parsed")
        else:
            errs += _check_subset(parsed, expect["status"])
    if "stateAfter" in expect:
        errs += _check_subset(_state(link), expect["stateAfter"])
    if "started" in expect and link.started != expect["started"]:
        errs.append("started: expected %r, got %r" % (expect["started"], link.started))
    return (not errs), "; ".join(errs) or "ok"


def _run_sequence(case: dict, link, impl, crypto=ref) -> tuple[bool, str]:
    errs = []
    for index, step in enumerate(case.get("steps") or []):
        label = "step %d" % (index + 1)
        expect = step.get("expect") or {}
        if "action" in step:
            try:
                writes = link.command(step["action"], step.get("nowMs", 0))
            except (RuntimeError, ValueError) as exc:
                errs.append("%s: unexpected error %s" % (label, exc))
                continue
            if "writes" in expect:
                got = [w["cmd"] for w in _writes_to_pairs(writes)]
                want = [_hex(x) for x in expect["writes"]]
                if got != want:
                    errs.append("%s writes: expected %r, got %r" % (label, want, got))
        elif "notify" in step:
            plain = bytes.fromhex(step["notify"]["plain"])
            if len(plain) < 16:
                plain += bytes(16 - len(plain))
            cipher = crypto.aes128_encrypt_block(
                plain[:16], crypto.derive_key(b"Lenzedev", impl.PIN))
            link.on_notify(cipher)
        elif step.get("disconnect"):
            link.disconnect()
        elif step.get("connect"):
            link.connect()

        for key, value in expect.items():
            if key == "writes":
                continue
            actual = {"started": link.started, "lock": link.lock, "mode": link.mode,
                      "armed": link.start_armed_at_ms is not None,
                      "connected": link.connected, "hint": link.hint}.get(key)
            if key in ("armed", "connected") and actual is None:
                actual = {"armed": link.start_armed_at_ms is not None,
                          "connected": link.connected}[key]
            if actual != value:
                errs.append("%s %s: expected %r, got %r" % (label, key, value, actual))
    return (not errs), "; ".join(errs) or "ok"


def run_all(impl=ref, crypto=ref, cases_path: Path | None = None) -> list[dict]:
    path = cases_path or (HERE / "cases.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    results = []
    for case in data["cases"]:
        ok, detail = run_case(case, impl, crypto)
        results.append({"id": case["id"], "title": case.get("title", ""),
                        "ok": ok, "detail": detail})
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="decision table runner")
    parser.add_argument("--json", action="store_true", help="machine readable output")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--cases", type=Path, default=None)
    args = parser.parse_args(argv)

    results = run_all(cases_path=args.cases)
    failed = [r for r in results if not r["ok"]]

    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "PASS" if r["ok"] else "FAIL"
            line = "%s %-6s %s" % (mark, r["id"], r["title"])
            if not r["ok"] or args.verbose:
                line += "\n        " + r["detail"]
            print(line)
        print("\n%d/%d decision-table cases passed" % (len(results) - len(failed), len(results)))

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
