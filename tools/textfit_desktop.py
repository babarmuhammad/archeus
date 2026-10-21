"""Solve font sizes for the desktop Overview text from the concept raster.

Run: py -I tools/textfit_desktop.py
For each text item, the concept ink box is measured (contrast against the local background inside a search
box) and the font size is solved so that the PIL ink width of the same string matches it. Output is a table of
size and width error in px; the sizes are then written into style.css by hand (see the round 10e README).
"""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CON = r"D:/hub-concepts-codex4/desktop-1-now-v2.png"
FONTS = {
    "serif": r"D:/archeus-t123-desktop/clients/v2-prototype/fonts/EBGaramond-wght.ttf",
    "sans": r"D:/archeus-t123-desktop/clients/v2-prototype/fonts/Inter-wght-opsz.ttf",
}
# name, font, weight, search box (x0, y0, x1, y1) in master px, text
ITEMS = [
    ("status", "sans", 400, (896, 16, 1074, 36), "Not stopped \u00b7 accepts new work"),
    ("fixture", "sans", 400, (16, 36, 136, 50), "CONCEPT FIXTURE"),
    ("wordmark_v2", "serif", 400, (18, 14, 166, 34), "ARCHEUS V2"),
    ("kicker", "sans", 400, (172, 52, 220, 68), "NOW"),
    ("headline", "serif", 400, (172, 68, 646, 122), "1 needs you \u00b7 1 verifying"),
    ("lede_1", "serif", 400, (172, 122, 580, 137), "Live constellation of your work. Missions, projects and ideas"),
    ("lede_2", "serif", 400, (172, 140, 430, 160), "in context, moving forward together."),
    ("core", "serif", 400, (556, 380, 716, 408), "ARCHEUS"),
    ("l_search", "serif", 400, (350, 282, 486, 302), "Search provenance"),
    ("l_review_plan", "sans", 400, (350, 304, 440, 320), "Review plan"),
    ("l_docs", "serif", 400, (392, 402, 476, 420), "Docs refresh"),
    ("l_done", "sans", 400, (392, 422, 440, 438), "Done"),
    ("l_offline", "serif", 400, (1050, 166, 1144, 184), "Offline capture"),
    ("l_captured", "sans", 400, (1050, 185, 1110, 199), "Captured"),
    ("l_export", "serif", 400, (1062, 220, 1156, 240), "Export backup"),
    ("l_new", "sans", 400, (1062, 240, 1100, 254), "New"),
    ("l_notes", "serif", 400, (1172, 102, 1222, 124), "Notes"),
    ("l_fix", "serif", 400, (850, 332, 942, 352), "Fix date test"),
    ("l_verifying", "sans", 400, (850, 352, 904, 368), "Verifying"),
    ("l_codex", "serif", 400, (904, 420, 966, 442), "Codex"),
    ("l_execution", "sans", 400, (904, 441, 966, 458), "execution"),
    ("l_verification", "serif", 400, (818, 482, 890, 500), "Verification"),
    ("l_results", "serif", 400, (936, 480, 986, 498), "Results"),
    ("l_ideas", "serif", 400, (1206, 402, 1248, 420), "Ideas"),
    ("l_early", "sans", 400, (1206, 421, 1290, 436), "Early concepts."),
    ("chat_you", "sans", 400, (388, 536, 420, 554), "You"),
    ("chat_1", "sans", 400, (446, 534, 700, 556), "Open a mission in Notes: Export backup"),
    ("chat_2", "sans", 400, (446, 574, 760, 596), "Mission created in Notes. Start it when you like."),
    ("card_q", "sans", 400, (446, 622, 668, 644), "Start and plan Export backup?"),
    ("card_start", "sans", 400, (728, 624, 778, 644), "Start"),
    ("card_keep", "sans", 400, (820, 624, 926, 644), "Keep as mission"),
    ("placeholder", "sans", 400, (352, 678, 452, 698), "Tell Archeus\u2026"),
    ("nav_now", "sans", 400, (62, 86, 102, 104), "Now"),
    ("nav_projects", "sans", 400, (62, 133, 124, 152), "Projects"),
    ("nav_replay", "sans", 400, (62, 175, 116, 194), "Replay"),
    ("tell", "sans", 400, (1108, 20, 1156, 36), "Tell"),
    ("stop", "sans", 400, (1208, 20, 1262, 36), "Stop"),
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
        if "Inter" in path:
            f.set_variation_by_axes([14, wght])
        else:
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
        f.set_variation_by_axes([14, 400] if "Inter" in path else [400])
    except Exception:
        pass
    bb = f.getbbox("H")
    return (bb[3] - bb[1]) / 400.0


SPACED = {"wordmark_v2", "core", "fixture", "kicker"}
MIN_FRAME = 11.0  # owner rule (round 10e): frame text is at least 11 px


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
    print(f"{'item':<15}{'concept w x h':>16}{'size':>7}{'track':>7}{'pil w':>8}{'err px':>8}")
    rows = []
    for name, font, wght, box, text in ITEMS:
        ib = ink_box(gray, box)
        if ib is None:
            print(name, "no ink")
            continue
        cw, ch = ib[2] - ib[0], ib[3] - ib[1]
        n = len(text)
        if name in SPACED:
            size = max(MIN_FRAME, round(ch / ratios[font], 1))
            w0, _ = pil_ink(FONTS[font], size, text, wght)
            track = round((cw - w0) / max(1, n - 1), 2)
            pw = w0 + track * (n - 1)
        else:
            size = round(solve_size(font, wght, text, cw), 1)
            track = 0.0
            if name in ("status", "tell", "stop"):
                size = max(MIN_FRAME, size)
            pw, _ = pil_ink(FONTS[font], size, text, wght)
        rows.append((name, font, size, track, cw, ch, pw - cw))
        print(f"{name:<15}{f'{cw} x {ch}':>16}{size:>7}{track:>7}{pw:>8.1f}{pw - cw:>8.1f}")
    return rows


if __name__ == "__main__":
    main()
