"""Solve Replay text sizes from the concept raster (same method as tools/textfit_desktop.py).

Run: py -I tools/textfit_replay.py
For each item the concept ink box is measured inside a search box (contrast against the local background), and
the font size is solved so the PIL ink width of the same string matches. Spaced items (wordmark, fixture,
ARCHEUS) are sized from cap height and tracked to the measured width. Output: a table to copy into style.css.
"""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CON = r"D:/hub-concepts-codex4/replay-2-desktop-v2.png"
FONT_DIR = r"D:/archeus-t123-replay/clients/v2-prototype/fonts/"
FONTS = {"serif": FONT_DIR + "LibreCaslonText-wght.ttf", "sans": FONT_DIR + "SourceSans3-wght.ttf"}
SERIF_WGHT = 500
MIN_FRAME = 11.0  # owner rule: frame text is at least 11 px

# name, font, search box (x0, y0, x1, y1) in master px, text, spaced (cap height sizing and tracking)
ITEMS = [
    ("wordmark", "serif", (14, 14, 206, 36), "ARCHEUS V2", True),
    ("fixture", "sans", (20, 42, 170, 58), "CONCEPT FIXTURE", True),
    ("status", "sans", (926, 14, 1150, 36), "Not stopped \u00b7 accepts new work", False),
    ("tell", "sans", (1200, 20, 1280, 42), "Tell", False),
    ("stop", "sans", (1330, 20, 1400, 42), "Stop", False),
    ("nav_now", "sans", (60, 100, 130, 122), "Now", False),
    ("nav_projects", "sans", (60, 146, 140, 168), "Projects", False),
    ("nav_replay", "sans", (60, 190, 130, 214), "Replay", False),
    ("core", "serif", (440, 164, 540, 188), "ARCHEUS", True),
    ("orchestrates", "serif", (492, 236, 582, 258), "orchestrates", False),
    ("fix", "serif", (430, 346, 550, 374), "Fix date test", False),
    ("verifying", "sans", (446, 378, 532, 398), "Verifying", False),
    ("executes", "serif", (366, 427, 434, 449), "executes", False),
    ("verifies", "serif", (544, 427, 602, 449), "verifies", False),
    ("codex", "serif", (300, 576, 374, 596), "Codex", False),
    ("execution", "serif", (300, 598, 376, 618), "execution", False),
    ("produces", "serif", (456, 588, 520, 608), "produces", False),
    ("verification", "serif", (580, 590, 680, 612), "Verification", False),
    ("results", "serif", (452, 733, 524, 756), "Results", False),
    ("title", "serif", (800, 86, 1250, 144), "Replay \u00b7 Fix date test", False),
    ("t1", "serif", (800, 176, 880, 208), "09:00", False),
    ("t2", "serif", (800, 262, 880, 294), "09:12", False),
    ("t3", "serif", (800, 348, 880, 380), "09:18", False),
    ("t4", "serif", (800, 436, 880, 468), "09:24", False),
    ("t5", "serif", (800, 524, 880, 556), "09:25", False),
    ("h1", "serif", (930, 172, 1200, 200), "Task initiated", False),
    ("s1", "sans", (930, 202, 1240, 222), "Scope, authority and starting state captured", False),
    ("h2", "serif", (930, 258, 1200, 286), "Files changed", False),
    ("s2", "sans", (930, 288, 1260, 308), "Changes and resulting artifacts linked to the task", False),
    ("h3", "serif", (930, 344, 1200, 372), "Tests passed", False),
    ("s3", "sans", (930, 374, 1240, 394), "Validation evidence recorded", False),
    ("h4", "serif", (930, 432, 1200, 460), "External response lost", False),
    ("s4", "sans", (930, 462, 1240, 482), "Side effect classified as uncertain", False),
    ("h5", "serif", (930, 520, 1200, 548), "Workflow suspended", False),
    ("s5", "sans", (930, 550, 1270, 570), "No unsafe retry. Operator reconciliation required.", False),
    ("c1", "sans", (1310, 176, 1388, 196), "Intended", False),
    ("c2", "sans", (1310, 262, 1388, 282), "Recorded", False),
    ("c3", "sans", (1310, 349, 1388, 369), "Verified", False),
    ("c4", "sans", (1306, 437, 1388, 457), "Uncertain", False),
    ("c5", "sans", (1306, 525, 1388, 545), "Needs you", False),
    ("c6", "sans", (1310, 620, 1388, 640), "Operator", False),
    ("reconcile_h", "serif", (930, 618, 1080, 646), "Reconcile", False),
    ("btn_reconcile", "sans", (960, 668, 1132, 690), "Reconcile", False),
    ("btn_open", "sans", (1190, 668, 1372, 690), "Open evidence", False),
    ("footer", "sans", (918, 746, 1240, 770), "Not every external effect can be reversed.", False),
]


def ink_box(gray, box, bg_thresh=40):
    x0, y0, x1, y1 = box
    sub = gray[y0:y1, x0:x1].astype(np.int16)
    med = np.median(sub)
    m = sub > med + bg_thresh
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return None
    return (xs.min() + x0, ys.min() + y0, xs.max() + x0 + 1, ys.max() + y0 + 1)


def pil_ink(path, size, text, wght=400):
    f = ImageFont.truetype(path, size=max(1, int(round(size * 8))))
    try:
        f.set_variation_by_axes([wght])
    except Exception:
        pass
    img = Image.new("L", (int(size * 8 * len(text) * 1.2) + 40, int(size * 8 * 2.4)), 0)
    ImageDraw.Draw(img).text((20, int(size * 8 * 0.4)), text, font=f, fill=255)
    a = np.array(img) > 110
    ys, xs = np.nonzero(a)
    if len(xs) == 0:
        return 0.0, 0.0
    return (xs.max() - xs.min() + 1) / 8.0, (ys.max() - ys.min() + 1) / 8.0


def cap_ratio(path):
    f = ImageFont.truetype(path, size=400)
    try:
        f.set_variation_by_axes([400])
    except Exception:
        pass
    bb = f.getbbox("H")
    return (bb[3] - bb[1]) / 400.0


def solve_size(font, wght, text, target_w, lo=6.0, hi=80.0):
    for _ in range(18):
        mid = (lo + hi) / 2
        w, _h = pil_ink(FONTS[font], mid, text, wght)
        if w < target_w:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main():
    im = cv2.imread(CON)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    ratios = {f: cap_ratio(p) for f, p in FONTS.items()}
    print(f"{'item':<14}{'concept x0 y0 x1 y1':>24}{'w x h':>10}{'size':>7}{'track':>7}{'err px':>8}")
    for name, font, box, text, spaced in ITEMS:
        ib = ink_box(gray, box)
        if ib is None:
            print(name, "no ink")
            continue
        cw, ch = ib[2] - ib[0], ib[3] - ib[1]
        wght = SERIF_WGHT if font == "serif" else 400
        n = len(text)
        if spaced:
            size = max(MIN_FRAME, round(ch / ratios[font], 1))
            w0, _ = pil_ink(FONTS[font], size, text, wght)
            track = round((cw - w0) / max(1, n - 1), 2)
            err = 0.0
        else:
            size = max(MIN_FRAME, round(solve_size(font, wght, text, cw), 1))
            w0, _ = pil_ink(FONTS[font], size, text, wght)
            track = 0.0
            err = round(w0 - cw, 1)
        print(f"{name:<14}{str(ib):>24}{f'{cw} x {ch}':>10}{size:>7}{track:>7}{err:>8}")


if __name__ == "__main__":
    main()
