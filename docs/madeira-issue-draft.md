**Title:** Watch_Dogs 2 (447040) on release v0.1.3: what I found, and which unreleased fixes it needs

**Environment**
- Madeira release v0.1.3 (4) (published 03 Oct), free Apple ID, JIT via StikDebug
- iPhone18,3, iOS 26.6.1, ram=7671MB (clamped to 6144MB)

**Findings, in the order they appeared (all from my logs, Valve's own `content_log.txt`, and current `main`)**
1. Madeira Dock start: `launch-client-error=17`. My install record for 447040 lists `"SharedDepots" { "1716751" "1716750" }` (1716750 = Ubisoft Connect PC Client), but install logged `[steam-shared-record] ... owners-written=0 owners-skipped=1`, so no `appmanifest_1716750.acf`. Valve's client created an empty one (StateFlags 66) and refused the launch. Writing the owner record by hand (StateFlags 4, buildid, InstalledDepots 1716751 with manifest and size) removed error 17. Possible fix: write the owner record even when `fetchAppInfo(1716750)` returns nil (patch attached in the fork notes).
2. Next: `launch-client-error=22`. Valve's `content_log.txt`: `Failed running app 447040 (entry for launch option 0 not found)`. Public `config.launch` for 447040 has only key `"1"`. Current `main` resolves the key (`[madeira-dock] launch option N` in ContentView), my release build never logs that line.
3. "Start with: The game" on `bin/WatchDogs2.exe`: `0xC0000135` for `MSVCR110.dll`, then for `gdiplus.dll` (needed by `Disrupt_64.dll`). Both are in `app/Madeira/arm64ec-windows/` on `main`, not in the release.
4. With both DLLs supplied, the game starts, spawns `UbisoftGameLauncher.exe -gamelauncher_wait_handle ... -upc_uplay_id 3619` and exits with code 0; the session ends and Madeira returns to the library. `env.MADEIRA_WAIT_CHILDREN=1` is read (`[madeira-env] MADEIRA_WAIT_CHILDREN=1`) but the session still ends and neither `[WineProc]` child-process line is printed, so the release seems to lack that code, or no live child was counted.
5. The Game details page of the release has no `Advanced > This game's config` section (it exists in `main`'s `Library.swift`).

**Questions**
- Is a release with the current `main` planned? Everything above except the owner record seems fixed there.
- Has Watch_Dogs 2 (Ubisoft Connect handoff, Easy Anti-Cheat, 6 GB limit) been tried on `main`?
