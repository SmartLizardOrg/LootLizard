# Third-party notices

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

The application's optional map-reference catalogs point to the user's own local images. No canonical game images, private captured evaluation fixtures, personal profiles or local catalogs are included in the source/binary distribution. Importing or matching a reference does not transfer ownership, grant redistribution rights or extend this MIT license to the image. PUBG imagery and trademarks retain their owners' rights.

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
