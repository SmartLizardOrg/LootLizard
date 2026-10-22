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

## Local match-context OCR

The optional, lazily loaded lobby/results reader uses Tesseract.js 7.0.0,
Tesseract.js-core 7.0.0 (Apache-2.0), and the English `4.0.0_best_int` model from
`@tesseract.js-data/eng` 1.0.0. That npm wrapper declares MIT; its upstream trained
data carries Apache-2.0. They are downloaded by the client
from pinned jsDelivr URLs rather than bundled in this static site. The English
gzip is 2,952,873 bytes, SHA-256
`45b4cb346724ac1774f1c36f42f182b887bcdb28ebe63e6fff90ac41f3fcff91`,
verified before loading. No recognition image or OCR text is uploaded.

- https://github.com/naptha/tesseract.js/blob/v7.0.0/LICENSE.md
- https://cdn.jsdelivr.net/npm/tesseract.js-core@7.0.0/LICENSE
- https://cdn.jsdelivr.net/npm/@tesseract.js-data/eng@1.0.0/package.json
- https://github.com/naptha/tessdata/blob/gh-pages/LICENSE

The footer descriptor and OCR words are session memory only. User names and
screen captures are not bundled, logged or added to the public distribution.

## Bundled official PUBG developer map references

The static application includes eleven unchanged public PNGs from the official
PUBG API developer asset repository, `pubg/api-assets`, pinned to commit
`32b13b51128b8d8909ae5e77f3b833e01230b24d` (2024-10-28). That commit was still
its latest master when checked on 2026-10-22.

| Map | Original official filename |
|---|---|
| Erangel | `Erangel_Main_Low_Res.png` |
| Miramar | `Miramar_Main_Low_Res.png` |
| Sanhok | `Sanhok_Main_Low_Res.png` |
| Vikendi | `Vikendi_Main_Low_Res.png` |
| Karakin | `Karakin_Main_Low_Res.png` |
| Paramo | `Paramo_Main_Low_Res.png` |
| Haven | `Haven_Main_Low_Res.png` |
| Taego | `Taego_Main_Low_Res.png` |
| Deston | `Deston_Main_Low_Res.png` |
| Rondo | `Rondo_Main_No_Text_Low_Res.png` |
| Training / Camp Jackal | `Training_Main_Low_Res.png` |

The complete source URL, original bytes, SHA-256, dimensions and byte count of each
asset are preserved in `web/app/map-assets/manifest.json`. All selected PNGs measure
819×819; the total is 14,079,121 bytes. Only local filenames were shortened. Rondo
uses the official no-text variant because the upstream file named
`Rondo_Main_Low_Res.png` actually contains JPEG data. Training/Camp Jackal duplicate
aliases are included once, not treated as distinct maps.

The files are served as part of LootLizard's free community application, with local
hash checks before use. They are not sold or offered as a standalone asset pack.
No private capture, user reference or personal profile is bundled. No screen image
is uploaded to GitHub, the publisher or another recognition service.

PUBG imagery remains owned by its rights holders and is **not covered by this
project's MIT code license**. The official asset repository directs its users to
the publisher's Terms of Use and Player-created Content rules. Its Terms describe
use and distribution of data in software products and prohibit removing proprietary
notices or distributing that data separately from a product. This notice does not
relicense the assets or claim additional permissions beyond the publisher's terms.

- Official repository and upstream instructions: https://github.com/pubg/api-assets/blob/32b13b51128b8d8909ae5e77f3b833e01230b24d/README.md
- Original map directory: https://github.com/pubg/api-assets/tree/32b13b51128b8d8909ae5e77f3b833e01230b24d/Assets/Maps
- Publisher Terms of Use: https://developer.pubg.com/tos
- Player-created Content URL supplied by upstream: https://www.pubg.com/player-created-content/

The Player-created Content URL could not be resolved during the automated check
on 2026-10-22; no additional license is inferred from that unavailable link. Keep
upstream notices and review the current publisher terms when changing asset use
or monetization. This application does not use the PUBG Developer API, require an
API key, or claim publisher approval.

PUBG, PLAYERUNKNOWN’S BATTLEGROUNDS and all related logos are trademarks of PUBG
Corporation or its affiliates. LootLizard is an independent community project.
No official PUBG logo is included in its application or landing-page branding.

These historical assets can differ from current game maps. Paramo's terrain changes
between matches; rotation/mode availability also changes. Bundled reference coverage
is not a guarantee of identification, current availability, exact projection or
own-player accuracy. Current publisher map descriptions are available at
https://www.pubg.com/en/game-info/maps/erangel . Haven is included as a historical
official battleground asset, not a claim about the current matchmaking rotation.

Source, byte hashes and PNG dimensions verified: 2026-10-22.

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

Official public reference PNGs are bundled separately under the source and publisher terms described above. This coordinate import includes no image, and its MIT license does not license the separately bundled PUBG artwork. Private evaluation captures, personal profiles, custom user references and local catalogs are never included in the source or static distribution. Matching a reference does not transfer ownership or extend the project's MIT license to that image. PUBG imagery and trademarks retain their owners' rights.

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
