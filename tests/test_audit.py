import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import audit  # noqa: E402


def make_macho(cputype=0x0100000C, cryptid=None, text=b"\x01\x02\x03\x04" * 4):
    uuid = bytes(range(16))
    cmds = struct.pack("<II16s", 0x1B, 24, uuid)
    cmds += struct.pack("<IIII", 0x32, 24, 1, 12 << 16) + struct.pack("<II", 0, 0)
    name = b"/usr/lib/libSystem.B.dylib\0".ljust(32, b"\0")
    cmds += struct.pack("<IIIIII", 0xC, 24 + len(name), 24, 0, 0, 0) + name
    if cryptid is not None:
        cmds += struct.pack("<IIIIII", 0x2C, 24, 0, 0, cryptid, 0)
    hdr_len = 32 + len(cmds) + 72 + 80
    seg = struct.pack("<II16sQQQQiiII", 0x19, 72 + 80, b"__TEXT", 0, 0, 0, 0, 0, 0, 1, 0)
    sect = struct.pack("<16s16sQQIIIIIIII", b"__text", b"__TEXT", 0, len(text), hdr_len, 0, 0, 0, 0, 0, 0, 0)
    n = 3 + (1 if cryptid is not None else 0) + 1
    header = struct.pack("<IiiIIIII", 0xFEEDFACF, cputype, 0, 2, n, len(cmds) + 72 + 80, 0, 0)
    return header + cmds + seg + sect + text


class AuditTest(unittest.TestCase):
    def run_audit(self, blob):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(blob)
        try:
            return audit.audit(f.name)
        finally:
            os.unlink(f.name)

    def test_parses_arm64(self):
        s = self.run_audit(make_macho())["slices"][0]
        self.assertEqual(s["cpu"], "arm64")
        self.assertEqual(s["platform"], "macOS")
        self.assertEqual(s["uuid"], "00010203-0405-0607-0809-0a0b0c0d0e0f")
        self.assertEqual(s["dylibs"][0]["path"], "/usr/lib/libSystem.B.dylib")
        self.assertIsNotNone(s["text_sha256"])

    def test_x86_only_is_no_go(self):
        self.assertEqual(audit.verdict(self.run_audit(make_macho(cputype=0x01000007)))[0], "NO-GO")

    def test_encrypted_is_no_go(self):
        self.assertEqual(audit.verdict(self.run_audit(make_macho(cryptid=1)))[0], "NO-GO")

    def test_arm64_is_go(self):
        self.assertEqual(audit.verdict(self.run_audit(make_macho()))[0], "GO")


class PatchTest(unittest.TestCase):
    def test_patch_roundtrip_and_guards(self):
        with tempfile.TemporaryDirectory() as d:
            blob = make_macho()
            src, dst, spec = (os.path.join(d, n) for n in ("in", "out", "p.json"))
            open(src, "wb").write(blob)
            off = len(blob) - 4
            json.dump({"uuid": "00010203-0405-0607-0809-0a0b0c0d0e0f",
                       "patches": [{"offset": hex(off), "old": "01020304", "new": "0a0b0c0d"}]}, open(spec, "w"))
            tool = os.path.join(ROOT, "tools", "patch_memory_budget.py")
            r = subprocess.run([sys.executable, "-I", tool, src, dst, spec], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(open(dst, "rb").read()[off:], bytes.fromhex("0a0b0c0d"))
            self.assertEqual(open(src, "rb").read(), blob)
            r = subprocess.run([sys.executable, "-I", tool, dst, dst + "2", spec], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)  # already patched -> refuse


if __name__ == "__main__":
    unittest.main()
