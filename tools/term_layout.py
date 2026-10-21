"""Measure the terminal overview concept and print the text-run table used by CONCEPT_TERM in app.js.

usage: py -I tools/term_layout.py <terminal-1-overview-v2.png> <RobotoMono-wght.ttf>

For each run the ink extent is read from the concept inside a search box (ink = luminance above 90, the
concept background is about 20). The font is Roboto Mono at the cell size (advance 0.6 em, so the size is
cell / 0.6). The origin and the letter pitch are solved so the rendered ink matches the concept's left and
right ink edges. Output: x (origin, design px), y (baseline), pitch (design px per character).
"""
import sys
import numpy as np
from PIL import Image, ImageFont

CELL = 13.0
SIZE = CELL / 0.6

# text, colour key, search box (x0, x1), baseline. Single glyphs use pitch None and are drawn as marks in app.js.
RUNS = [
    ("ARCHEUS", "ivory", (30, 140), 70),
    ("Not stopped · accepts new work", "ivory", (205, 640), 70),
    ("CONCEPT FIXTURE", "dim", (1360, 1575), 70),
    ("1 needs you", "amber", (30, 200), 102),
    ("·", "dim", (200, 222), 102),
    ("1 verifying", "blue", (222, 400), 102),
    ("Archeus", "ivory", (515, 625), 266),
    ("Search provenance", "amber", (560, 800), 329),
    ("Review plan", "amber", (575, 735), 393),
    ("Fix date test", "blue", (885, 1070), 329),
    ("Verifying", "blue", (890, 1025), 393),
    ("Codex", "ivory", (936, 1015), 459),
    ("Verification", "blue", (878, 1045), 528),
    ("Results", "blue", (910, 1012), 596),
    ("+1 more", "dim", (515, 615), 627),
    ("Notes", "ivory", (1268, 1345), 329),
    ("2 missions", "dim", (1276, 1412), 364),
    ("Ideas", "ivory", (1268, 1345), 497),
    ("ARCHEUS", "ivory", (745, 855), 172),
    ("Why:", "amber", (36, 100), 699),
    ("Plan approval required.", "ivory", (106, 420), 699),
    ("[Enter] Open decision", "dim", (36, 330), 734),
    ("j/k select", "ivory", (36, 185), 804),
    ("Enter open", "ivory", (216, 362), 804),
    ("b Back", "ivory", (396, 490), 804),
    ("p Replay", "ivory", (518, 642), 804),
    ("t Tell", "ivory", (670, 765), 804),
    ("r Review", "ivory", (798, 922), 804),
    ("s Stop", "ivory", (950, 1046), 804),
    ("> Tell Archeus...", "dim", (36, 275), 855),
]


def main():
    concept, fontpath = sys.argv[1], sys.argv[2]
    im = np.asarray(Image.open(concept).convert("RGB")).astype(np.float32)
    L = 0.299 * im[..., 0] + 0.587 * im[..., 1] + 0.114 * im[..., 2]
    f = ImageFont.truetype(fontpath, SIZE)
    f.set_variation_by_axes([400])
    for text, colour, (x0, x1), base in RUNS:
        band = L[base - 17:base + 3, x0:x1] > 90
        cols = np.nonzero(band.any(axis=0))[0]
        ink0, ink1 = x0 + cols[0], x0 + cols[-1] + 1
        chars = [c for c in text if c != " "]
        first = text.index(next(c for c in text if c != " "))
        last = len(text) - 1 - text[::-1].index(next(c for c in text[::-1] if c != " "))
        lsb = f.getbbox(text[first], anchor="ls")[0]
        rink = f.getbbox(text[last], anchor="ls")[2]
        n = last - first
        if n > 0:
            pitch = ((ink1 - ink0) - (rink - lsb)) / n
        else:
            pitch = CELL
        origin = ink0 - lsb - first * pitch
        print('  ["%s", "%s", %.1f, %d, %.2f],' % (text.replace('"', '\\"'), colour, origin, base, pitch))


if __name__ == "__main__":
    main()
