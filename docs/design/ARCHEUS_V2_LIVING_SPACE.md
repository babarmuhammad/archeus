

## Round 10b (partial, 2026-10-21): measured Overview layout

Status: partial. Desktop and phone Overview were driven from a measured table (`CONCEPT_LAYOUT`) read from labelled grids over the Codex concepts. Phone-2 and phone-3 were not compared in this round. Known open items: the phone Archeus project label collides with the Codex label at 360 to 440 CSS px (a breach of the zero-overlap rule, stated plainly in the README). Owner decisions kept: Uncertain 09:24 and Needs you 09:25 amber; Verification and Results as blue chain dots.

## Round 10e font size rule and desktop method (2026-10-22)

- Font size rule, changed by the owner (verdict "1 on 1", and the 12 px pick): on the desktop Now frame the concept's own sizes win. Minimum 11 px for frame text (scene, chat, header and nav, Apple HIG 11 pt). Every other view keeps the 14 px minimum (check.mjs asserts both). Tappable controls keep 44 pt hit areas; the visible shapes stay at the concept's size.
- Desktop method is hybrid: the concept raster with live content removed is the base art; every text, rail item, header control, chat row, composer and mark is live on top. Marks and the Fix date test to Codex links are live SVG. The art is rebuilt with `tools/art_desktop.py`; text sizes and offsets are solved with `tools/textfit_desktop.py` and `tools/textreg_desktop.py`.
- Fonts: EB Garamond (titles, headline, lede, wordmark) and Inter (sans, UI, states); both self-hosted under `clients/v2-prototype/fonts/` with OFL texts and sha256.
- Round 10f fonts: serif Libre Caslon Text 500 (headline at 37.42 px with +1.08 px tracking), sans Source Sans 3 400, from the font bake-off (D:\fontbake\results.md). EB Garamond and Inter removed; sha256 in clients/v2-prototype/fonts/sha256.txt.
