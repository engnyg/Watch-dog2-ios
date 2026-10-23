#!/usr/bin/env python3
"""Print PE facts about a wow64.dll and whether it still contains the NtRaiseHardError stub.

Usage: wow64-diag.py <dll> [--expect-patched]
Exit 1 with --expect-patched when the stub marker is still present or the PE is not ARM64.
"""
import struct
import sys

STUB_MARKER = b"%lu %lx %p %u %p: stub"
FUNC_NAME = b"wow64_NtRaiseHardError"

path = sys.argv[1]
expect_patched = "--expect-patched" in sys.argv
d = open(path, "rb").read()

if d[:2] != b"MZ":
    sys.exit(f"{path}: not a PE file")
pe = struct.unpack_from("<I", d, 0x3C)[0]
machine, nsec = struct.unpack_from("<HH", d, pe + 4)
opt = pe + 24
exp_rva, exp_size = struct.unpack_from("<II", d, opt + 112)
print(f"{path}: size={len(d)} machine=0x{machine:04x} sections={nsec} export_dir=(rva=0x{exp_rva:x}, size=0x{exp_size:x})")

sec_off = opt + struct.unpack_from("<H", d, pe + 20)[0]
for i in range(nsec):
    name = d[sec_off + i * 40:sec_off + i * 40 + 8].rstrip(b"\0").decode("ascii", "replace")
    vsz, va, rsz, roff = struct.unpack_from("<IIII", d, sec_off + i * 40 + 8)
    print(f"  section {name:8} va=0x{va:x} vsize=0x{vsz:x} raw=0x{roff:x} rawsize=0x{rsz:x}")

has_stub = STUB_MARKER in d
has_name = FUNC_NAME in d
print(f"stub-format-string present: {has_stub}; function-name string present: {has_name}")

if expect_patched:
    if machine != 0xAA64:
        sys.exit("rebuilt wow64.dll is not ARM64")
    if has_stub:
        sys.exit("rebuilt wow64.dll still contains the NtRaiseHardError stub")
    print("OK: rebuilt wow64.dll is ARM64 and the stub string is gone")
