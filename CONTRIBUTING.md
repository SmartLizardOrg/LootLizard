# Contributing to LootLizard

LootLizard is an experimental community project under [molnard-labs](https://github.com/molnard-labs/LootLizard). Pull requests for coordinate corrections, additional point datasets, translations and code fixes are welcome. A coordinate passing validation does not prove that a room exists or remains accessible in the current game.

## Correct or add point data

1. Fork the repository and edit `data/<map-id>.json` on a branch based on `main`. These are the human-editable source files. Do not edit the generated `metadata` branch or add `maps.json` to `main`.
2. Keep each existing map id and point id stable. Add new point ids rather than renumbering an entire list. Explain removals and corrections; a name change is not a reason to replace an id.
3. Supply a reusable source URL, its data license and attribution. Prefer a pinned commit/permalink or a dated primary source. A repository's code license is not automatically a license for copied coordinates, game artwork or another site's data. Retain required notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
4. Describe manual coordinate evidence and its limits in the PR: game/map version and date, mode, full-map grid anchors or known image dimensions, normalization method, whether an entrance or only a room center was checked, and completeness. A model prediction or successful projection is not independent ground truth. Mark unverified or incomplete data honestly in `source.notes`.
5. Run validation and tests below, then open a PR against `main` using the template. Do not commit copyrighted game map images, private screenshots, local reference catalogs, profiles, usernames or account data. Use shareable source links and textual measurement notes.

Example only; this identifies no real room:

```json
{
  "id": "my-map",
  "name": "My map",
  "size_m": 8000,
  "source": {
    "url": "https://example.org/data-source",
    "license": "MIT",
    "attribution": "Data contributors",
    "notes": "Incomplete, unverified example; explain actual evidence here."
  },
  "points": [{"id": "my-map-01", "name": "Secret room 01", "x": 0.25, "y": 0.5}]
}
```

Map and point ids use lowercase letters, digits, `_` or `-`, start with a letter/digit and contain at most 64 characters. Map ids must be unique across files; point ids must be unique within their map. Use English default names. Coordinates are finite numbers in `[0,1]`, relative to the **entire** map with top-left origin: x increases rightward, y downward. Do not normalize a zoomed viewport as the full map. `size_m` is an approximate map-side distance scale, not image-pixel dimensions. There are at most 5,000 points per map, 32 maps per feed and 2,000,000 encoded UTF-8 bytes in the whole feed. Duplicate JSON keys, non-finite values, unsafe ids and missing credits fail publication.

The currently bundled data is only **15 Erangel and 12 Taego points**. Both sets remain unverified; Taego is explicitly incomplete. Additional map data needs a matching user-supplied local image reference before LootLizard can recognize that map. Point data alone never creates image recognition.

## Validate locally

From the repository root, after setting up Python as in [README.md](README.md):

```powershell
.\.venv\Scripts\python.exe scripts/build_map_catalog.py --revision (git rev-parse HEAD) --output "$env:TEMP/lootlizard-maps.json"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The builder needs a full lowercase 40-character commit SHA and uses the same feed parser as the updater, plus publication source/license checks. This local command is a validation preview; do not publish uncommitted edits under an old revision. Every changed published snapshot must have a new validated main commit revision. The generated feed has exactly three top-level fields:

```json
{"schema_version": 1, "revision": "0123456789abcdef0123456789abcdef01234567", "maps": []}
```

The illustrative revision above is not a real publication. The shortened example is an empty snapshot; a populated feed contains complete point-data objects like the input example in `maps`. An empty list is a valid complete removal snapshot. The builder validates/encodes the whole feed before atomically replacing its output file.

## What happens after merge?

The read-only **Check** workflow validates every point file and runs tests for main pushes and PRs. The separate **Publish map metadata** workflow runs only for relevant main changes or manual dispatch on main. Its serialized write-enabled job checks out the newest main, validates it, uses that exact checkout commit as the feed revision and pushes a single complete `maps.json` commit to `metadata`. Pull-request code never runs with that publisher's write token. A non-fast-forward remote update fails rather than force-overwriting history.

The public feed is <https://raw.githubusercontent.com/molnard-labs/LootLizard/metadata/maps.json>. Running clients normally check on startup and about every 60 seconds. Workflow queues, raw-content CDN caching, offline conditions and retry delays mean delivery is eventual. Bad/incomplete downloads leave the previous valid cache in use. Explicit local point imports override community entries with the same id.

A **data-only PR** can reach existing clients through this feed without a new executable. An **application/code change** needs normal review, tests and a new tagged binary release; the data updater never downloads or executes application code. Check [Actions](https://github.com/molnard-labs/LootLizard/actions) for actual CI results; a local test run is separate evidence.

## Application releases and installer updates

Version **0.8.1** uses the per-user [LootLizard-Setup.exe](https://github.com/molnard-labs/LootLizard/releases/latest/download/LootLizard-Setup.exe) as the primary Windows download. The installed files live under `%LOCALAPPDATA%\SmartLizardOrg.LootLizard\current`; `%LOCALAPPDATA%\LootLizard` contains user settings, profiles and map cache and is retained on uninstall. Existing ZIP/source users need a one-time installer run for application self-updates. Portable ZIPs remain a manual-update option.

Application updates use stable releases of this repository, independently of `metadata/maps.json`. The installed app checks at startup and every six hours and stages a verified higher-version full package through Velopack. A ready package is applied only after ordinary Close, or explicit **Restart to update**; current background work must finish first. Disabling **Automatic app updates** disables scheduled checks and normal-exit apply. Manual checking/downloading and explicit restart remain available. Never introduce an update-triggered close during gameplay, a downgrade, a channel switch, or image upload.

Build with matching **`velopack==1.2.161`** and **.NET `vpk` 1.2.161**. [scripts/build_installer.py](scripts/build_installer.py) consumes the enriched payload from `package_release.py`, validates the full package/feed and produces the stable installer alias; it does not install or publish. Source, tests, data and dependency notices accompany the installer/full update package. The tagged release pipeline publishes these with the optional ZIP and SHA-256 checksums. Windows binaries are currently unsigned; checksum verification is not independent publisher authentication. Repository/release maintainers and their publishing credentials are part of the application-update trust boundary.

Installer CI uses an isolated synthetic `0.7.99` package fixture to exercise install → check/download `0.8.1` → retained pending package → apply-on-exit → uninstall, checking that synthetic user data survives. The older fixture uses the current payload with an older install manifest; it is not a previously published application binary. `--update-probe` is a headless test hook, not a supported alternative update source. Its runner-environment/path checks prevent accidental normal use; environment variables are not proof of trusted CI or an authorization boundary against a local caller. Normal application updates use the fixed public GitHub repository.

Report actual [Actions](https://github.com/molnard-labs/LootLizard/actions) results separately from local mocked tests. Headless installer success cannot establish GUI focus behavior, real-game capture/recognition, SmartScreen behavior on another PC, or all worker-shutdown races. Test ordinary Close, explicit restart, automatic-update opt-out and an update download still running at Close. Keep synthetic CI files out of real user directories and retain the package id, channel, version and checksum validation.
