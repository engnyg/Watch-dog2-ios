#!/usr/bin/env python3
"""Version-locked instruction patcher.

Writes only when the binary UUID matches and every target still holds its
original bytes. Patches are listed in patches.json (empty until a real
allocation failure has been traced to a specific reservation; never guess).

patches.json: {"uuid": "...", "patches": [{"offset": "0x..", "old": "d2c00209",
               "new": "d2c00049", "why": "..."}]}

Usage: tools/patch_memory_budget.py <in> <out> patches.json [--check]
"""
import json
import shutil
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from audit import audit  # noqa: E402


def main(src, dst, spec_path, check_only=False):
    spec = json.load(open(spec_path))
    uuids = {s["uuid"] for s in audit(src)["slices"]}
    if spec["uuid"] not in uuids:
        sys.exit(f"UUID mismatch: binary {sorted(uuids)} vs patch set {spec['uuid']}; re-audit required")
    data = bytearray(open(src, "rb").read())
    for p in spec["patches"]:
        off, old, new = int(p["offset"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])
        if len(old) != len(new):
            sys.exit(f"{p['offset']}: length mismatch")
        if bytes(data[off:off + len(old)]) != old:
            sys.exit(f"{p['offset']}: original bytes differ; refusing to patch")
        data[off:off + len(new)] = new
    if check_only:
        print(f"OK: {len(spec['patches'])} patches apply cleanly")
        return
    shutil.copyfile(src, dst)  # source is never modified
    open(dst, "wb").write(data)
    print(f"wrote {dst} with {len(spec['patches'])} patches")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3], "--check" in sys.argv)
