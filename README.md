# LootLizard

A browser companion that keeps the PUBG map and community room markers on your
second monitor. Open the website, connect the game window, then return to PUBG.
Map recognition and point projection run on your computer.

**Web alpha · 0.9.0.** English by default; Hungarian is available. No desktop
installation, account, API key, manual reference download or global hotkey.

[Open LootLizard](https://lootlizard.pages.dev/app/) ·
[Landing page](https://lootlizard.pages.dev/) · [Magyar](README.hu.md) ·
[Contributing](CONTRIBUTING.md) · [Releases](https://github.com/molnard-labs/LootLizard/releases)

## Use the companion

1. Open the site in desktop Chrome or Edge on your second monitor. Wait for the
   local recognition engine and bundled map images to load.
2. Select **Connect PUBG window**, choose the game window or its monitor in the
   browser picker, then return focus to PUBG.
3. Open the complete in-game map. LootLizard identifies it automatically and shows
   the map with available room markers. No per-scan browser click is needed; the
   app does not press PUBG's map key for you. After the first recognition, the
   game preview collapses automatically and can be reopened when needed.
4. Keep playing. The last recognized map remains visible through gameplay,
   inventory and temporary capture pauses. Reopen PUBG's map to refresh the held
   image; its last-update age remains visible.
5. The prominent **Reset match** button clears the held map while keeping sharing active. **Stop**,
   browser Stop sharing, or closing the page ends capture and clears the view.

Gameplay appears only in a small sampled source preview. The main view contains
recognized map pixels, never old geometry placed over a newer gameplay frame.
Positive English lobby/results evidence must repeat before automatic reset.
Other languages and unfamiliar menus can remain uncertain; use **Reset match**
when needed. A whole-monitor stream cannot reliably distinguish exiting PUBG
from briefly switching to the desktop.

## Inspect the map

Scroll over the recognized map to zoom toward the pointer, from **100% (fit)** to
**800% (8×)**. Drag the map to move around a crowded area, such as Deston. The
**+** and **−** buttons zoom around the centre; **Fit map** shows the complete map
again. Focus the map with Tab or click it to use arrow keys for movement,
**+ / −** for zoom and **0** to fit.

Location icons keep their screen size while the map enlarges, and their small
centre points continue to mark the exact coordinates. New captures of the same
map preserve your zoom and focus. A new match, **Reset match** or stopping sharing
restores the fitted view. Moving or zooming redraws the saved map without an
extra screenshot or recognition pass; normal map checks continue independently.
Zoom cannot reveal image detail beyond the captured map's resolution.

## Bundled maps and coordinates

The release includes **11 official developer map references**: Erangel, Miramar,
Sanhok, Vikendi, Karakin, Paramo, Haven, Taego, Deston, Rondo and Training
(Camp Jackal). Training/Camp Jackal aliases share one reference. Map availability
in PUBG depends on mode and rotation. These pinned historical assets do not
establish current matchmaking availability or recognition accuracy.

Images and the complete local map catalog ship with the website. Users do not
need to find or import map images, and the app does not poll GitHub metadata or
fetch map PNGs from an external image host. The reference package is about
**14.1 MB** before ordinary HTTP caching; decoded images and feature caches use
additional memory. PNG sizes and SHA-256 are checked before use.

Community location coordinates are bundled for **nine maps**: Erangel, Taego,
Miramar, Deston, Rondo, Vikendi, Paramo, Karakin and Haven. The data covers secret rooms,
security rooms, bear cave entrances, tunnel entrances and possible supply-cache
buildings, depending on the map. Taego includes
15 source-listed secret rooms. Imported community coordinates have not been
independently verified in game for this project; neither the counts nor the lists
establish complete coverage of the current game. Verify locations and entrances.

Underground entrances have their own green tunnel symbol. Erangel includes seven
separately sourced bunker entrances (four at Shelter); Miramar includes three
entrances at the Los Leones underground complex alongside its 15 secret rooms.
Karakin retains its 22 tunnel entrances. Multiple entrances can lead to the same
underground space; these counts do not mean additional key-locked rooms. Existing
room markers are not relabelled as precise entrances. Entrance positions are
community observations and have not been checked in the current game for LootLizard.

Paramo's landmarks can change between matches; check its locations against the
current in-game map. Haven's 22 markers identify possible Pillar cache building
centres transcribed from a historical community guide; only some buildings are
active each match, and this list needs checking. They are not 22 guaranteed rooms.
Sanhok and
Training retain empty point lists because no supported coordinates are bundled;
an empty list does not mean no secret locations exist.

Door, lock, cave, tunnel and supply-crate symbols distinguish location types on the
map and in the list. Small center points mark the coordinates; offset badges use
short leader lines. In crowded areas, badges move into free space or leave the
anchor visible without a number. The legend shows only types present on the map.

The current match stays associated with its first verified map until a confirmed
match end, **Reset match**, or sharing interruption. Subsequent scans check that
map rather than repeatedly comparing all eleven references. Initial recognition
searches the complete library. **Reset match** before a new match if its transition
was missed, including when the next match uses the same map.

The player app performs map registration and room projection only. Player-position,
view-cone and safe-circle detection do not run in this interface. Changed artwork,
extreme zoom and occlusion can prevent map recognition.

## Platforms and performance

The app has no Windows-specific native component. Desktop Chrome and Edge are
the initial target; capture and background scheduling depend on browser, OS and
source. Other platforms require validation. This does not make the PUBG game
itself available on another OS; console/mobile image capture is not integrated.
Keep LootLizard visible on the second monitor because hidden tabs can be throttled.

Choose a map-check interval of **0.5, 1, 2, 5 or 10 seconds**; **1 second** is the
default. Language and interval are saved in this browser. Capture requests follow
that selection: `FPS = 1000 / intervalMs`, with at most 2400 pixels per side/four
million sampled pixels. Recognition is serial and scheduled start-to-start:
effective spacing is at least the greater of processing time and the requested
interval. Slow work never queues screenshots. Initial all-map matching can take
several seconds. Known-map matching, reused canvases and unchanged-view checks
reduce repeated work.

There is no FPS guarantee. Earlier 3 FPS sharing measurements on one PC showed
small mean-FPS changes and larger slow-frame effects. The current optimized path,
including bundled references and optional OCR, needs controlled in-game frame-time
measurement. Functional tests do not establish an insignificant performance cost.

## Privacy and updates

There is no image-upload endpoint, account, telemetry or AI service. Screen pixels,
map results and local OCR remain in memory. Preferences can use localStorage;
there is no custom-reference import/storage flow or runtime coordinate-feed cache.
The website serves its app, map catalog and reference images. Initial runtime and
optional English OCR packages are fetched from pinned public CDN URLs and execute
locally; those hosts see normal asset requests, never recognition screenshots.

A learned bottom-right footer provides positive continued-play evidence and can
skip OCR. Its changing suffix is ignored. A missing/changed footer or missing map
never alone resets a match. Lazy OCR runs serially with map CV and normally no
more than once per 12 seconds, with faster confirmation of positive menu evidence.
Startup happens in the background. Names, OCR words and footer descriptors are
not logged, exported or persisted. See [web/README.md](web/README.md).

**Code, maps and point data update together through GitHub Releases.** After a
reviewed change reaches `main`, publishing `v0.9.0-web.NUMBER` builds and tests the
release, attaches its static ZIP/checksum, and updates the generated `web-release`
branch. Cloudflare Pages serves that branch. There is no separate metadata branch
publisher or open-session data polling. Navigation/reload loads the new release;
an existing sharing session is never forcibly reloaded mid-match. Reloading
requires selecting the sharing source again.

## Develop and publish

The static build uses Python 3.12+ and its standard library:

```sh
python scripts/build_web.py
python scripts/serve_web.py --port 8765
```

Open `http://127.0.0.1:8765/`; the app is `/app/`. The loopback GET/HEAD-only server
serves curated `dist/`, with no uploads or source-checkout directory listing.
The first browser runtime/OCR load still needs Internet access.

For developer CV and browser contract checks:

```sh
python -m pip install .
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s web/tests -p 'test_*.py' -v
node --test web/tests/*.test.mjs
```

The hosted browser smoke test uses real Pyodide/OpenCV with synthetic frames;
private captures are never part of CI or public artifacts. The builder validates
all local map records, bundled image hashes/dimensions and the exact public asset
allowlist before replacing a previous build.

For Cloudflare Pages Git integration: production branch `web-release`, framework
None, empty build command, output directory `/`. The branch already contains the
curated site. A source merge alone does not publish production. `build-info.json`
records version, source commit, release tag and every public asset hash. Local
preview catalogs use a deterministic content revision when no commit is supplied.

## License and attribution

Project code is [MIT](LICENSE). Bundled PUBG artwork retains its owners' rights
and is not MIT licensed. Sources, hashes, publisher terms and coordinate credits
are preserved in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the bundled
map manifest/notice. LootLizard is an independent community project; image-based
operation does not establish official approval or anti-cheat compatibility.
No private capture, user reference, profile or local evaluation catalog is shipped.
The earlier Windows application remains in Git history and the `v0.8.0` tag.
