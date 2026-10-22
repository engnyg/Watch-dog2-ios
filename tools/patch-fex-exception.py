#!/usr/bin/env python3
"""FEX Exception.h: fix ICEBP (0xF1) ExceptionAddress in HandleGuestException.

Real x86 delivers EXCEPTION_SINGLE_STEP for INT1/ICEBP as a *trap-type* exception:
ExceptionAddress = EIP+1 (the byte AFTER the 0xF1 opcode). FEX's HandleGuestException
X86_TRAPNO_DB case sets ExceptionAddress = Rip without advancing, so upc.exe's .ubx
packer self-integrity check sees the wrong address and terminates with 0xDEADC0DE.

Discriminant: Fault.err_code == 0 for ICEBP (INTOp sets ErrorRegister=0); hardware
TF single-step carries DR6.BS = 0x4000 in err_code, hardware breakpoints carry other
non-zero DR6 bits. So err_code == 0 is safe to use as the ICEBP-only guard.

Usage: patch-fex-exception.py <Source/Windows/Common/Exception.h>
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()

if "ml-icebp-fex" in src:
    print("already patched"); sys.exit(0)

OLD = "    case FEXCore::X86State::X86_TRAPNO_DB: Dst.ExceptionCode = EXCEPTION_SINGLE_STEP; return Dst;"
NEW = """\
    case FEXCore::X86State::X86_TRAPNO_DB:
      Dst.ExceptionCode = EXCEPTION_SINGLE_STEP;
      if (Fault.err_code == 0) { // ml-icebp-fex: ICEBP (0xF1) is trap-type; advance EIP past the 1-byte opcode
        ++Rip;
        Dst.ExceptionAddress = reinterpret_cast<void*>(Rip);
      }
      return Dst;"""

if OLD not in src:
    sys.exit("target string not found in %s — check FEX commit" % path)

open(path, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
print("patched: ICEBP ExceptionAddress fix applied (ml-icebp-fex)")
