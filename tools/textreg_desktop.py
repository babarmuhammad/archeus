"""Register desktop text: ink box of each item in the concept vs the render (same search box, same threshold).

Run: py -I tools/textreg_desktop.py render_frame.png
Prints the concept ink box, the render ink box and the offsets (render minus concept) in master px.
"""
import sys
import cv2
sys.path.insert(0, r"D:/archeus-t123-desktop/tools")
from textfit_desktop import ITEMS, ink_box  # noqa: E402

CON = r"D:/hub-concepts-codex4/desktop-1-now-v2.png"


def main(render_path):
    c = cv2.cvtColor(cv2.imread(CON), cv2.COLOR_BGR2GRAY)
    r = cv2.cvtColor(cv2.imread(render_path), cv2.COLOR_BGR2GRAY)
    print(f"{'item':<15}{'concept x0,y0,x1,y1':>26}{'render':>26}{'dx0':>6}{'dy0':>6}{'dw':>6}{'dh':>6}")
    for name, font, wght, box, text in ITEMS:
        a = ink_box(c, box)
        b = ink_box(r, box)
        if a is None or b is None:
            print(f"{name:<15} no ink (concept {a is not None}, render {b is not None})")
            continue
        dx0, dy0 = b[0] - a[0], b[1] - a[1]
        dw, dh = (b[2] - b[0]) - (a[2] - a[0]), (b[3] - b[1]) - (a[3] - a[1])
        print(f"{name:<15}{str(a):>26}{str(b):>26}{dx0:>6}{dy0:>6}{dw:>6}{dh:>6}")


if __name__ == "__main__":
    main(sys.argv[1])
