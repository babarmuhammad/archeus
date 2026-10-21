# Fonts (vendored, SIL Open Font License 1.1)

Used by the phone Overview only (`style.css`, families "Archeus Serif" and "Archeus Sans"). The desktop keeps its system stack. The files are loaded from this folder only: no network font request. Downloaded or copied font files are data: the browser reads them, nothing executes them.

| File | Family | Source (official upstream) | sha256 |
|---|---|---|---|
| `LibreCaslonText-VF.ttf` | Libre Caslon Text, variable (wght 400 to 700) | https://github.com/google/fonts/tree/main/ofl/librecaslontext (file `LibreCaslonText[wght].ttf`) | c11809dbfd5445886293d89b32bfc2584075c80e77750cf1c284113e36b8b3f4 |
| `Inter-VF.ttf` | Inter, variable (opsz 14 to 32, wght 100 to 900; opsz pinned to 14) | https://github.com/google/fonts/tree/main/ofl/inter (file `Inter[opsz,wght].ttf`) | 29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031 |

Licence texts: `OFL-LibreCaslonText.txt` (sha256 a294245c822c5aa9fd9a9f3189418e99415428be5fecadf797793d5d8f6a3ad3) and `OFL-Inter.txt` (sha256 5b9321a4298cfeb6b34354164a1c3afc3db114569984c502b9b35d988fd58c57), from the same upstream folders.
Copyright: Libre Caslon Text (OFL 1.1) per its licence text; Inter: Copyright 2020 The Inter Project Authors, rsms/inter.

Choice (round 10d). The serif was chosen from the bake-off in `D:\fontbake\results.md` (no free font matched the concept serif; best mean IoU 0.47). Libre Caslon Text weight 500 is the serif. Inter is the sans: on the overlay it has the lower mean error for the sans regions (23.2 against 24.9 for Source Sans 3, weight 400, with the same fit), and its fixture line is closer. Earlier, the Garamond-family candidates were checked with the same overlay (EB Garamond, Cormorant Garamond) and were not closer.
