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

**Question**
By MadeiraDock.launchRefusal, 17/19/20 mean Steam wants content the game depends on. Which content is it (redistributables / shared depots 228980..228990 are in the depot selection)? Is there a way to make Steam's client accept the Madeira-installed files, e.g. validate or re-register, without re-downloading 26 GB?

**Attachments:** madeira-log.txt (run 1 and run 2), madeira-library.json. I checked them for account names before posting.
