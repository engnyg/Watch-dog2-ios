**Title:** Watch_Dogs 2 (447040) stops at launch-client-error=17 / launch-update-wait=17; game window never appears

**Environment**
- Madeira v0.1.3 (4), sideloaded with a free Apple ID (profile=development, increased-memory=1, extended-va=0)
- iPhone18,3, iOS 26.6.1 (23G83), ram=7671MB (clamped to 6144MB by ml992)
- JIT via StikDebug: "JIT enabled and debugger attached" on every attempt

**What happens**
1. Install of app 447040 completes (`install complete app=447040 bytes=26282162453`, depots=6 files=138, build 11638094). The download was paused/resumed several times and early attempts logged `[steam-depot] failed app=447040 reason=url--1200`.
2. Launch: `[dock-installers] app=447040 program=ubisoft connect pc client file=UbisoftConnectInstaller.exe status=done` — so Ubisoft Connect's installer finishes; it is not where the launch fails.
3. Madeira Dock signs in: `session-authenticated-online=1`, `session-requested-app-entitled=1`, `session-requested-app-listed=1`, `session-subscription-count=316`.
4. About 10 s after sign-in: `launch-client-error=17`, `launch-update-wait=17`, then `launch-update-retry=1,2,3`. `launch-update-ready` never appears.
5. No game window is ever created (`detach-wait: presents=0`). The dockhost console shows `[steamhost] launch-update-retry=2/3`.

Reproduced in two runs (same result within ~15 s of sign-in on the second run). Not a one-off network blip.

**Suspected cause (from reading the source, not verified on device)**
`DepotDownloader` writes the shared-owner record only when `app.sharedOwners[ownerID]` exists; otherwise it counts `owners-skipped`. The code comment says Valve's client refuses to launch until the owner app has its own record ("required app N not ready", as with GTA V Enhanced / 1899670).
My log for 447040 has exactly that: `[steam-shared] app=447040 owners=0 resolved=0 missing=0` and `[steam-shared-record] app=447040 shared=1 owners-written=0 owners-skipped=1`. The depot selection shows depots 228983/228984/228989/228990 as `shared<228980`, so the owner is app 228980 and no `appmanifest_228980.acf` was written. Steam then reports error 17 (needs content).
`fetchAppInfo(228980)` may have returned nil here (the same session logged `url--1200` TLS failures), or `sharedOwners` was never filled for this app.

**Question**
Could the owner record be written (or the owner metadata re-fetched) when `sharedOwners` is empty but `shared` is not? Is there a supported way to repair an already installed game, without re-downloading 26 GB?

**Attachments:** madeira-log.txt (run 1 and run 2), madeira-library.json. I checked them for account names before posting.
