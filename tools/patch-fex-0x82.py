#!/usr/bin/env python3
"""FEX: let 32-bit group-1 opcode 0x82 reach ALUOp.

In 32-bit mode 0x82 is an alias of 0x80 (ADD/OR/ADC/SBB/AND/SUB/XOR/CMP r/m8, imm8). FEX's group tables already
route 0x82 /0,1,4,5,6 to OpDispatchBuilder::SecondaryALUOp, but that function's switch only lists 0x80, 0x81 and 0x83,
so those encodings hit "Unknown ALU Op" and DecodeFailure (the guest then takes STATUS_ILLEGAL_INSTRUCTION).
Real CPUs execute them; Ubisoft Connect's upc.exe does. Usage: patch-fex-0x82.py <OpcodeDispatcher.cpp>
"""
import re, sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
start = src.index("void OpDispatchBuilder::SecondaryALUOp(OpcodeArgs)")
end = src.index("#undef OPD", start)
body = src[start:end]
if "OpToIndex(0x82)" in body:
    print("already patched"); sys.exit(0)

pat = re.compile(r"^(?P<ind>[ \t]*)case OPD\(FEXCore::X86Tables::TYPE_GROUP_1, OpToIndex\(0x83\), (?P<reg>\d)\):\n", re.M)
n = 0
def add(m):
    global n
    n += 1
    return ("%scase OPD(FEXCore::X86Tables::TYPE_GROUP_1, OpToIndex(0x82), %s): // 32-bit only alias of 0x80\n" % (m.group("ind"), m.group("reg"))) + m.group(0)
new_body = pat.sub(add, body)
if n != 5:
    sys.exit("expected 5 case labels for 0x83, found %d" % n)
open(path, "w", encoding="utf-8").write(src[:start] + new_body + src[end:])
print("patched %d cases" % n)
