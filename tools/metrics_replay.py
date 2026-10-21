"""Replay regional metrics, full resolution, unblurred: concept against a render at 1440 x 810.

Run: py -I tools/metrics_replay.py render_frame.png [out_dir]
Prints mean absolute RGB difference (0 to 255) and the percentage of pixels above 24 per region. Regions are the
art-removal boxes (text, marks, chips, buttons) and the rest of the frame, so "art only" shows registration of the base.
Writes the abs-diff x4 image and the 50 percent overlay when out_dir is given.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from art_replay import DISCS, HEADER_FIT, PANEL_FIT, RAIL, TEXT_BOXES  # noqa: E402

CON = r"D:/hub-concepts-codex4/replay-2-desktop-v2.png"


def region_mask(shape, boxes, discs=(), rail=None):
    m = np.zeros(shape, bool)
    for x0, y0, x1, y1 in boxes:
        m[y0:y1, x0:x1] = True
    for cx, cy, r in discs:
        yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
        m |= (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    if rail:
        x0, y0, x1, y1 = rail
        m[y0:y1, x0:x1] = True
    return m


def stats(d, m):
    if not m.any():
        return None
    v = d[m]
    return float(v.mean()), float((v.max(axis=1) > 24).mean() * 100)


def main(render_path, out_dir=None):
    c = cv2.imread(CON).astype(np.int16)
    r = cv2.imread(render_path)[:810, :1440].astype(np.int16)  # the frame; the footer strip is below it
    H, W = c.shape[:2]
    assert (H, W) == (810, 1440), (H, W)
    d = np.abs(c - r)
    live_text = [b for b in TEXT_BOXES]
    live_fit = [(x0, y0, x1, y1) for x0, y0, x1, y1, _k, _f in PANEL_FIT] + [(x0, y0, x1, y1) for x0, y0, x1, y1, _p in HEADER_FIT]
    live_all = region_mask((H, W), live_text + live_fit, DISCS, RAIL)
    art_only = ~live_all
    regions = {
        "art only (outside live boxes)": art_only,
        "text boxes": region_mask((H, W), live_text),
        "live marks (discs)": region_mask((H, W), [], DISCS),
        "chips, buttons, header controls": region_mask((H, W), live_fit),
        "rail column": region_mask((H, W), [], (), RAIL),
        "header strip": region_mask((H, W), [(880, 0, 1440, 60)]),
        "panel (rows, title, footer)": region_mask((H, W), [(779, 67, 1421, 787)]),
        "full frame": np.ones((H, W), bool),
    }
    print(f"{'region':<34}{'mean abs':>10}{'% > 24':>9}")
    for name, m in regions.items():
        s = stats(d, m)
        print(f"{name:<34}{s[0]:>10.2f}{s[1]:>9.2f}")
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        cv2.imwrite(os.path.join(out_dir, "absdiff_x4.png"), np.clip(np.abs(c - r) * 4, 0, 255).astype(np.uint8))
        cv2.imwrite(os.path.join(out_dir, "alpha50.png"), ((c + r) // 2).astype(np.uint8))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
