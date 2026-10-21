"""Build the desktop Overview base art: the concept raster with all live content removed.

Run: py -I tools/art_desktop.py [concept.png] [out_dir]
Writes <out_dir>/desktop-now-base.png (lossless) and <out_dir>/desktop-now-base.webp (lossless),
and <out_dir>/mask.png (the removal mask, for review). Glyph pixels are masked by colour inside text
boxes, so mesh wires that cross a label box are kept and inpainted only where they touch a glyph.
"""
import sys

import cv2
import numpy as np

CONCEPT = sys.argv[1] if len(sys.argv) > 1 else r"D:/hub-concepts-codex4/desktop-1-now-v2.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"D:/archeus-t123-desktop/clients/v2-prototype/art"

# Boxes that hold live content (x0, y0, x1, y1) in master px (1296 x 729), measured on the concept.
TEXT_BOXES = [
    (14, 12, 162, 50),       # wordmark and fixture line
    (868, 10, 1284, 46),     # status dot and text, Tell, Stop
    (14, 62, 140, 262),      # rail: active band, icons, labels
    (172, 50, 218, 68),      # NOW kicker
    (172, 66, 642, 122),     # headline
    (172, 118, 574, 164),    # lede
    (560, 378, 712, 408),    # ARCHEUS wordmark
    (350, 282, 484, 320),    # Search provenance, Review plan
    (350, 324, 458, 362),    # Review button
    (388, 400, 472, 438),    # Docs refresh, Done
    (1048, 164, 1140, 200),  # Offline capture, Captured
    (1060, 216, 1154, 256),  # Export backup, New
    (1168, 100, 1292, 154),  # Notes
    (846, 328, 940, 368),    # Fix date test, Verifying
    (902, 418, 966, 458),    # Codex, execution
    (818, 478, 890, 500),    # Verification
    (936, 478, 984, 500),    # Results
    (1204, 400, 1284, 438),  # Ideas, Early concepts
]
# Solid mark boxes (glyph shapes are replaced live): dots, diamonds, star, sparkle, code glyph.
MARK_BOXES = [
    (316, 280, 346, 316),    # Search provenance diamond
    (354, 392, 384, 422),    # Docs refresh diamond
    (1018, 162, 1050, 194),  # Offline capture diamond
    (1022, 210, 1060, 250),  # Export backup sparkle
    (798, 312, 862, 378),    # Fix date test star and its halo (round 10e)
    (850, 398, 892, 438),    # Codex apex dot and halo (round 10e)
    (800, 480, 820, 500),    # Verification dot
    (918, 480, 938, 500),    # Results dot
    (850, 432, 890, 462),    # code glyph
]
# Chat, composer and the Start card (master px, below the frame's header).
CHAT_BOX = (296, 516, 1000, 718)
# Bright threshold: glyph pixels are much brighter than mesh wires.
GLYPH_CONTRAST = 14


def glyph_mask(gray, sat):
    h, w = gray.shape
    local_bg = cv2.medianBlur(gray, 21).astype(np.int16)
    contrast = gray.astype(np.int16) - local_bg
    m = np.zeros((h, w), np.uint8)
    for x0, y0, x1, y1 in TEXT_BOXES:
        hit = (contrast[y0:y1, x0:x1] > GLYPH_CONTRAST) | (sat[y0:y1, x0:x1] > 70)
        m[y0:y1, x0:x1] = np.where(hit, 255, 0)
    for x0, y0, x1, y1 in MARK_BOXES:
        m[y0:y1, x0:x1] = 255
    x0, y0, x1, y1 = CHAT_BOX
    m[y0:y1, x0:x1] = 255
    return m


# (x0, y0, x1, y1, ring pad, feather sigma) for flat regions.
FLAT_BOXES = [
    (296, 516, 1000, 718, 40, 9),
    (862, 4, 1290, 52, 30, 3),
    (0, 0, 139, 729, 0, 2),
]


def plane_fill(im, out, box, pad, feather):
    x0, y0, x1, y1 = box
    H, W = im.shape[:2]
    ys, xs = np.mgrid[0:H, 0:W]
    ring = np.zeros((H, W), bool)
    rx0, ry0, rx1, ry1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    ring[ry0:ry1, rx0:rx1] = True
    ring[y0:y1, x0:x1] = False
    if pad == 0:  # rail column is flat: constant median of its content-free interior
        col = np.median(im[300:700, 20:130].reshape(-1, 3), axis=0).astype(np.float32)
        box_m = np.zeros((H, W), np.float32)
        box_m[y0:y1, x0:x1] = 1.0
        soft = cv2.GaussianBlur(box_m, (0, 0), feather)
        return out * (1 - soft[..., None]) + col[None, None, :] * soft[..., None]
    u = (xs - 648) / 648.0
    v = (ys - 364) / 364.0
    A = np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=-1)
    fit = np.zeros((H, W, 3), np.float32)
    Ar = A[ring]
    for c in range(3):
        coef, *_ = np.linalg.lstsq(Ar, im[:, :, c][ring].astype(np.float64), rcond=None)
        fit[:, :, c] = (A @ coef).astype(np.float32)
    box_m = np.zeros((H, W), np.float32)
    box_m[y0:y1, x0:x1] = 1.0
    soft = cv2.GaussianBlur(box_m, (0, 0), feather) if feather else box_m
    return out * (1 - soft[..., None]) + fit * soft[..., None]


# (cx, cy, r) in master px: the Fix date test star, the Codex apex and the Verification and Results dots.
DISCS = [(826, 344, 19), (871, 416, 13), (806, 488, 11), (925, 488, 11)]


def disc_fill(im, out, cx, cy, r):
    H, W = im.shape[:2]
    ys, xs = np.mgrid[0:H, 0:W]
    d = np.hypot(xs - cx, ys - cy)
    ring = (d > r + 4) & (d < r + 22)
    u = (xs - 648) / 648.0
    v = (ys - 364) / 364.0
    A = np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=-1)
    fit = np.zeros((H, W, 3), np.float32)
    for c in range(3):
        coef, *_ = np.linalg.lstsq(A[ring], im[:, :, c][ring].astype(np.float64), rcond=None)
        fit[:, :, c] = (A @ coef).astype(np.float32)
    m = np.clip((r + 0.5 - d) / 1.5, 0, 1).astype(np.float32)
    return out * (1 - m[..., None]) + fit * m[..., None]


def main():
    im = cv2.imread(CONCEPT)
    assert im.shape[:2] == (729, 1296), im.shape
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    b, g, r = [im[:, :, i].astype(np.int16) for i in range(3)]
    sat = np.clip(np.maximum(r - b, b - r), 0, 255).astype(np.uint8)

    m = glyph_mask(gray, sat)
    # Feather: grow the hard mask by 2 px so no glyph halo survives, inpaint the grown mask.
    grow = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    clean = cv2.inpaint(im, grow, 3, cv2.INPAINT_TELEA)
    # Flat UI boxes (chat, header controls, rail column): replace with a quadratic fit of the plum ring around
    # them, feathered at the edge. Inpainting leaves streaks on these; the fit does not.
    out = clean.astype(np.float32)
    for bx0, by0, bx1, by1, pad, feather in FLAT_BOXES:
        out = plane_fill(im, out, (bx0, by0, bx1, by1), pad, feather)
    # Discs round the live marks: the concept's glow spreads past any box, so these are refilled from a ring of
    # neighbouring pixels (the live SVG mark covers the centre). Link segments outside the discs are kept.
    for cx, cy, r in DISCS:
        out = disc_fill(im, out, cx, cy, r)
    out = np.clip(out, 0, 255).astype(np.uint8)

    cv2.imwrite(f"{OUT}/mask.png", grow)
    cv2.imwrite(f"{OUT}/desktop-now-base.png", out, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    cv2.imwrite(f"{OUT}/desktop-now-base.webp", out, [cv2.IMWRITE_WEBP_QUALITY, 101])
    print("mask px", int((grow > 0).sum()))


if __name__ == "__main__":
    main()
