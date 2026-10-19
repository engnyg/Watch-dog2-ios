#!/usr/bin/env python3
"""Write a SHA-256 manifest of a game resource tree (streamed, 4 MiB chunks).

Usage: tools/resource_manifest.py <game root> <manifest.json>
Also flags names that differ only by case, and case-sensitive path hazards
(e.g. 'Mac' vs 'mac'), which need a symlink on the device.
"""
import hashlib
import json
import os
import sys


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(4 << 20):
            h.update(chunk)
    return h.hexdigest()


def main(root, out):
    files, total = [], 0
    for d, _dirs, names in os.walk(root):
        for n in sorted(names):
            p = os.path.join(d, n)
            if os.path.islink(p):
                continue
            size = os.path.getsize(p)
            files.append({"path": os.path.relpath(p, root), "size": size, "sha256": sha256_file(p)})
            total += size
    json.dump({"root": os.path.basename(root), "count": len(files), "bytes": total, "files": files},
              open(out, "w"), indent=1)
    print(f"{len(files)} files, {total} bytes")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
