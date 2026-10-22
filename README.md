# LootLizard 0.8.1 — Legacy desktop edition

[Magyar gyorsindító](README.hu.md)

An experimental, open-source Windows companion by [molnard-labs](https://github.com/molnard-labs) that projects known PUBG: BATTLEGROUNDS secret-room coordinates onto a requested screenshot on a second display. **Ctrl+Shift+B** captures one selected monitor. Image recognition runs locally; community point updates use GitHub HTTPS. No account or AI API key is needed.

**[Download LootLizard-Setup.exe for Windows](https://github.com/molnard-labs/LootLizard/releases/latest/download/LootLizard-Setup.exe)** — the latest stable per-user installer. No Python installation or administrator rights are required. Other assets are on [Releases](https://github.com/molnard-labs/LootLizard/releases). Contribute corrections or new point datasets through a pull request: [CONTRIBUTING.md](CONTRIBUTING.md).

Version **0.8.0** adds an installer and optional automatic **application updates** from stable GitHub Releases. These are separate from the community coordinate updates below. Downloads do not close LootLizard or interrupt play; a ready program update is applied only after you close the app or explicitly choose **Restart to update**.

Version **0.8.1** keeps the legacy desktop edition on the `legacy/desktop-migration` branch and updates its GitHub organization links to `molnard-labs`. After the organization rename, an existing **0.8.0** installation needs a one-time run of the latest **LootLizard-Setup.exe** because its old updater rejects the repository redirect. The installer retains the same application identity, settings, profiles and map cache. Version 0.8.1 discovers releases by the permanent repository ID and accepts only the two known repository names, with the existing package and checksum checks.

Version 0.7 introduces the **LootLizard** name and automatic community point-data updates. The app checks at startup and approximately every 60 seconds while open; GitHub workflow execution, CDN caching and retry/backoff can delay delivery. These updates contain coordinates and attribution only, never application code or map images.

Version 0.4 adds **opt-in local map-reference catalogs**. With a suitable full-map reference, the app can identify a referenced map and place points after supported zoom/pan changes. **Your player icon is optional for point display.** Bundled community data contains **15 Erangel points and 12 Taego points**; both sets are unverified, and the Taego list is explicitly incomplete. These are coordinates, not distributed game map images.

Version 0.5 adds **automatic viewing-cone estimates** after map registration, without an icon sample or a supplied player position. It also adds an optional offline Windows OCR hint from city names when geometry cannot identify the map. Text never authorizes point placement.

Version 0.6 redesigns the native interface around the map: precise amber room anchors with small offset number badges, a cyan **YOU** marker, a wider destination list and a separate Settings window. Every visible known room is marked; circle membership and distance determine the list order. **Settings > General > Marker size** offers Large (default) and Medium badges; the small location anchor stays precise.

Both icon methods estimate appearance, not player identity. A changed squad color/slot, an identical-looking teammate or another symbol can cause a wrong match. Solo/Squad player identification has not been validated. This prototype has no official PUBG approval or affiliation.

## Start and choose a language

Run [LootLizard-Setup.exe](https://github.com/molnard-labs/LootLizard/releases/latest/download/LootLizard-Setup.exe), then open LootLizard from its Start menu or desktop shortcut. The application is installed per user under `%LOCALAPPDATA%\SmartLizardOrg.LootLizard\current`; settings, profiles and map cache stay separately under `%LOCALAPPDATA%\LootLizard` and are retained on uninstall.

Windows builds are **unsigned**. Windows SmartScreen may show an unknown-publisher warning; a published SHA-256 is an integrity check, not a code-signing certificate. Download from this project's release page.

The optional ZIP remains a portable/manual-update build: extract the entire ZIP, keep `_internal` beside `LootLizard.exe`, and run it. `start-pubg.cmd` also requests a Steam launch of PUBG. **Existing ZIP/source users must run the installer once to enable application self-updates.** Their compatible local settings and profiles remain usable.

To run from source on Windows with Python 3.12 or newer, including Tkinter:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m lootlizard
```

Source dependencies include Pillow, `opencv-python-headless`, NumPy and, on Windows, Velopack 1.2.161. The source command is `lootlizard`. Windows capture, the global hotkey and two-monitor placement are the supported target; other operating systems are not tested.

The interface starts in **English**. Choose **Settings > General > Language > Magyar** for Hungarian. Language changes apply immediately, preserve the current image/setup/result, and are saved locally. The instructions below use English control labels. **Settings > General > Help** opens the in-app guide.

## Application updates

In an installed build, **Settings > General > App updates > Automatic app updates** is on by default. It checks stable releases from [molnard-labs/LootLizard](https://github.com/molnard-labs/LootLizard/releases) at startup and every six hours, downloading a newer verified package in a separate worker. **Check now** requests a manual check. This is program code from the project's release publishers; package checksums detect corruption, not a compromised publisher account.

A ready update applies after an ordinary **Close**, without restarting, or after you select **Restart to update**. Nothing forces the app to close while you play, and PUBG is not restarted. Explicit restart waits for current background work to finish. If work is still running at ordinary Close, application is deferred to a later run/check; a partially downloaded update is never applied.

Turning **Automatic app updates** off disables scheduled checks **and normal-exit automatic application**. Manual **Check now** and explicit **Restart to update** remain available. Detailed failures are in **Settings > Diagnostics**; update/network failures leave the current map view intact. Source/portable builds instead show **Install LootLizard to enable automatic app updates** and **Download installer**. Community **Map updates** is a separate control and still checks roughly every 60 seconds.

## Local map catalog: optional icon, supported zoom and pan

1. In **Settings > General**, select the game monitor and a different monitor for the companion. Keep the companion entirely on its own display.
2. Prepare your own canonical reference image for each map you want to recognize. Capture the complete, fully zoomed-out map, then crop its exact square map extent in an image editor, excluding surrounding UI. The crop must represent the whole normalized map, not a zoomed section. Save an **RGB PNG or JPEG**. An existing profile's `reference.png` can be reused if its original whole-map bounds and map identity were correct.
3. Put the images and a `catalog.json` together in a local directory. The app imports an existing catalog; it does not create this file or save a new canonical crop for you. See the format below.
4. Choose **Settings > Advanced > Load local map catalog…** and select that JSON file. Its absolute path is saved in local preferences; the images remain at your chosen location. Keep the catalog and images there for future starts. No images are downloaded or copied into the application.
5. Open PUBG's map, at a supported zoom/pan, and press **Ctrl+Shift+B**, or use **Open image…**. The worker identifies a unique referenced map, selects matching bundled/imported point data, and projects visible points onto the screenshot. No icon training or companion click is needed for point placement.

Example local directory:

```text
my-map-references/
  catalog.json
  erangel-full.png
  taego-full.png
```

Example `catalog.json`:

```json
{
  "schema_version": 1,
  "references": [
    {"map_id": "erangel", "file": "erangel-full.png"},
    {"map_id": "taego", "file": "taego-full.png"}
  ]
}
```

Include only references you actually have. Each `map_id` must be unique and must exactly match the corresponding point-data id. `erangel` and `taego` have bundled coordinate data. Other referenced maps need matching point JSON from a community update or imported through **Import JSON…**; identifying a map without matching point data withholds overlays. Loading a catalog does not establish that its images were labeled or cropped correctly. Receiving a new point dataset does not create the local image reference needed to recognize that map.

An optional `sha256` string on each reference entry checks the image's 64-digit hexadecimal SHA-256 when loading. Obtain it in PowerShell with:

```powershell
(Get-FileHash .\erangel-full.png -Algorithm SHA256).Hash.ToLowerInvariant()
```

`file` paths are relative to the catalog directory. Subdirectories are allowed; absolute paths, parent traversal and escaping symlinks are rejected. A catalog is limited to 128 KiB and 32 unique map ids. Each reference must be an RGB PNG/JPEG no larger than 64 MiB, 8192 pixels per side or 40 million pixels, with sides at least 128 pixels. Approximately square geometry and distributed visual detail are required; use an accurately square crop rather than relying on the limited aspect tolerance.

Registration uses distributed SIFT features and a checked similarity transform, with limited affine correction for small reference-aspect errors. It supports north-up map views with enough matching detail. It is **not a universal PUBG map recognizer**: maps absent from the catalog, weak/ambiguous matches, extreme zoom, unsupported rotation/distortion, closed maps and minimap-only scenes should remain unknown. Extreme zoom already caused two abstentions in the small local dataset described below. A match only identifies the supplied reference; it cannot repair an incorrectly labeled/cropped reference.

Version 0.4.1 also requires distributed matches within the map interior. Shared grid letters or HUD icons around different maps' borders cannot establish identity, even when their geometry fits precisely. A small repeated interior patch is insufficient, and multiple genuinely supported references still produce an ambiguous rejection.

Choose **Disable map catalog** to return to the compatible fixed-layout profile path. Existing saved icon profiles are retained.

## Automatic viewing-cone position and optional city-name hints

In catalog mode the worker searches the registered map for a compact colored marker body and two broad, fading cone borders. A unique supported candidate is shown as **YOU**, with an estimated-position description and approximate distances. Center, radius and color are found from the screenshot; no profile is required. The inverse map transform converts the screen position correctly after zoom/pan. Conflicting cone/profile positions and competing cones leave the position unknown. A missing cone can still use a valid, unique legacy trained-icon profile.

**Settings > General > Replay / observer image** disables automatic player estimates for replay/spectator inputs, including trained profiles. Live play is the default intended workflow; this setting is explicit and is not an automatic live/replay classifier. Manual checking positions remain available. A new image or a context change clears old estimates before analysis.

Clipped, dark, occluded or cluttered cones can be missed. In the small local development set, the automatic finder located **3/5 roster-labeled live Training markers**, abstaining on cursor overlap and a cluttered facility background. It also located a cone-like marker in an older private live reference, giving **4/6 visual examples** within **2.7 source pixels**. That older sample does not independently prove identity. All **17 replay/catalog/loading/world examples** returned no center even when tested with a live-context assumption; explicit replay context also abstained. Four Taego replay scenes were evaluated after freezing the detector; there is **no held-out live validation**. These figures do not establish general teammate/pin/color/slot accuracy.

When geometric registration abstains, optional Windows OCR can suggest Erangel or Taego from at least two distinct supported city names. Generic/shared labels such as School, Prison, Terminal or Camp cannot identify a map. The UI says **Text suggests … — zoom out to place points** and keeps overlays withheld. A name alone does not determine zoom, translation or a correct POI transform.

The OCR bridge uses installed English Windows OCR, runs in a hidden local PowerShell process with an eight-second budget, and sends image data only through local memory/stdin. It installs/downloads nothing. Missing language packs or unavailable OCR produce no hint. Microsoft documents desktop OCR with [package identity/MSIX](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr); the unpackaged bridge worked on this development host but is optional and not a deployment guarantee. Across 24 saved scenes it produced 5 correct hints, 7 abstentions on 12 Erangel/Taego views, and no hints on 7 negatives or 5 Camp Jackal views. It **does not rescue the existing extreme-zoom failures 0013/0014**.

## Existing fixed-layout profile path

Catalog use is optional. Without one, the earlier manual/full-map workflow remains available:

1. Use the correct point dataset and open its complete, fully zoomed-out map. Keep the same screenshot dimensions and map framing for later automatic icon matching.
2. Capture/import that image. Choose **Settings > Advanced > Select map bounds**, then click the square map's top-left and bottom-right corners.
3. For automatic icon distances, choose **Save your icon sample**. Select a tight 7–90 source-pixel rectangle around the intended icon, including a 2–3 pixel background margin. Then click a clearly visible, solid-colored, opaque icon pixel inside that box.
4. If a unique match is found, the app saves the cropped reference, mask and profile metadata locally. **Settings > Advanced** shows the profile and mask preview. A manual checking position is also available by clicking an unmarked location on the displayed map.

The app does not verify that the chosen symbol belongs to you. Inspect the sample and matched location yourself. Retrain after changes to icon color/slot, appearance, resolution, UI scale or framing. The shape matcher tolerates component rotation; this does not prove identity. An identical-looking teammate can be a wrong unique match.

The older icon recognizer still requires its saved screenshot size and almost unchanged full-map layout, using distributed ORB features as a guard. **Catalog registration does not make that icon profile zoom-aware.** Under catalog mode, a missing or rejected icon match leaves point overlays available and distances unavailable. Optional icon setup still needs a complete full map; it does not require retraining merely to display zoomed point projections.

## Refresh and read the result

With the companion running, open the game map and press **Ctrl+Shift+B** while PUBG stays focused. The hotkey captures the screen; it does not open/close PUBG's map. Importing an image also starts analysis. Processing does not need a focus change or gameplay input.

The main view shows the map, destinations, a short action/status message and snapshot freshness. Choose **Refresh map** to capture from the companion, or use the shortcut in PUBG. **Settings > Diagnostics** contains detailed recognition messages, shortcut registration and received-request count/time. If capture is black or misses the game, try borderless/windowed mode or import an image. Capture compatibility, DPI scaling and hotkey availability depend on your setup; another application may own the shortcut.

The map overlay shows only points projected inside the image viewport. Once a catalog reference is verified and matching point data is available, the table lists that entire point dataset, including points off-screen. Catalog mode shows **zero table rows and no overlays** while registration is pending, unknown, or unsupported by point data. The legacy fixed-layout mode retains its existing point list. A new capture clears the previous projection, position, circle and distances before analysis. Older asynchronous results cannot replace the current snapshot.

Every visible room has a tiny amber dot/cross at its projected coordinate. A short stem connects it to a small numbered badge matching its list position, so the number does not cover the location. Select a room in the list or click its anchor or badge to highlight it. The top three distance-ranked targets have compact distance labels. Without a fresh unique viewing-cone estimate, trained-icon match or manual checking position, distances are **—**. Icon failure does not hide a successfully registered map's points. A manual checking position is cleared by the next capture. Distances are approximate straight lines and do not account for terrain, roads, entrances or travel time.

A successful result is a snapshot, not continuous tracking. It becomes stale as you move or the circle changes; request a new image. Capture/import age remains visible. The app cannot determine whether a secret room is accessible, opened, looted or contains loot.

## White circle and priority

When a white safe-zone ring is detected, points inside it have a mint outer ring and sort before outside points, then by distance if a position is available. Outside points use a dark amber diamond. If circle membership is unknown, all points keep a neutral amber round marker. The three ranked targets can include outside alternatives if fewer than three points are inside; inspect the circle state in the destination list.

In catalog mode, circle detection currently runs only when the **entire near-axis-aligned, near-uniformly-scaled map fits inside the screenshot**. A clipped zoom/pan view, rotation or distortion leaves the circle **unknown**, even if part of its ring is visible. This avoids incorrectly treating viewport coordinates as full-map coordinates. Zoomed point projection still works independently. Full-map circle detection is approximate, particularly near its edge.

A missing, faint, obscured or competing ring leaves no circle priority. When a position exists, ranking then uses distance alone; without one, distances remain unavailable. An unrelated white ring can resemble the game boundary. The detector does not predict future circles, plan a route through the blue zone, account for terrain or choose a destination for your team.

## Point datasets

Bundled data is [Erangel: 15 points](data/erangel.json) and [Taego: 12 points](data/taego.json). These community coordinates have **not been checked in-game for this project**. Accuracy, completeness and validity for the current game are unverified. The Taego set is an incomplete list, not a claim to cover every secret room.

**Settings > General > Map updates** contains **Automatic map updates** (on by default), **Check now**, and the active data revision/status. Automatic checks run on startup and roughly every 60 seconds. **Check now** requests an immediate check but still respects a server retry delay. Disable the checkbox to stop automatic requests; manual checks remain available. The last valid downloaded snapshot is cached in `%LOCALAPPDATA%\LootLizard\maps-cache.json`; failures keep the last valid data, or bundled data when no valid download/cache exists. The app works with that data while offline.

The public feed is [metadata/maps.json](https://raw.githubusercontent.com/molnard-labs/LootLizard/metadata/maps.json). It is a complete snapshot: removals replace older community entries as well as additions/changes. Your explicitly imported local point files are saved by path and take precedence over community entries with the same map id; a remote update does not overwrite those files. Images and profiles are never part of the feed.

To correct coordinates or add a map, edit the human-readable `data/*.json` on `main` and open a pull request. After merge, the **Publish map metadata** workflow validates all point files and publishes one atomic `maps.json` commit on the `metadata` branch. Running apps can then pick up the new snapshot without a new executable. This is eventual delivery, not an instant push notification: workflow queues, GitHub's raw-content cache and network retry limits apply. A new map still needs a matching local full-map reference before its points can be projected. See [the contribution guide](CONTRIBUTING.md) for stable ids, source licensing and manual coordinate evidence.

Use **Settings > Advanced > Import JSON…** / **Export…** for normalized point data:

```json
{
  "id": "my-map",
  "name": "My map",
  "size_m": 8000,
  "source": {"url": "https://example.org/source", "license": "your-data-license", "attribution": "Data contributors", "notes": "Illustrative, incomplete and unverified."},
  "points": [
    {"id": "point-01", "name": "Secret room 01", "x": 0.25, "y": 0.5}
  ]
}
```

Coordinates refer to the whole square map: `(0, 0)` is top-left and `(1, 1)` bottom-right, regardless of current zoom or pan. `size_m` is an approximate map-side length for distance estimates. The bundled 8000 m scales are nominal; 8192 source-image pixels do not mean 8192 metres. The example identifies no real secret room. Preserve source attribution and licensing when sharing data. There is no interactive point editor.

The coordinate imports come from a pinned community source. Their adaptations and full upstream MIT license are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). That license does not cover PUBG map imagery.

## Local files, privacy and game imagery

Capture uses [Pillow ImageGrab](https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html). Only the selected monitor is returned on request; other visible content on that display can be included. Normal refresh images/results stay in memory and are not written to disk. Image import does not modify the original.

**Successful explicit icon setup saves** `%LOCALAPPDATA%\LootLizard\profiles\<hashed-map-id>\reference.png`, `mask.png` and `profile.json`. The crop can contain markers or any other visible content within the selected bounds. The directory name uses the first 24 hex characters of the map id's SHA-256; it does not anonymize the saved content. The full setup screenshot is not saved by that step. Recreating the same map's profile replaces those files. Close the app and delete its profile directory to remove it.

**Catalog import reads your existing local reference images** and saves only the catalog path in `%LOCALAPPDATA%\LootLizard\settings.json`, alongside language/display preferences. It does not copy them or grant redistribution rights. Dataset export writes to your chosen location. Disabling a catalog removes its saved preference, not your image files.

Image recognition is offline. Enabled/manual update checks access the public GitHub point-data feed and, for installed builds, stable GitHub Releases and their package downloads. **Download installer** opens the fixed release download in your browser. Screenshots, OCR text, profiles and local references are not sent. There is no telemetry, account or API key. Installing dependencies can use the internet, and launching PUBG opens Steam with its own network behavior. The app does not read game memory/files, intercept game traffic, inject code or automate gameplay input. Screenshot operation alone does not establish KRAFTON permission, anti-cheat compatibility or authorization for in-match use; review the current [PUBG Rules of Conduct](https://pubg.com/en/clause/rules_of_conduct).

When no new LootLizard settings exist, compatible earlier `%LOCALAPPDATA%\BasementCompanion\settings.json` settings can be read. Legacy profiles are read in place if no new LootLizard profile exists. The app does not move, copy or delete those old files; future settings/profile/cache writes use LootLizard's directory.

**No copyrighted game map images, captured fixtures, local catalogs or personal icon profiles are distributed with the source/binary.** Create and keep references locally. PUBG imagery and trademarks retain their owners' rights; the project code's MIT license does not cover them. The upstream project also separates its code license from game assets.

## Current validation snapshot

The v0.4.1 private snapshot contains **24 captures** and a local catalog for **Erangel, Camp Jackal and Taego**. Registration identified **15 of 17 visible-map captures correctly** and rejected **all 7 negative scenes**. The two extreme-zoom views, `0013` and `0014`, abstained. The positive count includes **3/3 training reference images**; excluding those, map identification succeeded on **12/14 held-out captures**: Erangel 6/8, Camp Jackal 4/4 and Taego 2/2. Camp Jackal has no secret-point dataset, so recognizing it correctly still produces no secret-room targets.

Across manually annotated held-out views, **72/72 geometry checks were within 8 screenshot pixels**, with a **5.28 px maximum error**. These are grid-anchor/POI projection checks, not proof of physical basement entrances or community-coordinate accuracy. Rejected views do not gain successful position comparisons. Primary inference used annotated map search viewports; separate full-screenshot and GUI checks do not establish automatic viewport or HUD-occlusion discovery.

Before the v0.4.1 fix, adding Taego exposed cross-map matches supported only by common border grid labels and HUD icons, causing ambiguous rejections of valid reference views. The new distributed-interior check rejects that unsupported evidence while retaining rejection when multiple references genuinely qualify. Targeted synthetic cases failed before the fix and pass afterward; the figures above are from the post-fix run.

This is a **small, closed set of three known references**, not general map-recognition accuracy. Multiple captures are correlated; Taego's reference and held-out views come from the **same replay match**. Additional independent matches, maps, zoom/pan settings and 1–4-player scenarios remain necessary. **Own-player identity and allied-marker count are not predicted by registration and remain unverified**; unannotated own identities are not scored. An earlier live yellow-icon check produced a 0.96 silhouette score, which is not a probability of player identity. No real screenshots, reference crops or personal profiles are bundled.

Synthetic tests cover registration transforms, shared border/HUD features, small repeated interior patches, unknown/ambiguous maps, icon ambiguity and circle distractors. State/GUI checks cover optional-icon point display, off-screen clipping, matching-data selection, language switching, clearing stale projections/positions/circles and focus preservation. These checks do not establish general game accuracy.

## Start PUBG together, test and package

**Launch PUBG** requests its Steam launch URI. A shortcut can start both from one icon:

```powershell
.\LootLizard.exe --launch-pubg
# Source equivalent:
.\.venv\Scripts\python.exe -m lootlizard --launch-pubg
```

Steam/PUBG must already be installed. There is no installed Windows autostart or background service; independently launching PUBG will not start a closed companion.

Run tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Build a Windows directory bundle in the same environment:

```powershell
.\.venv\Scripts\python.exe -m pip install "pyinstaller>=6.11,<7"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name LootLizard --add-data 'data;data' --collect-all PIL --collect-all cv2 --collect-all numpy --collect-all velopack --distpath dist --workpath build --specpath . launcher.py
.\.venv\Scripts\python.exe scripts/package_release.py --binary dist/LootLizard --output release --label 0.8.1
```

`--binary` accepts the onedir directory or its `LootLizard.exe`. Packaging refuses to replace an existing bundle/ZIP. Use the build environment so runtime versions/licenses match. Local builds are `local-unpublished` with null repository/commit fields; byte-for-byte reproducibility is not claimed. Source packaging includes code, tests, point JSON and notices, not local screenshots/references/profiles.

Installer packaging uses [scripts/build_installer.py](scripts/build_installer.py) and matching **Velopack Python SDK / .NET `vpk` 1.2.161**. Building requires a compatible .NET SDK; end users do not need Python or the .NET build tools. Install the pinned tool with `dotnet tool install vpk --tool-path .build-tools --version 1.2.161`, then pass `--payload` (the enriched directory produced above), an empty `--output`, and `--vpk .build-tools/vpk.exe` to the script. The installer and full update package include source and dependency notices. The script validates the generated full-package feed/checksum and creates the stable `LootLizard-Setup.exe` alias; it does not install or publish anything.

The `check` workflow validates community data and runs unit tests on Windows for main pushes and pull requests. The separate `metadata` workflow publishes validated point snapshots after relevant main changes or manual dispatch. It never runs a write-enabled job for a pull request. Tagged release automation packages the installer, full update feed/package, optional ZIP and checksums. Check [Actions](https://github.com/molnard-labs/LootLizard/actions) and [Releases](https://github.com/molnard-labs/LootLizard/releases) for actual publication/test status. A local mock or packaging test does not establish a successful installed upgrade. Headless installer CI can verify install/download/apply/uninstall and retained user data, but does not exercise real gameplay, UI focus or the GUI worker-shutdown race. Exercise capture, DPI/monitors, the hotkey, catalog reload, unknown rejection, optional profiles, Steam launch and shutdown on the supported setup before distributing a binary.

## License and sources

Project code: [MIT](LICENSE), copyright 2026 LootLizard contributors. Coordinate attribution and the full upstream MIT license: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Retain runtime/dependency notices when distributing binaries; OpenCV 4.5+ uses Apache-2.0. PUBG imagery and trademarks belong to their respective owners.

- [Coordinate source, pinned commit](https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/web/src/data/secrets.js)
- [Upstream MIT license](https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/LICENSE)
- [Upstream separation of code and game-asset licenses](https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/README.md)
- [Pillow ImageGrab documentation](https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html)
- [OpenCV licensing](https://opencv.org/license/)
- [PUBG Rules of Conduct](https://pubg.com/en/clause/rules_of_conduct)
