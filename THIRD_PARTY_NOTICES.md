# Third-party notices

## Browser runtime and computer vision

LootLizard's own code is MIT licensed. Its runtime dependencies retain their
respective licenses: Pyodide (MPL-2.0), Python (PSF), NumPy (BSD-3-Clause),
Pillow (HPND) and OpenCV (Apache-2.0). The browser downloads the pinned Pyodide
314.0.7 distribution and its packaged dependencies from jsDelivr; these packages
are not copied into this repository's static build.

- https://github.com/pyodide/pyodide/blob/314.0.7/LICENSE
- https://www.python.org/psf/license/
- https://numpy.org/doc/stable/license.html
- https://pillow.readthedocs.io/en/stable/about.html#license
- https://opencv.org/license/

The retired Windows installer and Velopack integration remain in the v0.8.0
source tag, with the notices belonging to that release.

## Automatic Erangel and Taego reference images

Source: the official PUBG API developer asset repository, pubg/api-assets,
commit 32b13b51128b8d8909ae5e77f3b833e01230b24d (2024-10-28).

- Erangel: https://github.com/pubg/api-assets/blob/32b13b51128b8d8909ae5e77f3b833e01230b24d/Assets/Maps/Erangel_Main_Low_Res.png
- Taego: https://github.com/pubg/api-assets/blob/32b13b51128b8d8909ae5e77f3b833e01230b24d/Assets/Maps/Taego_Main_Low_Res.png

The client downloads these reviewed 819 x 819 PNGs directly from the public
raw.githubusercontent.com source and verifies their pinned SHA-256 before use.
The original images are not committed to or bundled with LootLizard. User
screenshots and custom references are never uploaded to that source.

PUBG imagery remains owned by its rights holders and is NOT covered by this
project's MIT code license. The official asset repository directs users to
PUBG's Terms of Use and Player-created Content rules:

- https://github.com/pubg/api-assets
- https://developer.pubg.com/tos
- https://www.pubg.com/player-created-content/

The latter link was unavailable when checked on 2026-10-22. Preserve the
upstream asset notices and consult the current publisher rules before changing
asset use or adding monetization. This free community alpha does not use the
PUBG Developer API, require an API key, sell assets or claim endorsement.

PUBG, PLAYERUNKNOWN’S BATTLEGROUNDS and all related logos are trademarks of PUBG
Corporation or its affiliates. LootLizard is an independent community project.
No official PUBG logo is included in the landing page or application branding.

These historical reference images may differ from the current game. Recognition
can abstain or misalign; default-reference loading is not a general accuracy
claim. A local custom full-map image can override a default for the session.

Retrieved and checksum-verified: 2026-10-22.

## Erangel and Taego secret-room coordinates

Source: adzpm/pubg-map, `web/src/data/secrets.js`.
Source commit: 10dc2faa743835fc2fe00cd745c9f9e3373322b1

Source permalink: https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/web/src/data/secrets.js

Source image dimensions (8192 by 8192 pixels for each map):

- Erangel: https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/web/public/assets/tiles/erangel/info.json
- Taego: https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/web/public/assets/tiles/taego/info.json

License: MIT.

The 15 Erangel entries in data/erangel.json and 12 Taego entries in data/taego.json are adapted from the source file. Changes: x and y were divided by 8192 to produce whole-map coordinates between 0 and 1; stable ids and English display names were added. The upstream order was retained for Taego. These are community observations that have not been verified in the game for this app. Completeness, accuracy and continued validity are unverified. The Taego import is explicitly an incomplete list and must not be presented as a complete inventory of Taego secret rooms.

The 8192 source-image pixels do not mean 8192 metres. Both datasets use size_m: 8000 as an approximate distance scale for the nominal 8 by 8 kilometre maps. Displayed distances are straight-line estimates and do not account for roads, terrain or entrances.

No map image or other KRAFTON asset is included in this data import. The source repository states that its MIT license covers code and does not cover PUBG map imagery or other KRAFTON assets: https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/README.md .

Default map images are fetched directly from the official public source described above. Optional custom reference images remain local. No game image binaries, private captured evaluation fixtures, personal profiles or local catalogs are included in this source or static distribution. Importing or matching a reference does not transfer ownership, grant redistribution rights or extend this MIT license to the image. PUBG imagery and trademarks retain their owners' rights.

Retrieved: 2026-10-21.

The full upstream license follows.

---
MIT License

Copyright (c) 2026 Aleksei Reuk

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
