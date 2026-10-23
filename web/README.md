# LootLizard browser application

`web/landing/` provides `/`; `web/app/` provides `/app/`. The site contains its own
map catalog and public reference PNGs. Manual mode displays these assets without
a capture stream or recognition worker. Explicitly selecting automatic mode
starts the client-side Pyodide/OpenCV worker. There is no backend, screenshot
upload, account or live metadata service.

## Build and preview

Python 3.12+ standard library is enough to build:

```sh
python scripts/build_web.py
python scripts/serve_web.py --port 8766
```

Open `http://127.0.0.1:8766/`. The loopback server exposes only the curated `dist/`
site, refuses listings/escaping links/uploads, and never serves private captures.
Map PNGs and `data/maps.json` are same-origin release assets. Automatic mode's
first initialization needs Internet for the pinned browser runtime and optional OCR.

For tests:

```sh
python -m pip install -e .
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s web/tests -p 'test_*.py' -v
node --test web/tests/*.test.mjs
```

`browser-smoke.cjs` remains CI-only. It runs real WASM CV on original synthetic
fixtures and exercises worker-free manual map selection, map reset/navigation,
exclusive mode switching, the automatic map library, map persistence, projection,
late-reply rejection, Stop and positive-context reset. Its loopback test hook
never bypasses a real browser's sharing permission. Local visual review uses an
explicitly selected visible browser.

## Release map catalog and references

`data/*.json` contains eleven normalized map records. Nine have community location
data: Erangel, Taego, Miramar, Deston, Rondo, Vikendi, Paramo, Karakin and Haven. Taego
contains 15 source-listed secret rooms. Depending on the map, markers identify
secret rooms, security rooms, bear cave entrances, tunnel entrances or possible
Pillar cache buildings. These source-based lists have
not been independently verified in game for this project and may be incomplete
or outdated. Their presence does not establish recognition accuracy.

Erangel additionally has seven historical community-listed bunker entrances,
including four at Shelter, with factual provenance in
`data-sources/erangel-bunker-entrances.json`. Miramar's three Los Leones underground
entrances are separate from its 15 secret rooms. Both use `tunnel_entrance`, like
Karakin's existing 22 entrances, with the shared green symbol and unchanged
coordinate anchors. Multiple entrances can lead into one underground space;
existing room positions are not reclassified as exact doors.

Empty `points: []` is valid and means no POI coordinates are supplied; this applies
to Sanhok and Training. It is not evidence that no secret locations exist.
Paramo's landmarks can change between matches. Check its locations against the
current in-game map.

Haven's 22 `supply_cache` markers are possible building centres transcribed from a
historical community guide. Only some caches are active each match. The list needs
current-game verification; it does not identify 22 guaranteed active rooms. The app
shows that caveat whenever Haven markers are displayed.

`location-markers.mjs` shares five vector symbols between the map, sidebar and
present-types-only legend. Optional point `kind` values are `secret_room` (legacy
default), `security_room`, `bear_cave`, `tunnel_entrance` and `supply_cache`; other values fail
catalog validation. Map coordinates remain fixed while constant CSS-pixel badges
are placed around them. Badges avoid other badges and anchors, use bounded leader
lines, and can omit numbers or disappear when no free space remains. Exact small
anchors are drawn last. No remote marker images are loaded.

`scripts/build_map_catalog.py` validates safe ids, normalized points, attribution,
size/count limits and duplicate identities using only the standard library/pure
model. `scripts/build_web.py` embeds its complete output as `/data/maps.json`, plus
the individual JSON records. A release catalog uses the source commit as revision;
a local preview uses `content:<sha256>` derived deterministically from its maps.
No external snapshot can replace this catalog during a running session.

`automatic-references.mjs` exports `AUTOMATIC_REFERENCES`, `fetchReference`, and
`loadAutomaticReferences`. URLs resolve under the module's own `/app/map-assets/`
directory; there are no runtime GitHub/CDN map-image requests. Each file is bounded
to 2 MB and checked for PNG type/signature and the pinned SHA-256 before decoding.
The source manifest records original public URLs, byte counts and 819×819 dimensions.

The library contains Erangel, Miramar, Sanhok, Vikendi, Karakin, Paramo, Haven,
Taego, Deston, Rondo and Training/Camp Jackal. Duplicate Training aliases are not
loaded twice. Rondo uses the official no-text PNG because the named upstream
`Main_Low_Res.png` contains JPEG bytes. The full library totals 14,079,121 bytes;
decoded images, descriptors and runtime memory add to that download size.

All assets are unchanged public files from official `pubg/api-assets` commit
`32b13b51128b8d8909ae5e77f3b833e01230b24d` (2024-10-28), still its latest master
when checked on 2026-10-22. This is historical reference coverage, not proof that
every map is in the current rotation or matches the current game. Paramo's landmarks
can change between matches. PUBG imagery is not covered by the project's code
license; retain the manifest, `map-assets/NOTICE.txt` and root third-party notices.

The builder verifies image hash/size/PNG dimensions, official pinned source URLs,
exact manifest/file correspondence and catalog/reference ids before writing output.
It rejects an unlisted image in the map-assets directory. Private screenshots,
custom references and evaluation profiles never enter the public build.

## Manual and automatic modes

Every page load starts in manual mode. The central picker offers eleven named
map-preview tiles backed by the same bundled map manifest as recognition. Choosing
a tile loads that complete map with its static points into the shared zoom/pan
viewer. Empty point lists remain valid: Sanhok and Training still show their maps.
**Reset map** clears the selection and returns to the picker.

Manual mode does not create the vision worker, initialize CV/OCR, schedule scans
or request `getDisplayMedia`. A stale map-image load cannot replace a later
selection, reset picker or automatic view. The image hashes and local map catalog
validation remain in effect. Language is available in both modes.

Selecting **Automatic recognition** initializes the bundled references and local CV
worker, then offers the normal connection flow. Sharing controls, match reset,
recognition status, retained-map age and scan settings appear only in this mode.
Selecting manual mode stops the capture track, invalidates pending work and
disposes the automatic worker. Selecting automatic mode clears the manual map.
At most one map source owns the viewer, and old asynchronous replies cannot
restore the previous mode's map.

## Automatic capture, persistence and scan cadence

Use desktop Chrome/Edge on a second monitor. Start PUBG, connect its window or
monitor through the browser picker, then return to the game and open its full map.
Screen sharing needs HTTPS or loopback and fresh user source selection each time.
Hidden tabs can be throttled. Browser portability does not establish tested capture
on every OS or a console/mobile integration.

The small source preview is at most 240×135 and updates only when sampled. The main
canvas uses the registered map crop and matching frame, with its last-update age.
Ordinary gameplay, inventory, unknown frames and temporary
capture pauses retain that paired map; they never draw old geometry onto gameplay.
Opening a recognized map refreshes that held map. After the first successful screen
recognition, the small game preview collapses automatically and can be reopened.
The prominent Reset match button remains available outside the collapsed preview.

### Map navigation

Scroll over the selected or recognized map to zoom toward the pointer from 100% fitted size
to 800% (8×), then drag to pan. The **+ / −** toolbar buttons zoom around the
centre; **Fit map** restores the whole map. With the map focused, arrow keys pan,
**+ / −** zoom and **0** fits the map. Icons and coordinate anchors retain their
CSS-pixel size as the map enlarges, so they remain readable in dense areas.
Magnification remains limited by the source map image's resolution.

`map-canvas.mjs` owns the cropped saved bitmap and redraws it with the view from
`map-navigation.mjs`. Pointer and keyboard navigation do not capture another
frame or invoke CV; an enabled automatic capture schedule continues separately. A fresh
capture of the same map retains the zoom and normalized focus. A confirmed new
match/reset, changed map, manual Reset map or Stop clears the view and starts fitted again.

The first verified map locks recognition to that map for the current match.
Subsequent frames search its cached reference instead of comparing eleven maps.
Confirmed lobby/results, Reset match, or Stop clears the lock; the next match again
searches all eleven. If an end transition is missed, use Reset match before a new
match, including another match on the same map. The manual picker belongs to the
separate manual mode and does not restrict automatic identification.

Intervals are 500/1000/2000/5000/10000 ms, with 1000 ms the default. Language and
interval persist through the browser preference store. Capture requests
`1000 / intervalMs` FPS and at most 2400 pixels per side; samples are at most four
million pixels. Scheduling is start-to-start with one scan in flight: the next
delay is `max(0, intervalMs - elapsedSinceScanStart)`. Effective spacing is therefore
at least `max(processingTime, requestedInterval)`, subject to browser scheduling.
Long work never queues frames. Initial all-map matching can take seconds. Reused
canvases, retained owned buffers and unchanged-view checks avoid unnecessary copies.

The player application submits the explicit `map-only` context. It runs map
registration and room-point projection; player-marker/view-cone and safe-zone
processing are skipped. Portable marker/zone algorithms remain in developer CV
modules and tests, but are disabled in this player interface. There is no game
memory, packet, telemetry or hidden-position source.

## Conservative context reset

A footer descriptor learned only after a verified map is session memory. Only
its stable left prefix is compared; changing suffix pixels cannot identify a
new match. Positive support can skip OCR. Missing/different footer pixels, an
absent map and elapsed time never alone clear a match.

The fallback loads pinned Tesseract.js/core 7.0.0 and a SHA-256-verified English
model. Startup is asynchronous. Recognition is serial with CV, normally at most
every 12 seconds and every six seconds while confirming menu evidence. Five
bounded crops cover 770,000 pixels. Three consistent positive observations over
at least six seconds are required. A carefully restricted dark-navigation path
uses exact ordered menu tokens, layout and stronger separate action/mode cues;
it does not lower confidence for arbitrary OCR text. Pause and inventory cues veto
reset. Other languages, changed menus and ambiguous OCR can retain the map.

Context words, names and footer descriptors are never persisted/logged/exported.
Closing the captured game window normally ends its stream; a monitor stream does
not reveal whether PUBG exited or the user briefly switched applications.

## Diagnostics and limitations

Developer processing controls and timing access exist only behind the loopback
`?test=1` hook used by synthetic tests; they are not player settings. Test-mode
changes invalidate old guidance. Timing records contain at most 128
dimension/duration/status events, never pixels, labels, words or device ids.
Track settings report negotiated output, not delivery frequency, physical GPU work
or guaranteed FPS impact. Synthetic/native CV timings are not game FPS benchmarks.

The optimized full pipeline has not been established as negligible overhead.
Control game scene, focus, capture source, sharing bar and map visibility when
comparing frame times. Keep runtime/reference initialization outside steady-state
measurements, then separately report their cold cost.

## Publish and update

Merge reviewed source to main and publish a tested `v0.9.0-web.NUMBER` prerelease.
The release workflow validates ancestry, runs checks, packages the exact build,
attaches its ZIP/checksum and updates `web-release` without rewriting its history.
Older release tags cannot replace newer production. Cloudflare Pages uses this
branch with framework None, no build command and root `/` output.

Code, maps and coordinates ship together. There is no metadata publishing workflow,
GitHub polling, custom-reference import or separate update channel. Navigation/reload
revalidates the website, while an open sharing session keeps its running release
until the user reloads. Reloading ends capture and needs a new source selection.
