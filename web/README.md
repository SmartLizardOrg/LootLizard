# LootLizard browser application

The browser application lives in `web/app/`; the landing page is in
`web/landing/`. Visitors open `/` and launch the companion at `/app/`.
Recognition runs on the visitor's computer in a dedicated worker using Pyodide
314.0.7, Python OpenCV, NumPy and Pillow. There is no image-upload endpoint.

## Build and preview

The static build needs Python 3.12 or newer and no installed CV dependencies:

```sh
python scripts/build_web.py
python scripts/serve_web.py --port 8766
```

Open `http://127.0.0.1:8766/`. The server serves only the curated `dist/` output,
not the checkout. It refuses directory listings, uploads and escaping links.
The published package contains the landing, app, seven Python CV source files,
point JSON, notices and hosting metadata. Runtime packages and public reference
PNGs are downloaded by the client rather than bundled.

For development tests, install the Python project dependencies and run:

```sh
python -m pip install -e .
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s web/tests -p 'test_*.py' -v
node --test web/tests/*.test.mjs
```

The browser smoke test is restricted to hosted GitHub Actions. It exercises the
real WASM engine, automatic public references, synthetic map/gameplay/map
transitions, projection, stale-reply rejection, diagnostic mode changes and
ended-stream clearing. Its loopback `?test=1` hook accepts generated canvas
streams; it never bypasses screen-sharing consent. Local browser review uses
the approved visible browser tooling instead of bypassing the CI guard.

## Player flow

Use a desktop browser that supports `getDisplayMedia`; desktop Chrome/Edge are
the initial target. This is a browser architecture, not evidence of tested
capture on every operating system, browser or console. A console/mobile game
would need its image made available to the browser separately.

1. Open the companion on the second monitor and wait for the local engine and
   default Erangel/Taego map images to load.
2. Select **Start sharing** and choose the PUBG window or its monitor.
3. Return focus to PUBG and open its full map. Periodic local scans update the
   companion without another browser click or a global hotkey.
4. Stop sharing from the page or browser when finished.

Sharing requires a user gesture and fresh source selection for each new
session. HTTPS (or loopback development) is required. The page cannot persist
capture permission, silently choose a source or register another foreground
application's Windows global hotkey. Hidden/minimized tabs may be throttled;
keep the companion visible on the second monitor.

The default UI is English; **Setup & preferences > Language > Magyar** enables
Hungarian. **Replay or spectating** disables player estimation. Marker appearance
is not verified own-player identity; unknown or ambiguous images withhold
geometry. Points remain community observations, with an incomplete Taego list.

## Automatic reference images and local overrides

`automatic-references.mjs` lists reviewed official PUBG developer map images at
a pinned public commit. The client verifies PNG type, size and SHA-256, then
uses the images locally. No user download/import step is required for Erangel
or Taego. Each map can fail independently; the app remains usable for the demo
and local images if the reference host is unavailable.

These historical assets can differ from the current game. **Map images** under
Setup accepts an optional complete, square custom image. A custom image overrides
its map's default. **Use default images** removes saved custom references and
retries the reviewed defaults. Image rights remain with their owners; see
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

Private captures and custom references stay on this device. Optional custom
references use IndexedDB; preferences and coordinate snapshots use localStorage.
Automatic references use the browser's ordinary public HTTP cache. Disabling
local remembering clears the saved custom references/preferences/catalog for
this origin. Browser-managed storage can be cleared or evicted.

The public coordinate feed remains separate:
`https://raw.githubusercontent.com/molnard-labs/LootLizard/metadata/maps.json`.
Startup and roughly 60-second checks validate whole snapshots and preserve the
last valid data on failure. A coordinate PR does not add an unreviewed image URL
or execute application code.

## Performance diagnostics

Capture requests 1 FPS and at most 2400 pixels per side; sampled frames are
bounded to four million pixels. The default recognition interval is three
seconds after the previous operation finishes. Browser constraints describe the
output track and do not guarantee the internal capture/GPU work or a particular
PUBG FPS cost.

The sampler reuses bitmap dimensions. Owned capture ImageData is retained
directly, with a separate copy only for a worker request. Status-only changes
do not rewrite the same snapshot. An empty reference library updates the preview
and abstains before worker transfer; the Python adapter also avoids PIL/RGB
conversion for valid no-reference inputs. This path is not map recognition.

On loopback only, add `?diagnostics=1` and expand Setup. Temporary controls switch
1/3 FPS on the existing track and select capture-only, preview-only or normal
processing. Mode changes clear old geometry. Reported settings and constraint
failures remain visible. Downloaded timings contain at most 128 local events,
image dimensions and stage durations, never pixels, labels or device IDs.

`captureMs` measures canvas sampling. `totalMs` measures the subsequent controller
operation, excluding capture. Worker round trip includes conversion and queueing;
Python's nested timings cover Python stages only. Track frameRate is a reported
setting, not a delivery-rate measurement. No continuous OS focus or GPU queue
trace is collected. Synthetic tests establish functionality; fresh controlled
game measurements are needed for performance claims with full recognition.

## Publishing and updates

Source changes merge into `main`. Publish an alpha release such as
`v0.9.0-web.1` from a tested main commit. The trusted **Publish web release**
workflow validates the tag, runs checks, attaches the static ZIP and checksum,
and commits the exact public build to `web-release` without force-pushing.
An older web release cannot replace a newer production build.

Cloudflare Pages connects to `molnard-labs/LootLizard` with production branch
`web-release`, framework **None**, no build command and output directory `/`.
The generated branch already contains the deployable files. Therefore a source
merge alone does not update the public application; a published web release does.
Application files revalidate on new page loads. An already open sharing session
keeps its running code until the player reloads; it is never forcibly reloaded
mid-game. Reloading ends capture and requires a new sharing selection.
