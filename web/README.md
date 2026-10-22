# LootLizard browser experiment

This separate proof of concept runs map recognition in a browser worker using
Pyodide, NumPy, Pillow and OpenCV. It imports the same pure Python geometry and
CV modules as the desktop application. It does not replace the released Windows
application, and it is not a hosted production service.

The browser downloads the pinned **Pyodide 314.0.7** runtime and its packages from
jsDelivr. The official package set includes `opencv-python`; this experiment
uses Python OpenCV, rather than assuming the stock OpenCV.js build exposes all
required functions. The worker checks real SIFT, descriptor matching and affine
estimators before reporting ready. See [Pyodide packages](https://pyodide.org/en/stable/usage/packages-in-pyodide.html).

## Open the local preview

From the repository root, with Python 3.12 or newer:

```powershell
py -3.12 scripts/serve_web_poc.py --port 8765
```

Open **<http://127.0.0.1:8765/web/poc/>** in desktop Chrome or Edge. Move that
browser window to the second monitor. The server does not open a browser for
you. Stop the server with **Ctrl+C** when finished.

There is no frontend build step or local Python package installation required
for this static server. Internet access is required to load the browser runtime
and packages on a cold start. The first load can take substantially longer than
subsequent frame processing. An offline/PWA cache is not implemented.

The server binds only `127.0.0.1`. It serves the web experiment, direct Python
source modules and point JSON through GET/HEAD. It rejects uploads, mutation
methods, directory listings, traversal and links escaping the public paths.
It is a local development server, not an internet-facing deployment server.

## Try it without a game

Wait for the engine to become ready, then choose **Load demo**. This creates
original deterministic artwork in memory and sends it through the actual CV
worker. The demo has six synthetic rooms and no PUBG imagery. It exercises
registration, point projection and optional marker/circle estimation; it is not
evidence of general accuracy on PUBG screenshots.

**Open image** analyzes a selected PNG or JPEG locally. A real game image needs
a suitable local reference for its map; an arbitrary screenshot is not a
reference or independent confirmation of player identity.

## Use your own map reference and sharing session

1. Open **Setup & preferences**. Under **Local map reference**, choose Erangel or
   Taego, then **Import reference image**. Supply your own complete, fully
   zoomed-out map, cropped to its exact square extent. Alternatively open/share
   an image, choose **Use current image as reference**, drag around the complete
   square map and save it. Exclude surrounding HUD; the selected square must
   represent the entire normalized map, not a zoomed viewport.
2. Choose **Start sharing** and select the PUBG window or the game monitor in
   the browser's picker. Permission and source selection are required each time
   a new capture session starts. The page cannot silently choose a remembered
   game window or monitor.
3. Return focus to PUBG and open its map. Keep the companion visible on the
   second monitor. While sharing stays active, it requests periodic local
   analysis at the selected **Scan interval**. No per-frame click on the browser
   is required. The browser does not press the game's map key for you.
4. Close the map and the next processed non-map frame must clear its map
   targets, position and circle. **Stop**, or the browser's Stop sharing control,
   clears the current result and invalidates replies from earlier frames.

The default language is English; **Language > Magyar** changes the interface.
Use the explicit replay setting when examining replay/observer images; player
estimation is disabled in that context. A reference image is user-owned input,
not a distributed or downloaded game map.

The bundled data contains 15 Erangel and 12 Taego points. Both community lists
remain unverified and Taego is incomplete. Point data alone cannot identify a
map. Updated public point metadata is separate from image references and from
application code. The page checks GitHub's public point feed on startup and
roughly every 60 seconds; failures retain the last valid or bundled data.
Required credits remain in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Browser differences and limits

- Starting screen capture requires a user gesture in a focused, active page.
  Capture consent cannot be persisted. Repeated frame processing uses the same
  live stream until it is stopped or interrupted. See [Screen Capture](https://www.w3.org/TR/screen-capture/).
- A visible browser on monitor 2 can be unfocused while the game has focus.
  This is different from a hidden/minimized tab. Hidden-tab timers and repaint
  callbacks can be throttled, and capture availability depends on the browser,
  OS and selected surface. Do not rely on fixed scan timing or unattended
  background execution. See [page lifecycle](https://developer.chrome.com/docs/web-platform/page-lifecycle-api).
- A normal webpage does not reproduce the desktop companion's Windows global
  **Ctrl+Shift+B** while PUBG owns keyboard focus. This experiment uses an
  already-approved sharing session and automatic scans instead. Keyboard Lock
  concerns a web app's own fullscreen keyboard input; it does not register a
  Windows global hotkey for another foreground application. See [Keyboard Lock](https://developer.chrome.com/docs/capabilities/web-apis/keyboard-lock).
- Monitor placement is manual. Automatic cross-monitor placement would require
  separate Window Management support and permission, which is not universal.
- The CV worker bounds frame size and reference count to contain memory use.
  It accepts at most eight references, reduces reference sides to at most
  1800 pixels and caps processed frames at four million pixels/2400 pixels per
  side. WASM processing speed and memory use must be measured on the target PC.
- Unknown, insufficiently detailed or ambiguous maps abstain. Extreme zoom can
  still fail. Circle priority is unavailable for clipped, rotated or distorted
  full-map geometry. Position/cone estimates remain experimental and do not
  establish own-player identity or distinguish every teammate reliably.
- Desktop Windows OCR, saved desktop icon profiles, Steam launch, native global
  hotkeys and installed-app update handling are not ported by this experiment.
  Closing or reloading the page ends its in-memory capture session.

## Local data and network behavior

Image processing occurs in the worker on the user's device. Screenshots and
reference pixels are not sent to the local server, GitHub, jsDelivr or another
service. There is no image POST endpoint, telemetry, account or AI API key.
Network requests load public runtime/packages, source/data and public point
metadata. Screen sharing grants the page access to the selected surface;
choose the narrowest suitable surface and stop sharing when finished.

With **Remember preferences and map references on this device** enabled, selected reference PNG
blobs are saved in this site's IndexedDB. Language/scan preferences and the last
valid point catalog are saved in localStorage. Captured frames and recognition
results remain in memory. Disabling this checkbox removes the saved references,
preferences and point catalog; currently loaded references remain usable for
the current page session. **Clear references** removes the reference library.

Browser storage belongs to the origin, including the hostname and port. Opening
`localhost:8765` instead of `127.0.0.1:8765`, changing the port, using another
browser/profile or moving to a hosted domain creates a different storage scope.
It does not import the desktop application's AppData paths. Browser-managed
storage is best-effort and can be evicted or cleared; this prototype does not
request persistent storage or provide a reference-library export. Keep original
images and backups outside the page. See [storage quotas and eviction](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria).

## Tests and evidence

Run the non-browser tests from the repository root:

```powershell
py -3.12 -B -m unittest discover -s web/tests -p 'test_*.py' -v
node --test web/tests/*.test.mjs
```

The separate **Browser experiment** workflow runs these checks and installs
Playwright 1.64.1/Chromium into the disposable CI environment. Its actual-browser
probe loads the real pinned Pyodide packages, checks SIFT/affine functionality,
registers synthetic map → non-map gameplay → map frames, verifies known point
projection, tests the demo UI, and checks late replies and ended-stream clearing.
An explicitly gated loopback `?test=1` hook accepts a real synthetic canvas
MediaStream for these tests; it does not replace or bypass the normal screen
picker. Tests do not use real game screenshots, screen-sharing permissions or
user profiles. Reports, traces and screenshots contain synthetic data only.

The CI browser script is intentionally restricted to GitHub Actions. Use the
approved visible browser tooling for local visual validation. A source/syntax
test passing locally is separate from an actual successful browser/CI run; see
[Actions](https://github.com/SmartLizardOrg/LootLizard/actions) for recorded runs.
No production deployment or public hosting is performed by this workflow.

The project code license does not grant rights to PUBG imagery or trademarks.
Screenshot-based operation is not proof of official PUBG approval or anti-cheat
compatibility. All existing recognition and dataset limitations still apply.
