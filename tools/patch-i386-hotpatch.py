#!/usr/bin/env python3
"""Give exported functions of i386 PE modules the exact Windows entry bytes: 8B FF 55 8B EC.

llvm-mingw's -fms-hotpatch emits 66 90 (xchg ax,ax) at every i386 function entry; real Windows (and gcc's
ms_hook_prologue, which upstream Wine relies on) use 8B FF. Ubisoft Connect's API-hooking engine reports
'Error at hooking API ...' when an entry does not look like that (Wine bug 46626). Both forms are 2-byte no-ops
that leave all registers and flags unchanged, so the rewrite is behaviour-neutral. The same goes for the two encodings
of 'mov ebp,esp': MSVC/Windows emit 8B EC, gcc/clang emit 89 E5; an engine that matches the Windows byte pattern only
accepts the former, so 55 89 E5 at an entry (after the optional 8B FF) is rewritten to 55 8B EC.

Usage: patch-i386-hotpatch.py <dir>   (every *.dll/*.exe/*.drv/*.ocx/*.cpl/*.ax under <dir>, recursively)
"""
import os
import struct
import sys

EXTS = (".dll", ".exe", ".drv", ".ocx", ".cpl", ".ax", ".acm", ".tlb")


def patch(path):
    d = bytearray(open(path, "rb").read())
    if d[:2] != b"MZ" or len(d) < 0x40:
        return 0
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        return 0
    machine, nsec = struct.unpack_from("<HH", d, pe + 4)
    if machine != 0x14C:
        return 0
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    if struct.unpack_from("<H", d, opt)[0] != 0x10B:
        return 0
    exp_rva, exp_size = struct.unpack_from("<II", d, opt + 96)
    if not exp_rva:
        return 0
    secs = []
    for i in range(nsec):
        o = opt + optsz + i * 40
        vsz, va, rsz, roff = struct.unpack_from("<IIII", d, o + 8)
        secs.append((va, max(vsz, rsz), roff, rsz))

    def off(rva):
        for va, sz, roff, rsz in secs:
            if va <= rva < va + sz and rva - va < rsz:
                return roff + rva - va
        return None

    eo = off(exp_rva)
    if eo is None:
        return 0
    nfunc = struct.unpack_from("<I", d, eo + 20)[0]
    fo = off(struct.unpack_from("<I", d, eo + 28)[0])
    if fo is None:
        return 0
    n = 0
    for i in range(nfunc):
        rva = struct.unpack_from("<I", d, fo + 4 * i)[0]
        if not rva or exp_rva <= rva < exp_rva + exp_size:
            continue
        o = off(rva)
        if o is None:
            continue
        if d[o:o + 2] == b"\x66\x90":
            d[o:o + 2] = b"\x8b\xff"
            n += 1
        p = o + 2 if d[o:o + 2] == b"\x8b\xff" else o
        if d[p:p + 3] == b"\x55\x89\xe5":
            d[p + 1:p + 3] = b"\x8b\xec"
            n += 1
    if n:
        open(path, "wb").write(d)
    return n


total_files = total_funcs = 0
for root, _, files in os.walk(sys.argv[1]):
    for f in files:
        if f.lower().endswith(EXTS):
            n = patch(os.path.join(root, f))
            if n:
                total_files += 1
                total_funcs += n
print(f"hotpatch: {total_funcs} entry rewrites (66 90 -> 8B FF, 55 89 E5 -> 55 8B EC) in {total_files} modules")
