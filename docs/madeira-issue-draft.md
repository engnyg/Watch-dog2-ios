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

**Update after a manual experiment (this narrows it down)**
The shared depot is `1716751` from owner app `1716750` (Ubisoft Connect PC Client), listed in my `appmanifest_447040.acf` as `"SharedDepots" { "1716751" "1716750" }`. The install log shows `[steam-shared-record] app=447040 shared=1 owners-written=0 owners-skipped=1`, so no `appmanifest_1716750.acf` was written by Madeira.
- Before: Valve's client created its own `appmanifest_1716750.acf` (StateFlags 66, empty InstalledDepots, buildid 0) and set my `appmanifest_447040.acf` to StateFlags 6 (update required). Launch: `launch-client-error=17`, `launch-update-wait=17`.
- I then replaced the owner record with the layout Madeira AppManifestWriter uses (StateFlags 4, buildid 25883745, InstalledDepots 1716751 with manifest 8458906404271031972, size 264202144; values from a public mirror). Valve's client did not rewrite it.
- After: error 17 is gone. Now `launch-client-error=22`, `launch-config-wait=22`, retries 1-3, then `launch-config-gave-up=24`, `probe-result=45`; the screen says "Steam did not finish loading this game's configuration after signing in." Two runs, 93 s and 150 s, same result. `appmanifest_447040.acf` is still StateFlags 6.

So writing the owner record seems necessary but not sufficient. Why did `owners-skipped=1` happen (`fetchAppInfo(1716750)` nil? the session also logged `url--1200` TLS failures)? And what makes Valve's client not load the game's config afterwards?

**Attachments:** madeira-log.txt (run 1 and run 2), madeira-library.json. I checked them for account names before posting.
