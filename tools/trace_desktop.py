"""Trace the desktop Overview concept raster into scene data for the V2 prototype.

Run: py -I tools/trace_desktop.py [concept.png] [out.js]
Reads the 1296 x 729 concept, masks text and marks, inpaints them, then emits
clients/v2-prototype/scene-desktop.js: a small blurred background grid, line
segments with sampled colour, node dots and Delaunay facet fills.
"""
import base64
import json
import sys

import cv2
import numpy as np
from scipy.spatial import Delaunay

CONCEPT = sys.argv[1] if len(sys.argv) > 1 else r"D:/hub-concepts-codex4/desktop-1-now-v2.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"D:/archeus-t123-desktop/clients/v2-prototype/scene-desktop.js"

# Text and chrome boxes in concept pixels (x0, y0, x1, y1), measured on the concept.
TEXT_BOXES = [
    (14, 12, 162, 50),      # wordmark and fixture line
    (868, 10, 1284, 46),    # status line, Tell, Stop
    (14, 62, 150, 262),     # rail
    (172, 50, 218, 68),     # kicker NOW
    (172, 66, 642, 122),    # headline
    (172, 118, 574, 164),   # lede
    (560, 378, 712, 408),   # ARCHEUS wordmark
    (350, 282, 484, 320),   # Search provenance and Review plan
    (350, 324, 458, 362),   # Review button
    (388, 400, 472, 438),   # Docs refresh and Done
    (1048, 164, 1140, 200), # Offline capture and Captured
    (1060, 216, 1154, 256), # Export backup and New
    (1168, 100, 1292, 154), # Notes title and sub
    (846, 328, 940, 368),   # Fix date test and Verifying
    (902, 418, 966, 458),   # Codex and execution
    (818, 478, 890, 500),   # Verification
    (936, 478, 984, 500),   # Results
    (1204, 400, 1284, 438), # Ideas and Early concepts
    (318, 282, 346, 314),   # Search provenance diamond
    (354, 392, 384, 422),   # Docs refresh diamond
    (1020, 164, 1050, 192), # Offline capture diamond
    (1024, 214, 1058, 248), # Export backup sparkle
    (810, 326, 844, 362),   # Fix date test star
    (812, 404, 922, 490),   # Codex triangle, dots and code glyph
]
SCENE_Y_MAX = 520  # chat and bar start below this row


def main():
    im = cv2.imread(CONCEPT)
    H, W = im.shape[:2]
    assert (W, H) == (1296, 729), (W, H)

    mask = np.zeros((H, W), np.uint8)
    for x0, y0, x1, y1 in TEXT_BOXES:
        mask[y0:y1, x0:x1] = 255
    mask[SCENE_Y_MAX:, :] = 255
    mask[:, :140] = 255
    mask[:, 1290:] = 255
    grow = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    clean = cv2.inpaint(im, grow, 4, cv2.INPAINT_TELEA)

    # Background: heavy blur of the cleaned image, sampled to a small grid.
    bg = cv2.GaussianBlur(clean, (0, 0), 28)
    grid = cv2.resize(bg, (48, 27), interpolation=cv2.INTER_AREA)
    ok, png = cv2.imencode(".png", grid)
    assert ok
    bg_b64 = base64.b64encode(png.tobytes()).decode("ascii")

    gray = cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)

    # Line segments (LSD), sampled peak colour per segment.
    lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    lines = lsd.detect(gray)[0]
    segs = []
    if lines is not None:
        for (x1, y1, x2, y2) in lines.reshape(-1, 4):
            if x1 < 130 or x2 < 130 or y1 > SCENE_Y_MAX or y2 > SCENE_Y_MAX:
                continue
            L = float(np.hypot(x2 - x1, y2 - y1))
            if L < 9:
                continue
            ts = np.linspace(0.2, 0.8, 9)
            pts = [(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t) for t in ts]
            peaks = []
            for (px, py) in pts:
                xi, yi = int(round(px)), int(round(py))
                if 0 <= xi < W and 0 <= yi < H:
                    win = clean[max(0, yi - 1):yi + 2, max(0, xi - 1):xi + 2].reshape(-1, 3)
                    peaks.append(win[np.argmax(win.sum(axis=1))])
            if not peaks:
                continue
            peak = np.median(np.array(peaks), axis=0)  # BGR
            if peak.max() < 30:
                continue
            segs.append([round(float(x1), 1), round(float(y1), 1), round(float(x2), 1), round(float(y2), 1),
                         int(peak[2]), int(peak[1]), int(peak[0])])

    # Node dots: bright compact blobs outside the text.
    bright = (gray > 115).astype(np.uint8) * 255
    bright[mask > 0] = 0
    n, lab, st, cen = cv2.connectedComponentsWithStats(bright, connectivity=8)
    nodes = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 4 or a > 90 or w > 14 or h > 14 or y > SCENE_Y_MAX - 4:
            continue
        if x < 140:
            continue
        cx, cy = cen[i]
        r = max(1.5, np.sqrt(a / np.pi))
        ys, xs = np.nonzero(lab[y:y + h, x:x + w] == i)
        col = clean[y + ys, x + xs].mean(axis=0)  # BGR
        nodes.append([round(float(cx), 1), round(float(cy), 1), round(float(r), 1),
                      int(col[2]), int(col[1]), int(col[0])])

    # Facets: Delaunay of the node centres, fill colour = median of the cleaned pixels in each triangle.
    fills = []
    if len(nodes) >= 4:
        P = np.array([[n_[0], n_[1]] for n_ in nodes])
        tri = Delaunay(P)
        for s in tri.simplices:
            tp = P[s]
            cen_ = tp.mean(axis=0)
            if not (150 < cen_[0] < 1290 and 40 < cen_[1] < SCENE_Y_MAX):
                continue
            area = abs(np.cross(tp[1] - tp[0], tp[2] - tp[0])) / 2
            if area < 4 or area > 60000:
                continue
            tm = np.zeros((H, W), np.uint8)
            cv2.fillPoly(tm, [tp.astype(np.int32)], 1)
            ys, xs = np.nonzero(tm)
            px = clean[ys, xs].astype(float)
            col = np.median(px, axis=0)  # BGR
            fills.append([[round(float(a_), 1), round(float(b_), 1)] for a_, b_ in tp] +
                         [int(col[2]), int(col[1]), int(col[0])])

    data = {
        "w": W, "h": H,
        "bg": {"w": 48, "h": 27, "png": bg_b64},
        "lines": segs,
        "nodes": nodes,
        "fills": fills,
    }
    body = json.dumps(data, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("// Traced from the Codex desktop Overview concept (desktop-1-now-v2.png, 1296 x 729).\n")
        f.write("// Generated by tools/trace_desktop.py. Do not edit by hand.\n")
        f.write("window.ARCHEUS_SCENE_DESK = " + body + ";\n")
    print("lines", len(segs), "nodes", len(nodes), "fills", len(fills), "bytes", len(body))


if __name__ == "__main__":
    main()
