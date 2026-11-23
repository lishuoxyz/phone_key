"""Bump the PWA version in ``pwa/version.json``.

Usage:
    python tools/bump_version.py            # 0.1.1 -> 0.1.2 (patch)
    python tools/bump_version.py --minor    # 0.1.1 -> 0.2.0
    python tools/bump_version.py --major    # 0.1.1 -> 1.0.0
    python tools/bump_version.py --print    # print the current version

Convention (enforced by .github/workflows/pages.yml):
every commit that changes ``pwa/**`` must bump this version, and the commit
message starts with ``pwa vX.Y.Z: ...``.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "pwa" / "version.json"


def read() -> dict:
    with open(VERSION_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def write(data: dict) -> None:
    with open(VERSION_FILE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def bump(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return "%d.%d.%d" % (major, minor, patch)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="bump phone_key PWA version")
    parser.add_argument("--major", action="store_true")
    parser.add_argument("--minor", action="store_true")
    parser.add_argument("--print", dest="show", action="store_true")
    args = parser.parse_args(argv)

    data = read()
    if args.show:
        print(data["version"])
        return 0

    part = "major" if args.major else "minor" if args.minor else "patch"
    data["version"] = bump(data["version"], part)
    data["updated"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    write(data)
    print(data["version"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
