#!/usr/bin/env python3
"""Madeira ntdll: correct INT1/ICEBP (opcode 0xF1) exception delivery.

On real x86, opcode 0xF1 (ICEBP/INT1) generates a trap-type #DB exception:
ExceptionAddress points to the byte AFTER 0xF1, not at it. FEX does not decode
0xF1 and emits BRK #0 (imm=0), which hits the `default` case in trap_handler
and produces EXCEPTION_ILLEGAL_INSTRUCTION with ExceptionAddress pointing AT
the 0xF1 byte. The one-byte discrepancy breaks self-integrity checks inside
packed programs such as Ubisoft Connect's upc.exe (Ubisoft .ubx packer).

Fix: in the `default` BRK-imm case, read the guest byte at ctx.Pc. If it is
0xF1, promote to EXCEPTION_SINGLE_STEP and advance ctx.Pc by 1.

Usage: patch-icebp.py <signal_arm64_ios.c>
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()

if "ml-icebp" in src:
    print("already patched"); sys.exit(0)

OLD = (
    "            default:\n"
    "                rec.ExceptionCode = EXCEPTION_ILLEGAL_INSTRUCTION;\n"
    "                break;\n"
    "            }\n"
    "        }\n"
    "        break;\n"
    "    default:\n"
    "        rec.ExceptionCode = EXCEPTION_ILLEGAL_INSTRUCTION;\n"
    "        break;\n"
    "    }\n"
    "\n"
    "    setup_raise_exception( sigcontext, &rec, &ctx );\n"
)

NEW = (
    "            default:\n"
    "                rec.ExceptionCode = EXCEPTION_ILLEGAL_INSTRUCTION;\n"
    "#ifdef WINE_IOS\n"
    "                /* ml-icebp: INT1/ICEBP (opcode 0xF1) is an undocumented x86 instruction\n"
    "                 * that FEX does not decode and emits as BRK #0 (imm=0).\n"
    "                 * On real hardware 0xF1 generates a trap-type #DB: ExceptionAddress points\n"
    "                 * to the byte AFTER 0xF1, not at it.  FEX stores guest EIP pointing AT the\n"
    "                 * 0xF1 byte; the one-byte discrepancy causes the .ubx packer self-integrity\n"
    "                 * check (ExceptionAddress == expected_next_insn) to fail in upc.exe.\n"
    "                 * Fix: detect 0xF1 at ctx.Pc (<4 GB = 32-bit guest), promote to\n"
    "                 * EXCEPTION_SINGLE_STEP and advance ctx.Pc by 1. */\n"
    "                if (ctx.Pc != 0 && ctx.Pc < 0x100000000ull)\n"
    "                {\n"
    "                    uint8_t guest_byte = 0;\n"
    "                    vm_size_t osz = 1;\n"
    "                    if (mach_vm_read_overwrite( mach_task_self(), (mach_vm_address_t)ctx.Pc,\n"
    "                                                1, (mach_vm_address_t)&guest_byte, &osz ) == KERN_SUCCESS\n"
    "                        && osz == 1 && guest_byte == 0xF1)\n"
    "                    {\n"
    "                        dprintf( STDERR_FILENO,\n"
    "                                 \"[icebp-guest] INT1/ICEBP at guest 0x%llx: promoting to \"\n"
    "                                 \"SINGLE_STEP and advancing EIP+1 (trap-type fix) rev=ml-icebp\\n\",\n"
    "                                 (unsigned long long)ctx.Pc );\n"
    "                        rec.ExceptionCode = EXCEPTION_SINGLE_STEP;\n"
    "                        ctx.Pc++;\n"
    "                    }\n"
    "                }\n"
    "#endif\n"
    "                break;\n"
    "            }\n"
    "        }\n"
    "        break;\n"
    "    default:\n"
    "        rec.ExceptionCode = EXCEPTION_ILLEGAL_INSTRUCTION;\n"
    "        break;\n"
    "    }\n"
    "\n"
    "    setup_raise_exception( sigcontext, &rec, &ctx );\n"
)

count = src.count(OLD)
if count != 1:
    sys.exit("expected exactly 1 occurrence of the target block, found %d" % count)

open(path, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
print("patched: INT1/ICEBP trap-type fix applied to trap_handler default BRK case")
