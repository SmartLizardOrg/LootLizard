# LootLizard

A browser companion for finding PUBG secret rooms on a second screen. Open the
website, start a screen-sharing session, return to the game and open its map.
LootLizard periodically processes the shared image on your computer and plots
community room coordinates when it can identify the map.

**Web alpha · 0.9.0.** The interface defaults to English, with Hungarian available.
No desktop installation, account, API key or global hotkey is required.
[Magyar leírás](README.hu.md) · [Contributing](CONTRIBUTING.md) ·
[Releases](https://github.com/SmartLizardOrg/LootLizard/releases)

## Use the companion

1. Open the landing page in desktop Chrome or Edge and select **Open LootLizard**.
2. Put the companion on the second monitor. Wait for the local recognition engine
   and map references to load on the first visit.
3. Select **Start sharing**, choose the PUBG window or its monitor in the browser
   picker and approve sharing. Return focus to PUBG.
4. Open the game's map. Automatic local scans update the companion; you do not
   need to click the companion for each scan. The website does not press the
   game's map key.
5. Select **Stop**, stop sharing with the browser control, or close the page when
   finished. Stopping invalidates any pending result and clears its geometry.

The app loads public map references automatically. You can optionally supply
your own complete, square map references in settings. The normal flow does not
require finding or downloading an image yourself. Reference availability depends
on its external source; a failed load is reported and must not produce a guessed
map result. Source and game-asset licensing details are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

**Load demo** runs the actual recognition worker on original synthetic artwork.
It lets you try the app without PUBG or screen-sharing permission. Its generated
rooms are demo data, not real secret-room locations.

## What the alpha provides

- Browser screen sharing with automatic scans while the game has keyboard focus.
- Map registration, projected room locations, experimental player/cone estimation
  and safe-circle prioritization when the required geometry is recognizable.
- Community coordinates for **15 Erangel rooms** and **12 Taego rooms**. The lists
  are unverified; Taego is incomplete. Displayed distances are approximate and do
  not account for terrain, roads or entrances.
- Local processing in a browser worker using Python, NumPy, Pillow and OpenCV
  through the pinned Pyodide runtime. Screenshots and reference pixels are not
  uploaded for recognition.
- Public point-data updates from this GitHub repository, checked at startup and
  roughly every 60 seconds. Invalid updates retain the last good data.
- Optional browser storage for preferences and map references.

Unknown or ambiguous frames clear targets instead of reusing old coordinates.
Extreme zoom, map changes, HUD occlusion and team-marker ambiguity can still
defeat recognition. A viewing-cone estimate is not proof of own-player identity.
Replay mode disables the player estimate. Check the in-game map before choosing
a destination.

## Platforms and performance

The website has no Windows-specific native component. Desktop Chrome and Edge
are the initial browser target; screen capture and background scheduling depend
on browser, operating system and capture source. Other browsers and operating
systems require validation. A portable website does not make the PUBG game
itself available on another operating system. Console/mobile capture is not an
implemented integration.

Keep the companion visible on the second monitor. Minimized or hidden tabs may
be throttled. Browsers require a fresh source selection for a new sharing
session; the page cannot silently reauthorize screen capture after a reload.

The default capture request is **1 FPS**, with bounded frame dimensions and a
three-second recognition interval. The sampler reuses its canvas and avoids
unchanged preview writes. This reduces unnecessary work, but does not establish
an insignificant game-performance cost. Earlier 3 FPS sharing measurements on
one PC showed a small mean-FPS decrease and a larger effect on the slowest
frames. The optimized path still needs controlled in-game measurement, including
full recognition with references. See [web/README.md](web/README.md) for details.

## Privacy and network use

Screen and image analysis runs on the user's device. There is no image-upload
endpoint, telemetry, account or AI service. Network requests fetch public app
files, pinned runtime packages, public map references and coordinate metadata.
Hosting and asset providers still receive ordinary requests for those files.

Captured frames and results stay in memory. If remembering data is enabled,
preferences and point metadata use localStorage and reference images use
IndexedDB. Storage belongs to the website origin and browser profile, can be
cleared by the user, and may be evicted by the browser. Disable remembering data
or clear references in settings to remove saved application data. Closing or
reloading the page ends screen capture.

The project does not read game memory, inject code, intercept game traffic or
automate gameplay. It is an independent community project. Image-based operation
does not establish official PUBG approval or anti-cheat compatibility.

## Develop locally

Building the static site requires only Python 3.12+ and the standard library:

```sh
python scripts/build_web.py
python scripts/serve_web.py --port 8765
```

Open `http://127.0.0.1:8765/`; the application is at `/app/`. Internet is needed on
the first visit for the browser runtime and public references. The development
server binds to loopback and serves only the generated `dist/` directory. It has
no backend or upload route.

For portable Python CV tests, also install the package dependencies:

```sh
python -m pip install .
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s web/tests -p 'test_*.py' -v
node --test web/tests/*.test.mjs
```

`web/tests/browser-smoke.cjs` runs in GitHub Actions with isolated Chromium and
the real pinned Pyodide/OpenCV runtime. Synthetic tests exercise registration,
projection, cancellation and stream shutdown. They do not establish recognition
accuracy across real matches or browser/OS combinations.

The source layout is intentionally small:

| Path | Purpose |
|---|---|
| `web/landing/` | Landing page and launch CTA |
| `web/app/` | Browser interface, capture/session logic and CV worker |
| `lootlizard/` | Portable geometry, CV and offline evaluation code |
| `data/` | Attributed community room coordinates |
| `scripts/build_web.py` | Public-asset allowlist and static packaging |
| `dist/` | Generated website, excluded from source control |

Native GUI, installer and installed-app updater code was removed from the web
branch. The earlier Windows version remains in Git history and the `v0.8.0` tag.

## Release-based hosting

Application publication follows **GitHub Releases**, rather than every source
commit. After tested source is merged to `main`, publish a prerelease such as
`v0.9.0-web.1`. The **Publish web release** workflow validates that its commit is
already in `main`, tests/builds it, attaches a static ZIP and checksum, then
updates the generated `web-release` branch without rewriting its history.
Older release tags cannot roll production back. No Windows installer or desktop
update feed is published by the web workflow.

For Cloudflare Pages Git integration, select this repository and configure:

| Setting | Value |
|---|---|
| Production branch | `web-release` |
| Framework preset | None |
| Build command | Empty |
| Build output directory | Repository root (`/`) |

That branch already contains the curated static site. Source branches and pull
requests are not the production publish source. A direct local preview build
uses `python scripts/build_web.py` and output `dist/` instead. The generated
`build-info.json` records version, source commit, release tag and asset hashes.

Application files revalidate on navigation/reload. An open game session keeps
its loaded application code until reloaded, so publishing does not interrupt
screen sharing. Community point-data updates remain separate and can arrive in
an existing session after a data PR is merged and its metadata workflow finishes.
GitHub/CDN caching may delay availability; updates are not guaranteed instant.

## License and attribution

Project code is [MIT](LICENSE). Required coordinate attribution, upstream
licenses and runtime/image-source notices are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The code license does not grant
rights to PUBG imagery or trademarks. Private captures, evaluation screenshots
and personal profiles are never part of the public static build.
