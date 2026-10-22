# Contributing to LootLizard

Open a focused pull request against `main`. Current development targets the
browser companion; the former Windows app remains in `v0.8.0` history.

## Develop and check

```sh
python -m venv .venv
# Activate using your shell's normal command.
python -m pip install .
python scripts/build_web.py
python scripts/serve_web.py --port 8765
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s web/tests -p 'test_*.py' -v
node --test web/tests/*.test.mjs
```

The app is `/app/`, landing `/`. Build and serve only curated `dist/`, never the
entire source checkout. End users need no Python installation or image import.
The hosted browser test uses synthetic frames and real WASM CV; keep its CI-only
guard and never add private screenshots/profiles or real sharing permission bypasses.
Local visual tests use an explicitly selected visible browser.

Recognition changes must test abstention, ambiguity, Stop, stale replies, reference
transactions and held-map pairing/ages. Successful synthetic recognition does not
establish real match accuracy. Performance claims need controlled game frame times.

## Map records and points

Edit the relevant `data/<id>.json`. Coordinates are normalized across the complete
map: `(0,0)` top-left, x right/east, y down/south, `(1,1)` bottom-right. `size_m` is
an approximate nominal side length for straight-line distance, not a route length.
Use stable lowercase safe map/point ids. Retain existing ids when correcting points.

Empty `points: []` is valid and means no coordinates are supplied. Do not manufacture
points or imply a zero-length list proves no secret rooms exist. Erangel has 15
unverified points; Taego has 12 and is incomplete. New point records need a precise
source URL, attribution, license, version and uncertainty notes. Preserve credits.

Validate a complete local catalog:

```sh
python scripts/build_map_catalog.py --output work/maps.json
```

A supplied `--revision FULL_40_CHARACTER_COMMIT_SHA` labels a release; otherwise the
catalog receives a deterministic content hash. The web builder includes this catalog
in the static site. Maps and coordinates update only with a web release; there is no
GitHub metadata polling, metadata branch publisher or independent data rollout.

## Official bundled references

`web/app/map-assets/manifest.json` records the selected public official asset URL,
source commit, byte count, dimensions and SHA-256 for every bundled PNG. The runtime
manifest in `automatic-references.mjs` must agree. Add/update only reviewed public
sources and preserve their rights; do not substitute a private capture or an arbitrary
map image. Keep `NOTICE.txt` and `THIRD_PARTY_NOTICES.md` accurate. PUBG imagery is not
MIT licensed. A source code license never licenses someone else's game imagery.

All eleven references are automatic; there is no manual map selector/import flow.
Do not add duplicate aliases with identical reference pixels (Training/Camp Jackal
is one map), which would make unique identification ambiguous. Initial matching
searches the library, then a verified map stays locked until the match is reset.
Measure both initial search cost and the subsequent known-map path.

Never bundle private screenshots, local catalogs, personal profiles, account names
or user-provided references. The local dataset/evaluation utilities may read private
files, but test ground truth must be independently annotated and remain local.
Report sample counts and abstentions; synthetic fixtures should be generated.

## Public build and release

The builder copies landing/app assets, exactly seven portable CV modules, validated
map records and their complete catalog, eleven reviewed public reference PNGs, notices
and hosting files. Hash/size/dimension/source checks run before replacing output.
Unlisted files in the map asset directory, unsafe paths, symlinks, invalid catalogs
and oversized inputs fail the build. Existing output needs its valid prior build
manifest and no untracked files before replacement.

Merge reviewed tested source to `main`, then publish a matching prerelease such as
`v0.9.0-web.4`. The release workflow checks tag ancestry, runs tests, builds the exact
source, attaches ZIP/SHA-256 assets and updates `web-release` without rewriting history.
Cloudflare Pages serves that generated branch with no build command and `/` output.
A source merge alone never publishes production. An older release cannot overwrite
a newer web build. No Windows update feed is changed.

Keep versions in `pyproject.toml` and `lootlizard/__init__.py` aligned. Each alpha
uses a new `-web.NUMBER`. Reload/navigation receives a new app/maps/data release;
open sharing sessions are not forcibly interrupted and must reselect their source
when the user reloads. See README and third-party notices before changing hosting,
public assets or dependencies.
