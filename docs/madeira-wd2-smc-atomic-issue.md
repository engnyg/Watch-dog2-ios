# Draft issue for Madeira: Watch Dogs 2 spends minutes in an SMC fault loop on an interlocked op inside a tracked code page

Status: DRAFT, not posted. Everything below is read from device logs and from the FEX source at
`willfaust/FEX` branch `ios-port-2607` (commit f59cab9). Root cause is a hypothesis; I have no device-side
confirmation of the proposed fix.

## Setup

- Madeira `main` @ 279fd0f (built by CI, Debug, unsigned IPA, sideloaded with a free Apple ID),
  `xtajit64.dll` byte-identical to the one tracked in the repo.
- iPhone18,3 (7671 MB RAM), iOS 26.6.1, JIT via StikDebug started from Madeira's Play button.
- Watch Dogs 2 (Steam app 447040), started through Madeira Dock.

## What works (so this is not a Steam / DRM / JIT / DLL problem)

- Dock: `session-authenticated-online=1`, `session-requested-app-entitled=1`, `launch-client-error=0`,
  `launch option 1` chosen automatically.
- Steam then starts `WatchDogs2.exe -uplay_steam_mode`; `Disrupt_64.dll`, `uplay_r1_loader64.dll`,
  DXMT `d3d11`/`winemetal`, MSVCR110/MSVCP110/gdiplus all load.

## What happens

The game never presents a frame (`detach-wait: presents=0` from 30 s to 301 s, CPU on E cores).
The log fills with the same two lines, 248,110 `Handled inline self-modifying code` events in ~5.3 minutes
(`[fault_rip] cnt=468000`, `[smc] ... 234000 self-modifying writes handled`):

```
D 24 Exception: Code: C0000005 Address: 3371FAF2C AV READ of FBABA7C80
D 24 Handled inline self-modifying code: pc: 3371FAF2C rip: FBABA7C72 fault: FBABA7C80
```

- Only TWO guest RIPs alternate (`..7C72`, `..7D1C`), one data address (`..7C80`), forever.
- Same location in every run: `Disrupt_64.dll` base `FB2790000` + `0x8417C80` (an earlier run with a different
  base gives the same RVA).
- Each iteration is `VirtualAlloc(8 MB, MEM_COMMIT, RW)` / `VirtualFree(MEM_DECOMMIT)` plus one SMC fault.
- The first SMC events are plain writes into the image (`[ml1001] previous SMC store ... LEFT THE BYTES UNCHANGED
  -- the store was DROPPED`), then the loop above.

## The faulting instruction

`[av-detail]`/`[bus-handler]` for the repeating fault:

```
pc=0x3371faf2c  insn=0xb8e60008  esr=0x9200004f  addr=0xfbaba7c80
region=0xfbaba4000+0x4000 prot=1 max=3     (host: READ only, max RW)
Wine view: vprot=0x25 COMMITTED READ EXEC, SEC_IMAGE WRITECOPY   (wine_want=5)
[wr-strip-declined] ... (not a strip)
[ml1048-non-image] ... wine expects unix_prot=5
ml1002: [smc-write] guest callers: all retRIP=0
```

- `0xb8e60008` decodes as `LDADDAL W6, W8, [X0]`, i.e. an aligned x86 `lock xadd dword [mem], reg`.
- `esr=0x9200004f`: EC 0x24, WnR=1, DFSC 0x0f = write permission fault, level 3. (FEX prints it as "AV READ"
  because the exception record is built from the read side of the atomic.)
- So the guest does an interlocked read-modify-write on a variable that lives in the same 16 KB page as code in
  the image section (a protector-style layout). The page is write-protected for SMC tracking.

## What the loop is (revised after reading the 5-minute log more closely)

My first reading was "the atomic never lands". The log does not support that: over 248,110 events there is NOT
ONE `Handled self-modifying code` line (the non-inline `else` branch, sampled 1 in 1000, would print ~248 of
them), and every event is exactly one fault followed by one `Handled inline self-modifying code`. So the
single-stepped `LDADDAL` does complete. The better reading is a performance cliff:

1. The guest runs a tight loop whose two sites (`..7C72`, `..7D1C`) do an interlocked op on a variable
   (`..7C80`) sitting in the same FEX page as the loop's own code.
2. `InvalidationTracker::HandleRWXAccessViolation` (Source/Windows/Common/InvalidationTracker.cpp:512)
   invalidates the WHOLE 4 KB page of compiled blocks and unprotects the page through `NtProtectVirtualMemory`.
3. The inline-SMC branch in `ResetToConsistentStateImpl` (Module.cpp ~1336) re-enters in single-step mode, the
   atomic lands, and execution continues. The next entry into the loop recompiles the blocks (the faulting host
   PC in the log creeps forward by ~0x258 per iteration = fresh code every time), which re-arms the trap.
4. Result: one Mach exception + one page invalidation + one recompile + two protection changes per loop
   iteration, ~1,100 iterations per second, against a loop that on a PC runs millions of times per second.

If that is right it is not an unhandled atomic but "data word inside a tracked code page". Directions:

- Invalidate only the written bytes (`[FaultAddress, FaultAddress+16)`) instead of the whole page in
  `HandleRWXAccessViolation`. A block that stops before the data word would survive, so the loop would stop
  recompiling. The trap must then be re-armed after the single step, otherwise later real SMC on that page is
  missed.
- Or, for a game that does not need it, run with `FEX_SMCCHECKS=none` (`DisableSMCDetection`, which
  `ProtectRWXIntervalsInternal` honours by never trapping). Untested on this game; I do not know whether
  Disrupt_64's startup depends on SMC detection.

Still unknown: whether the loop would eventually finish at this rate, and what it is waiting for. The
earlier "atomic cannot be written through IosAtomicWritableAlias" observation (Arm64.cpp:384) is real for
pages with no alias, but it is not what this log shows.

## Not the cause

- Not the translator binary: tracked `xtajit64.dll` behaves the same as a CI rebuild.
- Not Steam/Ubisoft: the loop starts after `WatchDogs2.exe`/`Disrupt_64.dll` are loaded and before the first
  `Present`; no Ubisoft launcher process has been started yet.
- Waiting does not help: 5 minutes, ~468k faults, `presents=0` throughout.
