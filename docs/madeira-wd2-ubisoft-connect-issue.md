# Draft issue for Madeira: Watch Dogs 2 (Steam) stops at Ubisoft Connect's `upc.exe` (32-bit, exits 0xDEADC0DE)

Status: DRAFT, not posted. Everything below is read from device logs and from the FEX / Wine sources at the
submodule pins of Madeira `main` @ 279fd0f. Nothing here was run outside the device logs.

## Setup

- Madeira `main` @ 279fd0f built by CI (Debug, unsigned IPA, free Apple ID). Original tracked `xtajit64.dll`.
  32-bit side: `i386-windows` farm built with `build/wine-i386/build.sh` (725 files, DXMT i386 included),
  `xtajit.dll` rebuilt with `build/fex-wow64/build.sh` (see "FEX fix" below).
- iPhone18,3, iOS 26.6.1, JIT through StikDebug started from Madeira's Play button.
- Watch Dogs 2 (Steam app 447040) started through Madeira Dock; Steam online, launch option 1.
- Per-game config: `env.FEX_SMCCHECKS = none` (needed: without it the game spends minutes in an SMC fault loop at
  `Disrupt_64.dll+0x8417C80`, see docs/madeira-wd2-smc-atomic-issue.md; with it the loop is gone).

## What works

`WatchDogs2.exe` starts, spawns `UbisoftGameLauncher.exe -gamelauncher_wait_handle ...` (32-bit) and exits 0, which is
how the Steam build hands over to Ubisoft Connect. With the i386 farm present the 32-bit launcher runs (threads
`UPC_Net`, `UPC_UI`), loads the 32-bit `steam_api.dll` / `steamclient.dll` / `steam.dll`, reads
`HKCU\Software\Valve\Steam\ActiveProcess`, then starts `upc.exe -upc_uplay_id 3619 -uplay_steam_mode -upc_game_starter`
(32-bit, CEF based). `upc.exe` loads `libcef.dll`, `d3d9.dll` (DXMT shim), winhttp, etc.

## What happens

- About 8 s after start `upc.exe` calls `NtRaiseHardError(0x50000018, ...)` and exits with `0xDEADC0DE`.
  Its own log (`Ubisoft Game Launcher/logs/game_starter_log.txt`) has one line:
  `SteamInfoReceiver.cpp (142) Failed receive local steam response for account. Error code: 3, IOFailure: false`.
- Meanwhile the 32-bit launcher polls `\\.\pipe\terminal_1_game_start_ipc_pipe_` (86 attempts, always
  STATUS_OBJECT_NAME_NOT_FOUND). Nothing creates it, presumably because `upc.exe` died first.
- `upc.exe` itself never opens a Steam registry key, Steam file or socket (trace+reg/file/winsock show only
  `WSAStartup`), so the "local steam response" is not something it reads from the prefix.
- Right before the exit FEX hands the guest a synchronous fault at the same dispatcher address every run
  (`[store-undecoded] insn=0xd4200000 pc=0x336ff8318`, `[exc-disp] raise code=c000001d`, guest eip `0x2C1662F`),
  which Madeira dispatches to the guest as `EXCEPTION_SINGLE_STEP`; the guest's SEH handler runs and the process ends
  with the hard error above. `eip 0x2C1662F` is in a large high section of `upc.exe`.
- The ICEBP fault (`0xF1`) is intentional: the same code path also calls `NtSetInformationThread`
  (ThreadHideFromDebugger) repeatedly and reads `NtQueryInformationProcess` (ProcessDebugPort), consistent with
  a standard integrity/anti-debug self-check in the unpacked runtime. After the ICEBP fix, `upc.exe` reaches the
  hard error stage consistently, so the self-check passes.

## Wine fix found on the way: wow64_NtRaiseHardError stub

`wow64_NtRaiseHardError` in Wine's `dlls/wow64/system.c` is a FIXME stub: it logs and returns
`STATUS_NOT_IMPLEMENTED` without setting `*Response`. `upc.exe` reads `*Response` to decide whether to continue;
the stub leaves it 0 (ReturnToCaller) so `upc.exe` immediately calls `NtTerminateProcess(0xDEADC0DE)`.

Fix (now applied in the CI build): translate the 32-bit argument frame to 64-bit (UNICODE_STRING32 → UNICODE_STRING
via `get_ptr()` which adds the WoW64 guest-window base), forward to the 64-bit `NtRaiseHardError`, and fall back to
`ResponseIgnore (4)` when the server returns 0 (headless iOS, no GUI). After this fix the hard error text is captured
in the device log:

```
ml-wow64 hard error: status 50000018 count 4 mask c option 0
ml-wow64   param 0: [Error at hooking API "LdrFindResource_U"]
ml-wow64   param 1: [upc.exe]
ml-wow64   NtRaiseHardError returned 00000000 response 4
```

Status `0x50000018` = `STATUS_VDM_HARD_ERROR`, option `0` = `OptionAbortRetryIgnore`. The text "Error at hooking API
"LdrFindResource_U"" is from upc's own internal hook engine, not from Wine's hooking. With ResponseIgnore returned,
`upc.exe` no longer terminates immediately — but it then reaches the same `EXCEPTION_SINGLE_STEP` path and still
exits with `0xDEADC0DE` shortly after.

## i386 entry-byte investigation (hypothesis tested and excluded)

**Observation (device log, Build #29):** just before the hard error, upc's hook engine dumped the entry bytes of
`ntdll.dll!LdrFindResource_U` (32-bit): `66 90 55 89 E5 53 57 56 83 EC 5C ...` — llvm-mingw's `66 90` (xchg ax,ax)
hotpatch prefix and `89 E5` (AT&T mov) encoding of `mov ebp,esp`. Real Windows 32-bit ntdll entries use `8B FF`
(mov edi,edi) + `55 8B EC` (push ebp; mov ebp,esp) (Wine bug 46626).

**Hypothesis:** upc's hook engine matches the Windows byte pattern `8B FF 55 8B EC` exactly and fails if the entry
looks different.

**Result (Build #30):** rewrote `66 90` → `8B FF` at every exported i386 PE entry (all of
`app/Madeira/i386-windows`). Entry is now `8B FF 55 89 E5 ...`. Still fails with the same "Error at hooking API"
message.

**Result (Build #31):** also rewrote `55 89 E5` → `55 8B EC`. Entry is now exactly `8B FF 55 8B EC 53 57 56 83 EC
5C ...` (matches Windows byte-for-byte). Still fails with the same message. ~504 other hook trampolines had been
installed in ntdll before this attempt, so the engine does reach and process the table.

**Conclusion:** the entry-byte pattern is not the cause. The hook engine is failing for a reason that is not visible
from the device logs without reverse-engineering upc's unpacked runtime. The entry-byte rewrite was reverted from CI.

## FEX fix found on the way (real bug, small)

32-bit opcode `0x82` (alias of `0x80`, `ADD/OR/AND/SUB/XOR r/m8, imm8`) is routed by the group tables to
`OpDispatchBuilder::SecondaryALUOp`, but that function's `switch` only lists `0x80`, `0x81`, `0x83`, so these hit
`Unknown ALU Op: 0x10/0x11/0x14/0x15/0x16` and DecodeFailure. 34 such lines per `upc.exe` run before the fix,
0 after. Patch: add the five `OpToIndex(0x82)` case labels (flags are identical to the `0x80` entries).
This did not change the `upc.exe` outcome.

## Questions

- Is Ubisoft Connect (32-bit CEF `upc.exe`) expected to run under the WoW64 path? Is WD2 / Ubisoft Connect a known
  unsupported case?
- Is there a supported way to get the Steam account info to `upc.exe` in `-uplay_steam_mode` that I am missing?
