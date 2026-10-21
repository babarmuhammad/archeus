"""Build the Replay base art: the concept raster with all live content removed.

Run: py -I tools/art_replay.py [concept.png] [out_dir]
Writes <out_dir>/replay-base.webp (lossless) and replay-mask.png (the removal mask, for review). The master is the concept at its own size, 1440 x 810.

Glyph pixels are masked by contrast inside text boxes, so mesh wires that cross a box stay. Panel text is refilled
from a plane fit of its own row card (the card is a flat tint with a gradient), so no ghost of a glyph remains.
Header controls and chips are refilled from a ring around them. Marks are discs refilled from their ring.
Only bright pixels (glyphs, wires, glows) are excluded from every fit.
"""
import sys

import cv2
import numpy as np

CONCEPT = sys.argv[1] if len(sys.argv) > 1 else r"D:/hub-concepts-codex4/replay-2-desktop-v2.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"D:/archeus-t123-replay/clients/v2-prototype/art"
H, W = 810, 1440

# Glyph boxes (x0, y0, x1, y1) in master px: text that is live on top of the art.
TEXT_BOXES = [
    (14, 12, 212, 60),       # wordmark and CONCEPT FIXTURE
    (898, 10, 1150, 40),     # status dot and text
    (436, 160, 540, 192),    # ARCHEUS label under the star
    (490, 234, 582, 260),    # orchestrates
    (428, 344, 550, 376),    # Fix date test
    (440, 376, 534, 400),    # Verifying (blue)
    (364, 425, 436, 451),    # executes
    (540, 425, 604, 451),    # verifies
    (296, 574, 378, 620),    # Codex execution
    (452, 584, 524, 610),    # produces
    (576, 588, 684, 614),    # Verification
    (450, 730, 526, 760),    # Results
    (796, 80, 1252, 148),    # panel title
    (796, 166, 884, 228),    # row time 1
    (796, 252, 884, 314),    # row time 2
    (796, 338, 884, 402),    # row time 3
    (796, 426, 884, 490),    # row time 4
    (796, 514, 884, 580),    # row time 5
    (918, 166, 1290, 228),   # row 1 title and sub
    (918, 252, 1290, 314),   # row 2
    (918, 338, 1290, 402),   # row 3
    (918, 426, 1290, 490),   # row 4
    (918, 514, 1290, 580),   # row 5
    (918, 612, 1290, 652),   # Reconcile title
    (918, 745, 1240, 772),   # footer line
]
# Row card that holds each panel box: its interior is the fit region (x0, y0, x1, y1).
CARDS = {
    "title": (790, 72, 1410, 154),
    "row1": (798, 161, 1402, 231),
    "row2": (798, 247, 1402, 317),
    "row3": (798, 333, 1402, 404),
    "row4": (798, 420, 1402, 493),
    "row5": (798, 508, 1402, 582),
    "reconcile": (798, 604, 1402, 706),
}
# Panel-owned boxes: (x0, y0, x1, y1, card key, feather). Chips and buttons sit inside their card.
PANEL_FIT = [
    (1298, 166, 1396, 208, "row1", 2),       # chip Intended
    (1298, 252, 1396, 294, "row2", 2),       # chip Recorded
    (1298, 339, 1396, 382, "row3", 2),       # chip Verified
    (1294, 427, 1396, 469, "row4", 2),       # chip Uncertain
    (1294, 515, 1396, 557, "row5", 2),       # chip Needs you
    (1298, 610, 1396, 652, "reconcile", 2),  # chip Operator
    (934, 654, 1160, 700, "reconcile", 2),   # Reconcile button
    (1168, 654, 1394, 700, "reconcile", 2),  # Open evidence button
]
# Header controls: (x0, y0, x1, y1), refilled from a ring around them (pad).
HEADER_FIT = [
    (1186, 9, 1300, 51, 6),          # Tell
    (1306, 9, 1420, 51, 6),          # Stop
]
# Discs round the live marks (cx, cy, r). The glow spreads past the mark, so the disc is refilled from a ring.
DISCS = [
    (488, 328, 14),          # mission node (state colour is live; the glow beyond the disc stays raster)
    (897, 194, 8),           # row 1 dot
    (897, 281, 8),           # row 2 dot
    (897, 368, 14),          # row 3 check
    (897, 455, 14),          # row 4 diamond
    (897, 543, 14),          # row 5 diamond
    (897, 637, 12),          # reconcile dashed circle
]
# Rail column (x0, y0, x1, y1): every item is live; the column is one flat fill, the divider at x 192 stays.
RAIL = (0, 0, 188, 810)
GLYPH_CONTRAST = 14
SPINE_X = (888, 905)     # the timeline spine: never refilled, never fitted


def main():
    im = cv2.imread(CONCEPT)
    assert im.shape[:2] == (H, W), im.shape
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    b, g, r = [im[:, :, i].astype(np.int16) for i in range(3)]
    sat = np.clip(np.maximum(r - b, b - r), 0, 255).astype(np.uint8)
    local_bg = cv2.medianBlur(gray, 21).astype(np.int16)
    contrast = gray.astype(np.int16) - local_bg

    # Removal mask: glyph pixels inside text boxes, plus the solid boxes, discs and the rail column.
    m = np.zeros((H, W), np.uint8)
    for x0, y0, x1, y1 in TEXT_BOXES:
        hit = (contrast[y0:y1, x0:x1] > GLYPH_CONTRAST) | (sat[y0:y1, x0:x1] > 70)
        m[y0:y1, x0:x1] = np.where(hit, 255, 0)
    for x0, y0, x1, y1, _k, _f in PANEL_FIT:
        m[y0:y1, x0:x1] = 255
    for x0, y0, x1, y1, _p in HEADER_FIT:
        m[y0:y1, x0:x1] = 255
    for cx, cy, rr in DISCS:
        cv2.circle(m, (cx, cy), rr + 1, 255, -1)
    x0, y0, x1, y1 = RAIL
    m[y0:y1, x0:x1] = 255
    grow = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    clean = cv2.inpaint(im, grow, 3, cv2.INPAINT_TELEA)

    # Valid pixels for every fit: not removed, not bright (glyph, wire, glow), not on the spine.
    valid = (cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) == 0) & (contrast < 8)
    valid[:, SPINE_X[0]:SPINE_X[1]] = False

    out = clean.astype(np.float32)
    # Rail column: flat, from its content-free interior (plain dark band).
    col = np.median(im[480:780, 20:150].reshape(-1, 3), axis=0).astype(np.float32)
    rail_m = np.zeros((H, W), np.float32)
    rail_m[0:H, 0:188] = 1.0
    out = out * (1 - rail_m[..., None]) + col[None, None, :] * rail_m[..., None]

    ys, xs = np.mgrid[0:H, 0:W]
    # Panel: a plane fit over each card's own valid interior, applied to the boxes that belong to it.
    for key, rect in CARDS.items():
        cx0, cy0, cx1, cy1 = rect
        inside = np.zeros((H, W), bool)
        inside[cy0:cy1, cx0:cx1] = True
        sel = inside & valid
        fit = np.zeros((H, W, 3), np.float32)
        u = (xs - (cx0 + cx1) / 2) / ((cx1 - cx0) / 2)
        v = (ys - (cy0 + cy1) / 2) / ((cy1 - cy0) / 2)
        A = np.stack([np.ones_like(u), u, v], axis=-1)
        for c in range(3):
            coef, *_ = np.linalg.lstsq(A[sel], im[:, :, c][sel].astype(np.float64), rcond=None)
            fit[:, :, c] = (A @ coef).astype(np.float32)
        boxes = [(x0_, y0_, x1_, y1_, f) for x0_, y0_, x1_, y1_, k, f in PANEL_FIT if k == key]
        boxes += [(x0_, y0_, x1_, y1_, 1) for x0_, y0_, x1_, y1_ in TEXT_BOXES if cx0 <= x0_ < cx1 and cy0 <= y0_ < cy1]
        for x0_, y0_, x1_, y1_, f in boxes:
            bm = np.zeros((H, W), np.float32)
            bm[y0_:y1_, x0_:x1_] = 1.0
            soft = cv2.GaussianBlur(bm, (0, 0), f) if f > 1 else bm
            out = out * (1 - soft[..., None]) + fit * soft[..., None]

    # Header controls: a plane fit around each, from valid pixels of a ring.
    for x0_, y0_, x1_, y1_, pad in HEADER_FIT:
        ring = np.zeros((H, W), bool)
        ring[max(0, y0_ - pad):min(H, y1_ + pad), max(0, x0_ - pad):min(W, x1_ + pad)] = True
        ring[y0_:y1_, x0_:x1_] = False
        sel = ring & valid
        u = (xs - 720) / 720.0
        v = (ys - 405) / 405.0
        A = np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=-1)
        fit = np.zeros((H, W, 3), np.float32)
        for c in range(3):
            coef, *_ = np.linalg.lstsq(A[sel], im[:, :, c][sel].astype(np.float64), rcond=None)
            fit[:, :, c] = (A @ coef).astype(np.float32)
        bm = np.zeros((H, W), np.float32)
        bm[y0_:y1_, x0_:x1_] = 1.0
        soft = cv2.GaussianBlur(bm, (0, 0), 2)
        out = out * (1 - soft[..., None]) + fit * soft[..., None]

    # Discs: refilled from the valid ring round each mark.
    for cx, cy, rr in DISCS:
        d = np.hypot(xs - cx, ys - cy)
        sel = (d > rr + 4) & (d < rr + 16) & valid
        u = (xs - 720) / 720.0
        v = (ys - 405) / 405.0
        A = np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=-1)
        fit = np.zeros((H, W, 3), np.float32)
        for c in range(3):
            coef, *_ = np.linalg.lstsq(A[sel], im[:, :, c][sel].astype(np.float64), rcond=None)
            fit[:, :, c] = (A @ coef).astype(np.float32)
        mm = np.clip((rr + 0.5 - d) / 1.5, 0, 1).astype(np.float32)
        out = out * (1 - mm[..., None]) + fit * mm[..., None]

    out = np.clip(out, 0, 255).astype(np.uint8)
    cv2.imwrite(f"{OUT}/replay-mask.png", m)
    # Lossless WebP (quality 101 in OpenCV): decodes pixel-exact to the base, and stays under 600 KB.
    ok, buf = cv2.imencode(".webp", out, [cv2.IMWRITE_WEBP_QUALITY, 101])
    open(f"{OUT}/replay-base.webp", "wb").write(buf.tobytes())
    print("webp bytes", len(buf))


if __name__ == "__main__":
    main()
