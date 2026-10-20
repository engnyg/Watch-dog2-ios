# Draft issue for Madeira: Watch Dogs 2 livelocks on an atomic RMW into a tracked code page

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

## Why it never completes (reading the source)

`Source/Windows/ARM64EC/Module.cpp`, `ResetToConsistentStateImpl`:

1. `InvalidationTracker->HandleRWXAccessViolation` accepts the fault. Because the fault page is in the current
   block, it takes the "inline SMC" branch: it sets `X11 = 1` (single-step) and re-enters at the guest RIP.
2. The single-stepped instruction is the same `LDADDAL`, on the same read-only host page. It faults again.
3. On the `FEX_IOS_HOST` `else` branch (ml657) the page is never made writable. `IosSmcStoreFastPath` only
   recognises STR/STUR forms; `HandleUnalignedAccess` -> `HandleAtomicMemOp` does emulate LDADD, but it writes
   through `IosAtomicWritableAlias()` (`FEXCore/Source/Utils/ArchHelpers/Arm64.cpp:384`), which only resolves
   (a) the fixed JIT pool and (b) anonymous aliases published for the Mono bridge (`IosMonoResolveRW`). For this
   page, which is neither, it returns the address unchanged ("neither the pool nor a live anonymous alias --
   leave it alone"), so the emulated atomic hits the same read-only view and faults again.

The comment at ml657 already names this case: "An ALIGNED store trapped by SMC would still loop -- not observed,
and it would need a different fix". This looks like the first observation, with an atomic instead of a store.

## Possible fix directions (untested)

- Give `IosAtomicWritableAlias` a third source for image-section pages: build a RW alias of the faulting page
  (`mach_vm_remap`, the region reports `max=3`) and return it, caching per page; or
- have the SMC else-branch make the tracked page host-writable for the duration of the atomic and then
  re-protect it, keeping the invalidation of blocks on that page.

I have not tried either. I can test a build on device if someone points at the intended place.

## Not the cause

- Not the translator binary: tracked `xtajit64.dll` behaves the same as a CI rebuild.
- Not Steam/Ubisoft: the loop starts after `WatchDogs2.exe`/`Disrupt_64.dll` are loaded and before the first
  `Present`; no Ubisoft launcher process has been started yet.
- Waiting does not help: 5 minutes, ~468k faults, `presents=0` throughout.
