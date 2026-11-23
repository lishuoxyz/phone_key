"""Run the whole phone_key test suite.

    python tests/run_all.py                 # reference implementation
    python tests/run_all.py --adapter "node tests/adapters/js/run.mjs"

Steps:
  1. reference self-check (AES + protocol constants from real captures)
  2. golden vectors: checked-in files must match what the generator produces
  3. vector conformance: encode / checksum / decode
  4. decision table (dt/cases.json)
  5. optional: run an implementation adapter and require all case ids to pass
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "reference"))
sys.path.insert(0, str(HERE / "dt"))

import gen_vectors  # noqa: E402
import protocol_ref as ref  # noqa: E402
import run_dt  # noqa: E402

VECTORS = HERE / "vectors"


def step(title: str) -> None:
    print("\n== %s ==" % title)


def check_vectors_drift() -> list[str]:
    """Regenerate into a temp dir and compare with the checked-in vectors."""
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        original = gen_vectors.VECTORS_DIR
        gen_vectors.VECTORS_DIR = tmp_path
        try:
            gen_vectors.main()
        finally:
            gen_vectors.VECTORS_DIR = original
        for name in ("golden.json", "golden.mjs", "GoldenVectors.kt"):
            a = (VECTORS / name).read_text(encoding="utf-8")
            b = (tmp_path / name).read_text(encoding="utf-8")
            if a != b:
                errors.append("%s is stale: run tests/reference/gen_vectors.py" % name)
    return errors


def check_vector_conformance() -> list[str]:
    data = json.loads((VECTORS / "golden.json").read_text(encoding="utf-8"))
    errors = []
    for v in data["vectors"]:
        kind = v["kind"]
        if kind == "encode":
            got = ref.encode_command(bytes.fromhex(v["cmd"]), v["pin"]).hex().upper()
            if got != v["expect"]:
                errors.append("%s: expected %s got %s" % (v["id"], v["expect"], got))
        elif kind == "checksum":
            got = ref.checksum(bytes.fromhex(v["cmd"]))
            if got != v["expect"]:
                errors.append("%s: expected %d got %d" % (v["id"], v["expect"], got))
        elif kind == "decode":
            parsed = ref.decode_notify(bytes.fromhex(v["cipher"]), v["pin"])
            if "expect" not in v:
                continue
            if not parsed:
                errors.append("%s: no decode" % v["id"])
                continue
            for key, value in v["expect"].items():
                if parsed.get(key) != value:
                    errors.append("%s.%s: expected %r got %r"
                                  % (v["id"], key, value, parsed.get(key)))
    # AES round trip over random payloads (deterministic seed, no third party libs)
    import random
    rng = random.Random(1234)
    key = ref.derive_key(b"Lenzedev", ref.PIN)
    for _ in range(50):
        block = bytes(rng.randrange(256) for _ in range(16))
        if ref.aes128_decrypt_block(ref.aes128_encrypt_block(block, key), key) != block:
            errors.append("AES round trip failed for %s" % block.hex())
            break
    return errors


def _with_adapter(command: str, fn):
    sys.path.insert(0, str(HERE / "adapters"))
    from remote import RemoteAdapter  # noqa: E402

    adapter = RemoteAdapter(command)
    try:
        return fn(adapter)
    finally:
        adapter.close()


def _adapter_vector_errors(adapter) -> list[str]:
    data = json.loads((VECTORS / "golden.json").read_text(encoding="utf-8"))
    errors = []
    for v in data["vectors"]:
        kind = v["kind"]
        try:
            if kind == "encode":
                got = adapter.encode(v["cmd"], v["pin"])
                if got != v["expect"]:
                    errors.append("%s: expected %s got %s" % (v["id"], v["expect"], got))
            elif kind == "checksum":
                got = adapter.checksum(v["cmd"])
                if got != v["expect"]:
                    errors.append("%s: expected %d got %d" % (v["id"], v["expect"], got))
            elif kind == "decode":
                parsed = adapter.decode(v["cipher"], v["pin"])
                for key, value in (v.get("expect") or {}).items():
                    if not parsed or parsed.get(key) != value:
                        errors.append("%s.%s: expected %r got %r"
                                      % (v["id"], key, value, (parsed or {}).get(key)))
        except Exception as exc:  # noqa: BLE001
            errors.append("%s: adapter error %s" % (v["id"], exc))
    return errors


def check_adapter(command: str) -> list[str]:
    """Run the golden vectors and the decision table against an adapter."""
    try:
        def run(adapter):
            errors = _adapter_vector_errors(adapter)
            results = run_dt.run_all(impl=adapter, crypto=ref)
            errors += ["%s: %s" % (r["id"], r["detail"]) for r in results if not r["ok"]]
            if not results:
                errors.append("adapter produced no results")
            return errors
        return _with_adapter(command, run)
    except FileNotFoundError as exc:
        return ["adapter not found: %s" % exc]


def _adapter_results(command: str) -> list[dict]:
    """Decision table only (used by the adapter-harness self-test)."""
    try:
        def run(adapter):
            return run_dt.run_all(impl=adapter, crypto=ref)
        return _with_adapter(command, run)
    except Exception as exc:  # noqa: BLE001 - the harness reports, never crashes
        return [{"id": "adapter", "title": "adapter failed", "ok": False,
                 "detail": str(exc)}]


def check_adapter_harness() -> list[str]:
    """The adapter mechanism itself must be covered: a correct adapter passes,
    a mutant with a missing release frame must fail."""
    py = sys.executable
    errors = []
    ref_cmd = '"%s" "%s"' % (py, HERE / "adapters" / "py" / "rpc_ref.py")
    results = _adapter_results(ref_cmd)
    errors += ["reference adapter %s: %s" % (r["id"], r["detail"])
               for r in results if not r["ok"]]
    if not results:
        errors.append("reference adapter produced no results")

    mut_cmd = '"%s" "%s"' % (py, HERE / "adapters" / "py" / "rpc_mutant.py")
    mutant = _adapter_results(mut_cmd)
    if all(r["ok"] for r in mutant):
        errors.append("mutant adapter was not detected (missing release frame)")
    return errors


def check_js_units(node: str) -> list[str]:
    """Run the pure JS unit tests (GATT selection / write queue)."""
    argv = [node, "--test", str(HERE / "unit")]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return ["node not found: %s" % node]
    if proc.returncode != 0:
        tail = (proc.stdout or "")[-1500:]
        return ["js unit tests failed:\n" + tail]
    return []


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="phone_key test suite")
    parser.add_argument("--adapter", default=None,
                        help='command that runs an implementation, e.g. "node tests/adapters/js/run.mjs"')
    parser.add_argument("--node", default=None,
                        help="path to node.exe; when given, also run tests/unit (GATT helpers)")
    args = parser.parse_args(argv)

    failures: list[str] = []

    step("reference self-check")
    ref.self_check()
    print("ok: AES-128-ECB + known ciphertexts")

    step("golden vectors")
    failures += check_vectors_drift()
    failures += check_vector_conformance()
    print("ok: %d vectors" % len(json.loads((VECTORS / "golden.json").read_text())["vectors"]))

    step("decision table")
    dt_results = run_dt.run_all()
    failed = [r for r in dt_results if not r["ok"]]
    for r in failed:
        print("FAIL %s: %s" % (r["id"], r["detail"]))
    print("%d/%d passed" % (len(dt_results) - len(failed), len(dt_results)))
    failures += ["%s: %s" % (r["id"], r["detail"]) for r in failed]

    step("adapter harness (self-test)")
    failures += check_adapter_harness()
    print("ok: reference adapter passes, mutant adapter is caught")

    if args.node:
        step("js unit tests")
        failures += check_js_units(args.node)
        print("ok: GATT selection / write queue")

    if args.adapter:
        step("adapter: %s" % args.adapter)
        failures += check_adapter(args.adapter)
        print("adapter checked")

    print()
    if failures:
        print("FAILED (%d)" % len(failures))
        for item in failures[:40]:
            print("  - " + item)
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
