"""Register Replay text: ink box of each item in the concept vs the render (same search box, same threshold).

Run: py -I tools/textreg_replay.py render_frame.png
Prints the concept ink box, the render ink box and the offsets (render minus concept) in master px. Apply the
offset to the element's translate (the --dx / --dy variables in style.css); a positive dy moves text down.
"""
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textfit_replay import ITEMS, ink_box  # noqa: E402

CON = r"D:/hub-concepts-codex4/replay-2-desktop-v2.png"


def main(render_path):
    c = cv2.cvtColor(cv2.imread(CON), cv2.COLOR_BGR2GRAY)
    r = cv2.cvtColor(cv2.imread(render_path), cv2.COLOR_BGR2GRAY)
    print(f"{'item':<14}{'concept':>24}{'render':>24}{'dx0':>6}{'dy0':>6}{'dw':>6}{'dh':>6}")
    for name, font, box, text, spaced in ITEMS:
        a = ink_box(c, box)
        b = ink_box(r, box)
        if a is None or b is None:
            print(f"{name:<14} no ink (concept {a is not None}, render {b is not None})")
            continue
        dx0, dy0 = int(b[0] - a[0]), int(b[1] - a[1])
        dw, dh = int((b[2] - b[0]) - (a[2] - a[0])), int((b[3] - b[1]) - (a[3] - a[1]))
        print(f"{name:<14}{str(tuple(int(v) for v in a)):>24}{str(tuple(int(v) for v in b)):>24}{dx0:>6}{dy0:>6}{dw:>6}{dh:>6}")


if __name__ == "__main__":
    main(sys.argv[1])
