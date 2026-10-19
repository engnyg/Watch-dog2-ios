#!/usr/bin/env python3
"""Audit a macOS game executable before any porting work.

Reports per-architecture: cpu type, UUID, load platform, minimum OS, dylib
dependencies, encryption flag (cryptid), entry kind and __text SHA-256.
Reads only; never modifies the input.

Usage: python3 -I tools/audit.py <Mach-O file> [--json]
"""
import hashlib
import json
import struct
import sys

FAT_MAGIC, FAT_MAGIC_64 = 0xCAFEBABE, 0xCAFEBABF
MH_MAGIC_64 = 0xFEEDFACF
CPU = {0x0100000C: "arm64", 0x01000007: "x86_64", 0x0200000C: "arm64_32"}
PLATFORM = {1: "macOS", 2: "iOS", 3: "tvOS", 4: "watchOS", 6: "macCatalyst", 7: "iOSSimulator"}
LC_SEGMENT_64, LC_UUID, LC_ENCRYPTION_INFO_64 = 0x19, 0x1B, 0x2C
LC_BUILD_VERSION, LC_VERSION_MIN_MACOSX, LC_MAIN, LC_UNIXTHREAD = 0x32, 0x24, 0x80000028, 0x5
LC_DYLIBS = {0xC: "load", 0x80000018: "weak", 0x8000001F: "reexport", 0x1F: "lazy"}


def _ver(v):
    return f"{v >> 16}.{(v >> 8) & 0xff}.{v & 0xff}"


def parse_thin(data, off=0):
    magic, cputype, _sub, ftype, ncmds, _sz, _flags, _r = struct.unpack_from("<IiiIIIII", data, off)
    if magic != MH_MAGIC_64:
        raise ValueError("not a 64-bit little-endian Mach-O")
    info = {"cpu": CPU.get(cputype, hex(cputype)), "filetype": ftype, "uuid": None,
            "platform": None, "minos": None, "dylibs": [], "cryptid": None,
            "entry": None, "text_sha256": None}
    p = off + 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, p)
        if cmd == LC_UUID:
            b = data[p + 8:p + 24].hex()
            info["uuid"] = f"{b[:8]}-{b[8:12]}-{b[12:16]}-{b[16:20]}-{b[20:]}"
        elif cmd == LC_BUILD_VERSION:
            plat, minos = struct.unpack_from("<II", data, p + 8)
            info["platform"], info["minos"] = PLATFORM.get(plat, plat), _ver(minos)
        elif cmd == LC_VERSION_MIN_MACOSX:
            info["platform"], info["minos"] = "macOS", _ver(struct.unpack_from("<I", data, p + 8)[0])
        elif cmd in LC_DYLIBS:
            nameoff = struct.unpack_from("<I", data, p + 8)[0]
            name = data[p + nameoff:p + size].split(b"\0")[0].decode()
            info["dylibs"].append({"kind": LC_DYLIBS[cmd], "path": name})
        elif cmd == LC_ENCRYPTION_INFO_64:
            info["cryptid"] = struct.unpack_from("<I", data, p + 16)[0]
        elif cmd == LC_MAIN:
            info["entry"] = "LC_MAIN"
        elif cmd == LC_UNIXTHREAD:
            info["entry"] = "LC_UNIXTHREAD"
        elif cmd == LC_SEGMENT_64:
            segname = data[p + 8:p + 24].split(b"\0")[0]
            nsects = struct.unpack_from("<I", data, p + 64)[0]
            q = p + 72
            for _s in range(nsects):
                sect = data[q:q + 16].split(b"\0")[0]
                seg = data[q + 16:q + 32].split(b"\0")[0]
                ssize, soff = struct.unpack_from("<QI", data, q + 40)
                if sect == b"__text" and seg == b"__TEXT":
                    info["text_sha256"] = hashlib.sha256(data[off + soff:off + soff + ssize]).hexdigest()
                    info["text_file_offset"] = soff
                q += 80
        p += size
    return info


def audit(path):
    data = open(path, "rb").read()
    magic = struct.unpack_from(">I", data, 0)[0]
    slices = []
    if magic in (FAT_MAGIC, FAT_MAGIC_64):
        n = struct.unpack_from(">I", data, 4)[0]
        for i in range(n):
            if magic == FAT_MAGIC:
                _c, _s, off, _sz, _a = struct.unpack_from(">iiIII", data, 8 + 20 * i)
            else:
                _c, _s, off, _sz, _a = struct.unpack_from(">iiQQI", data, 8 + 32 * i)
            slices.append(parse_thin(data, off))
    else:
        slices.append(parse_thin(data))
    return {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "slices": slices}


def verdict(report):
    """Go/no-go for the 'native ARM64 + UIKit shim' route."""
    arm = [s for s in report["slices"] if s["cpu"] == "arm64"]
    if not arm:
        return ("NO-GO", "no arm64 slice: this route does not apply (x86_64-only needs a CPU "
                         "emulator/JIT, a different project). Do not continue.")
    if any(s["cryptid"] for s in arm):
        return ("NO-GO", "arm64 slice is encrypted (cryptid != 0); decryption is out of scope.")
    return ("GO", "unencrypted arm64 slice present; continue with dependency audit.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rep = audit(sys.argv[1])
    rep["verdict"] = verdict(rep)
    if "--json" in sys.argv:
        print(json.dumps(rep, indent=2))
    else:
        for s in rep["slices"]:
            print(f"[{s['cpu']}] uuid={s['uuid']} platform={s['platform']} minos={s['minos']} "
                  f"cryptid={s['cryptid']} entry={s['entry']}\n  __text sha256={s['text_sha256']}")
            for d in s["dylibs"]:
                print(f"  dep({d['kind']}): {d['path']}")
        print("VERDICT:", *rep["verdict"])
