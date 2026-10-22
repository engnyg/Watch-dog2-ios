#!/usr/bin/env python3
"""Binary-patch wow64_NtRaiseHardError in wow64.dll (aarch64 PE DLL).

The tracked wow64.dll contains a FIXME stub that:
  - logs and returns STATUS_NOT_IMPLEMENTED without setting *Response
  - causes upc.exe to call NtTerminateProcess(0xDEADC0DE)

Patching the Wine source (tools/patch-wine-wow64.py) is insufficient because
wow64.dll is a tracked pre-compiled binary in the Madeira repo — no CI stage
recompiles it from the patched source.

This script patches the binary directly using the PE export table to locate
wow64_NtRaiseHardError, then overwrites its entry with 6 ARM64 instructions:

    LDR  X1, [X0, #24]    ; response32 = *(UINT64 *)(args + 24)
    CBZ  X1, .skip         ; if null, skip store
    MOVZ W2, #4            ; ResponseIgnore = 4
    STR  W2, [X1]          ; *response32 = 4
  .skip:
    MOVZ X0, #0            ; return STATUS_SUCCESS (0)
    RET

Offset 24 in the UINT *args flat array:
  args+0  : status      (ULONG, get_ulong)
  args+4  : count       (ULONG, get_ulong)
  args+8  : params_mask (ULONG, get_ulong)
  args+12 : params32    (PTR,   get_ptr, 8 bytes)
  args+20 : option      (ULONG, get_ulong)
  args+24 : response32  (PTR,   get_ptr, 8 bytes)  ← what we read

Usage:
    patch-wow64-binary.py <path/to/wow64.dll>
"""
import sys
import struct

TARGET_EXPORT = "wow64_NtRaiseHardError"

# ARM64 little-endian instruction bytes for the replacement function body.
# (Validated against ARMv8-A ISA reference, 4 bytes per instruction, LE.)
PATCH = bytes([
    0x01, 0x0C, 0x40, 0xF9,  # LDR  X1, [X0, #24]
    0x61, 0x00, 0x00, 0xB4,  # CBZ  X1, #12  (3 instructions forward to MOVZ X0)
    0x82, 0x00, 0x80, 0x52,  # MOVZ W2, #4
    0x22, 0x00, 0x00, 0xB9,  # STR  W2, [X1]
    0x00, 0x00, 0x80, 0xD2,  # MOVZ X0, #0
    0xC0, 0x03, 0x5F, 0xD6,  # RET
])


def rva_to_offset(rva, sections):
    for vaddr, raw_off, size in sections:
        if vaddr <= rva < vaddr + size:
            return raw_off + (rva - vaddr)
    raise ValueError(f"RVA 0x{rva:x} not covered by any section")


def patch_dll(path):
    with open(path, "rb") as f:
        data = bytearray(f.read())

    if data[:2] != b"MZ":
        sys.exit(f"{path}: not a PE file")

    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off:pe_off + 4] != b"PE\x00\x00":
        sys.exit(f"{path}: invalid PE signature at 0x{pe_off:x}")

    coff = pe_off + 4
    machine = struct.unpack_from("<H", data, coff)[0]
    if machine != 0xAA64:
        sys.exit(f"{path}: not ARM64 PE (machine=0x{machine:04x}); cannot patch")

    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_hdr_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt_hdr = coff + 20

    magic = struct.unpack_from("<H", data, opt_hdr)[0]
    if magic != 0x20B:
        sys.exit(f"{path}: not PE32+ optional header (magic=0x{magic:04x})")

    # Data directory[0] = export table (RVA, size) at opt_hdr + 112
    export_rva  = struct.unpack_from("<I", data, opt_hdr + 112)[0]
    if export_rva == 0:
        sys.exit(f"{path}: no export directory")

    # Parse section table
    sections_base = opt_hdr + opt_hdr_size
    sections = []
    for i in range(num_sections):
        sh = sections_base + i * 40
        vsize   = struct.unpack_from("<I", data, sh + 16)[0]
        vaddr   = struct.unpack_from("<I", data, sh + 20)[0]
        rawsize = struct.unpack_from("<I", data, sh + 24)[0]
        rawoff  = struct.unpack_from("<I", data, sh + 28)[0]
        sections.append((vaddr, rawoff, max(vsize, rawsize)))

    exp_off = rva_to_offset(export_rva, sections)

    num_names = struct.unpack_from("<I", data, exp_off + 24)[0]
    funcs_rva = struct.unpack_from("<I", data, exp_off + 28)[0]
    names_rva = struct.unpack_from("<I", data, exp_off + 32)[0]
    ords_rva  = struct.unpack_from("<I", data, exp_off + 36)[0]

    funcs_off = rva_to_offset(funcs_rva, sections)
    names_off = rva_to_offset(names_rva, sections)
    ords_off  = rva_to_offset(ords_rva, sections)

    # Locate the target export by name
    func_rva = None
    for i in range(num_names):
        name_rva = struct.unpack_from("<I", data, names_off + i * 4)[0]
        name_off = rva_to_offset(name_rva, sections)
        j, name_bytes = name_off, bytearray()
        while data[j]:
            name_bytes.append(data[j]); j += 1
        if name_bytes.decode("ascii") == TARGET_EXPORT:
            ord_idx = struct.unpack_from("<H", data, ords_off + i * 2)[0]
            func_rva = struct.unpack_from("<I", data, funcs_off + ord_idx * 4)[0]
            break

    if func_rva is None:
        sys.exit(f"{path}: export '{TARGET_EXPORT}' not found in export table")

    func_off = rva_to_offset(func_rva, sections)
    print(f"found {TARGET_EXPORT}: RVA=0x{func_rva:08x}  file_off=0x{func_off:08x}")

    # Idempotency: already patched if first 4 bytes match our patch
    if data[func_off:func_off + 4] == PATCH[:4]:
        print(f"already patched (first 4 bytes match); skipping")
        return

    if func_off + len(PATCH) > len(data):
        sys.exit(f"patch extends beyond file end; aborting")

    data[func_off:func_off + len(PATCH)] = PATCH

    with open(path, "wb") as f:
        f.write(data)

    print(f"patched {TARGET_EXPORT}: {len(PATCH)} bytes at file offset 0x{func_off:08x}"
          f"  (ml-wow64-raiseharderror-binary)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <wow64.dll>")
    patch_dll(sys.argv[1])
