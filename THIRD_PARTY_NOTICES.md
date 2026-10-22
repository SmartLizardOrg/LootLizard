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

## Original Erangel and Taego coordinates, and Deston supplements

Source: adzpm/pubg-map, `web/src/data/secrets.js`.
Source commit: 10dc2faa743835fc2fe00cd745c9f9e3373322b1

Source permalink: https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/web/src/data/secrets.js

Source image dimensions (8192 by 8192 pixels for each map):

- Erangel: https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/web/public/assets/tiles/erangel/info.json
- Taego: https://github.com/adzpm/pubg-map/blob/10dc2faa743835fc2fe00cd745c9f9e3373322b1/web/public/assets/tiles/taego/info.json

License: MIT.

The 15 Erangel entries and 11 retained Taego entries are adapted from this source. Taego keeps its stable ids: taego-01 is corrected from the second licensed source below, and taego-13 through taego-15 are added from that source, giving 15 source-listed rooms. Deston adds five distinct positions from this dataset (source pixels 3144/2713, 6395/4568, 6649/4966, 6714/4229 and 6764/4345) to the second source's 34. Exact upstream indices and native pixels for every imported point are recorded in data-sources/secret-locations.json. Coordinates were divided by 8192 with a top-left origin, x right/east and y down/south; stable ids and English names were added. Community observations are not in-game verification for LootLizard. Completeness, accuracy and current access remain unverified.

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


## Expanded secret locations: ziphow/pubg-map-toolkit

Source commit: 3b68a2f10b29a64603ea88aae36f90ee20cb3c68

- Coordinate source: https://github.com/ziphow/pubg-map-toolkit/blob/3b68a2f10b29a64603ea88aae36f90ee20cb3c68/src/points.js
- Coordinate convention: https://github.com/ziphow/pubg-map-toolkit/blob/3b68a2f10b29a64603ea88aae36f90ee20cb3c68/src/app.js
- License: https://github.com/ziphow/pubg-map-toolkit/blob/3b68a2f10b29a64603ea88aae36f90ee20cb3c68/LICENSE

License: MIT; Copyright (c) 2026 Axiom. Retrieved/reviewed 2026-10-22.

The source declares user-annotated native image pixels and MAP_PX=8192 for all maps, with a top-left origin and y increasing downwards. We normalize x/8192 and y/8192; nominal map size in metres is never the divisor. The source's obsolete Vikendi kmSize=6 is not imported; the separate official reference uses the reborn 8 km map.

Imported categories: 15 Miramar secret rooms plus three separate Los Leones underground entrances (source category `basement`, shipped as `tunnel_entrance`); 15 Rondo secret rooms with the individual correction below; 34 Deston security rooms (supplemented with five adzpm records above); 10 Vikendi security rooms and 10 bear-cave entrances; 8 Paramo room positions; and 22 Karakin basement/tunnel-entrance markers. Taego uses S403 for its first-point correction and S413-S415 for the three additions. Erangel retains its existing secret-room source; separate bunker entrance observations are documented below. New English names and stable ids were assigned; distinct location kinds drive the interface's room, security, cave and tunnel icons. Vehicles, gas stations, lab camps and crowbar locations are excluded. Multiple entrances may enter one underground space; cave/entrance counts are not counts of distinct key-locked rooms.

These are community-listed positions, not an exhaustive inventory or a claim that every entrance is accessible in the current game/mode. Deston's closely spaced or multilevel rooms have no floor/door metadata. Paramo's changing landmarks and historical reference imagery require comparison with the current match. Sanhok and Training retain empty point lists because no suitable precise secret-location coordinates were included; this is not evidence that those maps have no hidden places. Haven's separate historical candidate-building observations are documented below. No source images, tiles or game artwork are copied by this coordinate import.

### Erangel: separately recorded bunker entrance observations

Original author map: https://pubgresource.com/maps/erangel . Seven individual factual entrance coordinates were recorded from its numbered bunker-entrance markers: three northern bunkers and four Shelter approaches. The offshore Starting Island marker is excluded from gameplay targets. These are separate from the 15 MIT-licensed secret-room records; no room marker was moved, duplicated as an entrance or matched arbitrarily to one of these bunkers.

The source page's HTTP Last-Modified is 2023-10-30. Its versioned point bundle is https://pubgresource.com/_next/static/chunks/pages/maps/erangel-4766ea9aef9b58d1.js (raw SHA-256 `d2f7c70210d77bdcc410b934d95f384dc615e6ed30a86f2c78b7a7cdc08cfaae`); the coordinate component is https://pubgresource.com/_next/static/chunks/231.2e78ae7c661ea0cb.js (raw SHA-256 `621928b5ee80686af267914ef240c1d12c0040b4b455b7797d188cd243fc1e71`). Normalization is x/1000, y/1000 with a top-left origin, derived from the component's 256-unit map plane. Source/reference alignment with 741 affine inliers has a median residual of 0.299 reference pixels and p95 of 1.101 pixels; this checks image alignment, not doorway accuracy.

The original site has no identified general data license, and no license to its code or artwork is asserted. Only these factual location observations are recorded; no source code, tile images, icons or prose are redistributed. LootLizard's factual annotations, English names and ids are MIT, with attribution to PUBG Resource contributors retained in the map and `data-sources/erangel-bunker-entrances.json`. The audit preserves the exact observations, source fingerprints, coordinate convention and exclusions. These are historical community positions; current access and entrance precision have not been checked in game for LootLizard. Shelter has changed since this source was published, so the unchanged terrain alignment is not a guarantee of current accessibility. Reviewed 2026-10-22.

### Haven: independently transcribed historical candidate buildings

Original source: https://www.inven.co.kr/board/battlegrounds/5074/3400, posted 2020-12-10 by 핑핑위. The map credits Nabae-_- / HwapYong; its image URL records a 2021-03-25 revision: https://upload3.inven.co.kr/upload/2021/03/25/bbs/i15985128602.png . The source map is not openly licensed and is not redistributed or represented as MIT artwork.

LootLizard independently transcribed the 22 observed marker centres as factual possible-building coordinates and aligned them to its separately licensed official Haven reference. Only these new numerical observations and the reproducible affine transform are included in data-sources/haven-candidate-buildings.json, under the project's MIT license. No original image, map plate, author prose or bulk third-party coordinate dataset is copied. Original map/artwork rights remain with their owners.

The source reports five active Pillar Supply Caches per match among possible buildings, most randomly chosen. Accordingly, these records use the distinct supply_cache kind, names beginning 'Possible Pillar cache', and a player-visible historical/conditional warning. They mark approximate building centres, not exact doors or 22 guaranteed active caches. Current live/custom-game validity and completeness have not been verified. Image alignment (406 inliers, median residual 0.235 reference pixels) measures registration quality, not cache-door accuracy. A static catalogue cannot determine which candidates activate in a given match.

Sanhok's ordinary named Cave POI was deliberately not substituted for a precise hidden-room entrance. The absence of suitable records does not establish absence of hidden loot.

### Independent corroboration and one Rondo position correction

Public first-party key-use observations at https://pubgstatistics.com/secretrooms (page dated 2026-09-20; itself pending manual verification) and original authored room maps at https://steamcommunity.com/sharedfiles/filedetails/?id=3583051048 were consulted to cross-check position/type outliers. They are not treated as MIT-licensed datasets or artwork, and neither bulk dataset nor map image is redistributed. This is not LootLizard live-game verification.

One individual factual coordinate is corrected: stable id rondo-08, upstream S608 at 5615/6109 source pixels, now uses normalized (0.69952, 0.74753). Recent key-use observations and the original authored map independently place the room northwest of Tu Ling, about 114 m east of the source annotation. The original pixel pair and correction sources remain in the audit file, so the change does not misrepresent the upstream dataset. Taego's first marker correction and three additions are likewise corroborated, but use the MIT coordinate records themselves.

The source's full MIT license follows.

---
MIT License

Copyright (c) 2026 Axiom

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
