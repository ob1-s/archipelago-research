# Asset Licenses

All files under `sprites/`, `tilemap/`, and `KENNEY_TINYTOWN_LICENSE.txt` are
from the **Kenney "Tiny Town"** game-asset pack (version 1.1, released
2023-01-11), created and distributed by Kenney (www.kenney.nl).

- **Source:** https://kenney.nl/assets/tiny-town
- **Author:** Kenney (Kenney.nl)
- **License:** Creative Commons Zero 1.0 Universal (CC0)
  http://creativecommons.org/publicdomain/zero/1.0/
  The pack's own license text is kept verbatim in
  `KENNEY_TINYTOWN_LICENSE.txt`.
- **Files shipped:**
  - `sprites/tile_0000.png` ... `tile_0131.png` — the pack's 132
    individual 16x16 tiles (verbatim, unmodified).
  - `tilemap/tilemap.png` — the pack's packed tilemap sheet (verbatim,
    unmodified).
  - `KENNEY_TINYTOWN_LICENSE.txt` — the pack's license file (verbatim).

## Attribution

CC0 does not require attribution. As a courtesy: "Tiles by Kenney."

## Usage notes

- The shipped files are copied verbatim and are **not** used by the current
  web UI at render time. The viewer's town renderer draws procedural
  graphics (deterministic, from the replay bundle) so screenshots and
  replays depend on no external image loading.
- Tile glyphs, if used later, would be served from this directory by the
  viewer server as static files. Until then the sprites are reference
  material for a future sprite based renderer skin.

## Why CC0-only

Only CC0 / public-domain assets are eligible for inclusion in this
repository, to keep the viewer free to redistribute. No AI Town or other
proprietary game assets are used.