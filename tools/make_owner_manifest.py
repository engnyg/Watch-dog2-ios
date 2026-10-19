#!/usr/bin/env python3
"""Write the shared-content owner record that Valve's client wants.

Reads a game's appmanifest_<appid>.acf, takes its SharedDepots block and
writes appmanifest_<owner>.acf in the layout Madeira's AppManifestWriter uses
for owners. Experimental: manifest ids and the build id are unknown (0), so
Steam may still ask to verify. Never overwrites an existing file.

Usage: python3 -I tools/make_owner_manifest.py <appmanifest_447040.acf> <owner appid> <out dir>
"""
import os
import re
import sys


def shared_depots(text, owner):
    block = re.search(r'"SharedDepots"\s*\{([^}]*)\}', text)
    if not block:
        sys.exit("no SharedDepots block in the game's record")
    pairs = re.findall(r'"(\d+)"\s+"(\d+)"', block.group(1))
    return sorted(int(d) for d, o in pairs if o == str(owner))


def steam_id(text):
    m = re.search(r'"LastOwner"\s+"(\d+)"', text)
    return m.group(1) if m else "0"


def build(owner, depots, last_owner, name, installdir):
    L = ['"AppState"', "{", f'\t"appid"\t\t"{owner}"', '\t"universe"\t\t"1"',
         f'\t"name"\t\t"{name}"', '\t"StateFlags"\t\t"4"', f'\t"installdir"\t\t"{installdir}"',
         '\t"LastUpdated"\t\t"0"', '\t"LastPlayed"\t\t"0"', '\t"SizeOnDisk"\t\t"0"',
         '\t"StagingSize"\t\t"0"', '\t"buildid"\t\t"0"', f'\t"LastOwner"\t\t"{last_owner}"',
         '\t"DownloadType"\t\t"1"', '\t"UpdateResult"\t\t"0"', '\t"BytesToDownload"\t\t"0"',
         '\t"BytesDownloaded"\t\t"0"', '\t"BytesToStage"\t\t"0"', '\t"BytesStaged"\t\t"0"',
         '\t"TargetBuildID"\t\t"0"', '\t"AutoUpdateBehavior"\t\t"0"',
         '\t"AllowOtherDownloadsWhileRunning"\t\t"0"', '\t"ScheduledAutoUpdate"\t\t"0"',
         '\t"InstalledDepots"', "\t{"]
    for d in depots:
        L += [f'\t\t"{d}"', "\t\t{", "\t\t}"]
    L += ["\t}", '\t"UserConfig"', "\t{", '\t\t"language"\t\t"english"', "\t}",
          '\t"MountedConfig"', "\t{", '\t\t"language"\t\t"english"', "\t}", "}"]
    return "\n".join(L)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    game, owner, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    text = open(game, encoding="utf-8").read()
    depots = shared_depots(text, owner)
    if not depots:
        sys.exit(f"the game's record lists no depots shared from {owner}")
    out = os.path.join(outdir, f"appmanifest_{owner}.acf")
    if os.path.exists(out):
        sys.exit(f"{out} already exists; not overwriting")
    open(out, "w", encoding="utf-8", newline="\n").write(
        build(owner, depots, steam_id(text), "Steamworks Common Redistributables", "Steamworks Shared"))
    print("wrote", out, "depots", depots)
