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
- I could not tell from the logs whether that is an emulation error or a deliberate integrity check in the
  program; I did not investigate it further and do not intend to work around it.

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
