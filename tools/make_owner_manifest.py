#!/usr/bin/env python3
"""Write the shared-content owner record that Valve's client wants.

Reads a game's appmanifest_<appid>.acf, takes its SharedDepots block and
writes appmanifest_<owner>.acf in the layout Madeira's AppManifestWriter uses
for owners. Experimental: manifest ids and the build id are unknown (0), so
Steam may still ask to verify. Never overwrites an existing file.

Name and install folder of the owner are unknown here, so, like Madeira's own
fallback, the name is "App <owner>" and the folder is the game's installdir.
Override with --name / --installdir if you know them.

Usage: python3 -I tools/make_owner_manifest.py <appmanifest_447040.acf> <owner appid> <out dir>
                                               [--name N] [--installdir D]
                                               [--build ID] [--manifest GID] [--size BYTES]

With --build/--manifest/--size (public values for the owner app and the shared
depot, e.g. from SteamDB) the record matches what Madeira writes when it can
resolve the owner; without them Steam sees build 0 and asks for an update.
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


def field(text, key):
    m = re.search(r'"%s"\s+"([^"]*)"' % key, text)
    return m.group(1) if m else ""


def opt(flag):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else None


def build(owner, depots, last_owner, name, installdir, buildid="0", manifest=None, size=None):
    L = ['"AppState"', "{", f'\t"appid"\t\t"{owner}"', '\t"universe"\t\t"1"',
         f'\t"name"\t\t"{name}"', '\t"StateFlags"\t\t"4"', f'\t"installdir"\t\t"{installdir}"',
         '\t"LastUpdated"\t\t"0"', '\t"LastPlayed"\t\t"0"', f'\t"SizeOnDisk"\t\t"{size or 0}"',
         '\t"StagingSize"\t\t"0"', f'\t"buildid"\t\t"{buildid}"', f'\t"LastOwner"\t\t"{last_owner}"',
         '\t"DownloadType"\t\t"1"', '\t"UpdateResult"\t\t"0"', '\t"BytesToDownload"\t\t"0"',
         '\t"BytesDownloaded"\t\t"0"', '\t"BytesToStage"\t\t"0"', '\t"BytesStaged"\t\t"0"',
         f'\t"TargetBuildID"\t\t"{buildid}"', '\t"AutoUpdateBehavior"\t\t"0"',
         '\t"AllowOtherDownloadsWhileRunning"\t\t"0"', '\t"ScheduledAutoUpdate"\t\t"0"',
         '\t"InstalledDepots"', "\t{"]
    for d in depots:
        L += [f'\t\t"{d}"', "\t\t{"]
        if manifest:
            L.append(f'\t\t\t"manifest"\t\t"{manifest}"')
        if size:
            L.append(f'\t\t\t"size"\t\t"{size}"')
        L.append("\t\t}")
    L += ["\t}", '\t"UserConfig"', "\t{", '\t\t"language"\t\t"english"', "\t}",
          '\t"MountedConfig"', "\t{", '\t\t"language"\t\t"english"', "\t}", "}"]
    return "\n".join(L)


if __name__ == "__main__":
    if len(sys.argv) < 4:
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
        build(owner, depots, steam_id(text), opt("--name") or f"App {owner}",
              opt("--installdir") or field(text, "installdir"),
              opt("--build") or "0", opt("--manifest"), opt("--size")))
    print("wrote", out, "depots", depots)
