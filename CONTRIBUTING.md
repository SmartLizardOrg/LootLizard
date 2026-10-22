# Contributing to LootLizard

LootLizard is a browser application with portable Python CV modules. Open a
focused pull request against `main`. The earlier Windows application remains
available in the `v0.8.0` tag; new changes should target the web application.

## Local setup

```sh
python -m venv .venv
# Activate .venv using your shell's normal activation command.
python -m pip install .
python scripts/build_web.py
python scripts/serve_web.py --port 8765
```

The landing page is `/`, the companion is `/app/`. Browser packages and public
references are downloaded on the first visit; the Python installation above is
for developer tests, not an end-user requirement. Do not deploy the whole source
checkout: `scripts/build_web.py` creates the curated `dist/` directory.

## Checks

```sh
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s web/tests -p 'test_*.py' -v
node --test web/tests/*.test.mjs
python scripts/build_web.py
```

GitHub Actions also exercises the real Pyodide/OpenCV worker in Chromium using
synthetic artwork. The browser test must preserve its CI-only guard and use no
private screenshots, user profiles or real sharing permissions. Local visual
checks should use an explicitly selected, visible browser.

For recognition work, test unknown and ambiguous frames, stale asynchronous
replies, Stop/sharing interruption and reference replacement. Successful
synthetic registration is separate from general PUBG accuracy. A performance
change needs controlled frame-time measurement; a passing functional test does
not demonstrate an FPS improvement.

## Community point data

Edit the relevant file under `data/`. Positions are whole-map normalized values:
the upper-left corner is `(0, 0)` and the lower-right corner is `(1, 1)`.
Coordinates must describe the complete map, not a zoomed or panned screenshot.
Both current maps use an approximate `size_m` of 8000 for straight-line distances.

- Use stable, lowercase, safe ids for maps and points. Retain ids for corrections
  to an existing location so that updates can be reviewed clearly.
- Include a precise source URL, license and attribution. Describe uncertainty,
  map version and incompleteness in the source notes.
- Keep existing credits and indicate which points were added, moved or removed.
  Do not label a list complete without evidence. The Taego list is incomplete.
- Do not include screenshots, game map images, private catalogs or profiles in a
  coordinate PR. A code license does not establish rights to an image.

Run catalog validation using the full source commit:

```sh
python scripts/build_map_catalog.py --revision FULL_40_CHARACTER_COMMIT_SHA --output work/maps.json
```

The metadata workflow builds one validated snapshot after relevant changes reach
`main` and publishes it to `metadata/maps.json`. Open clients poll that fixed
public GitHub feed roughly every 60 seconds. CDN caching and failures can delay
updates; rejected snapshots retain the last good data. This channel publishes
point metadata only, not executable application code.

## Map references and private fixtures

Public reference-source configuration belongs to the browser application. Keep
its source provenance, byte/dimension bounds, version pins and validation intact.
Never substitute an arbitrary screenshot for a complete square map reference.
User-supplied references are optional local data; do not upload them in tests or
bug reports without deliberately reviewing the content and distribution rights.

The portable `lootlizard/dataset.py` utilities and
`scripts/evaluate_screenshots.py` can evaluate local annotated datasets. Ground
truth must be manually established; unknown facts remain null. Keep training
references separate from held-out evaluation captures, and report both sample
counts and abstentions. The repository does not contain the private real-game
evaluation set. Synthetic fixtures should be generated programmatically.

## Public builds and releases

The builder copies `web/landing/` to the site root and `web/app/` to `/app/`, plus
an explicit list of seven Python modules to `/cv/`, two point JSON files and
required notices. Public directories must contain only intended static assets;
unexpected file types, source links, oversized assets and unsafe paths fail the
build. Existing output may be replaced only when its prior build manifest is
valid and no untracked files are present.

Source changes do not automatically publish the production app. After all checks
pass and the source is merged to `main`, create a matching prerelease tag such
as `v0.9.0-web.1` and publish its GitHub Release. The release workflow validates
the tag and its ancestry, builds/tests the exact commit, attaches the ZIP and
SHA-256 file, and updates `web-release`. Cloudflare Pages serves that generated
branch with no build command and the repository root as its output directory.
The workflow keeps branch history and rejects an older release replacing a
newer production build. It never updates the legacy Windows feed.

Keep application versions in `pyproject.toml` and `lootlizard/__init__.py` aligned.
Use a new `-web.NUMBER` suffix for each web alpha release of that version.
Navigation/reload revalidates application assets; open sessions retain their
loaded code. Publishing must not force a reload or silently restart screen
capture. Keep preferences optional and provide a way to clear stored data.

## Licensing

Submit code under the repository's MIT license. Preserve attribution and update
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) when adding a dependency, public
reference source or adapted dataset. PUBG assets and trademarks keep their
owners' rights; do not present this project as officially approved.
